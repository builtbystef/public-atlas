"use client";

import type { EntityKind, EntityStatus } from "@public-atlas/api-client";
import { MaximizeIcon, MinusIcon, PlusIcon } from "lucide-react";
import { useTheme } from "next-themes";
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ComponentType,
  type ReactNode,
  type RefObject,
} from "react";
import type { ForceGraphMethods, ForceGraphProps } from "react-force-graph-2d";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { entityKindLabels, entityStatusLabels } from "@/lib/labels";

import {
  coverage,
  endId,
  graphKinds,
  neighbours,
  nodeRadius,
  ringRadii,
  ringRadius,
  rings,
  shortLabel,
  type Coverage,
  type GraphData,
  type GraphLinkObject,
  type GraphNodeObject,
  type GraphOverlay,
} from "../graph-data";

type Methods = ForceGraphMethods<GraphNodeObject, GraphLinkObject>;
type CanvasProps = ForceGraphProps<GraphNodeObject, GraphLinkObject> & {
  ref?: RefObject<Methods | undefined>;
};

// The library draws on the window at import, so it loads in the browser alone.
const ForceGraph2D = lazy(
  () =>
    import("react-force-graph-2d") as unknown as Promise<{ default: ComponentType<CanvasProps> }>,
);

/** The colours the canvas draws with, read from the console's tokens so both modes match. */
interface Palette {
  kind: Record<EntityKind, string>;
  status: Record<EntityStatus, string>;
  coverage: Record<Coverage, string>;
  muted: string;
  link: string;
  linkStrong: string;
  linkFaint: string;
  review: string;
  rejected: string;
  selection: string;
  text: string;
  halo: string;
  font: string;
}

// Labels fade in as the user zooms: place names first, since they are the landmarks, then the
// rest. Hovered, selected and root nodes are always named.
const PLACE_LABEL_ZOOM: [number, number] = [0.6, 1.6];
const LABEL_ZOOM: [number, number] = [1.4, 3];
const LABEL_PX = 11;
const FLY_MS = 600;
const FLY_ZOOM = 3;
const ZOOM_STEP = 1.6;
const PREFIT_EVERY = 10;
const PREFIT_MS = 250;
const DIM = 0.12;
const ASIDE = 0.25;

/**
 * How hard each kind is pulled to its ring: places hold the shape, and the
 * rest hang off them by their links, nudged outward so they sit on the far
 * side of their place.
 */
const RADIAL_STRENGTH: Record<EntityKind, number> = {
  place: 0.8,
  institution: 0.25,
  homepage: 0.12,
  source: 0.12,
  domain: 0.05,
};

const LINK_DISTANCE: Record<GraphLinkObject["relation"], number> = {
  parent: 60,
  government: 22,
  place: 26,
  serves: 60,
  homepage: 14,
  source: 12,
  domain: 20,
};

/**
 * The picture itself: d3-force physics on a canvas, with the root pinned in
 * the middle and each node pulled to a ring by its depth, so a region reads
 * as its hierarchy. Each node is a disc coloured by the overlay with its
 * status as a fade or a ring, sized by its figure; hovering one lights its
 * neighbours and dims the rest. The canvas keeps the node objects across payloads, so a refetch
 * settles rather than jumps.
 */
export function GraphCanvas({
  data,
  rootId,
  selectedId,
  focus,
  overlay,
  emphasis,
  onSelect,
}: {
  data: GraphData;
  rootId: string | undefined;
  selectedId: string | undefined;
  /** The node to fly to, once the layout has settled; `key` asks again for the same node. */
  focus: { id: string; key: number } | null;
  overlay: GraphOverlay;
  /** The nodes the overlay lights, the rest set aside; null when it lights them all. */
  emphasis: ReadonlySet<string> | null;
  onSelect: (id: string | undefined) => void;
}) {
  const graph = useRef<Methods | undefined>(undefined);
  const { ref: frame, size } = useElementSize<HTMLDivElement>();
  const palette = usePalette();
  const mounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
  const [hovered, setHovered] = useState<GraphNodeObject | null>(null);
  const [pointer, setPointer] = useState<{ x: number; y: number } | null>(null);
  // Where the pointer last was, for the tooltip the moment a hover starts.
  const lastPointer = useRef<{ x: number; y: number } | null>(null);
  const onNodeHover = useCallback((node: GraphNodeObject | null) => {
    setHovered(node);
    setPointer(node ? lastPointer.current : null);
  }, []);
  const related = hovered ? (neighbours(data.links).get(hovered.id) ?? new Set<string>()) : null;

  // The rings, read by the radial force on every tick through a ref: the force is made once.
  const ring = useMemo(() => rings(rootId, data.nodes, data.links), [rootId, data]);
  const radii = useMemo(() => ringRadii(ring), [ring]);
  const layout = useRef({ ring, radii });
  useEffect(() => {
    layout.current = { ring, radii };
  }, [ring, radii]);

  // The root stays in the middle; the rings are around it.
  useEffect(() => {
    for (const node of data.nodes) {
      if (node.id !== rootId) continue;
      node.fx = 0;
      node.fy = 0;
      node.x ??= 0;
      node.y ??= 0;
    }
  }, [data, rootId]);

  // The camera waits for the layout to settle before it moves: a node that is still being
  // pushed about would slide out from under it.
  const engineRunning = useRef(false);
  const pendingFly = useRef<string | null>(null);
  const fittedFor = useRef<string | undefined>(undefined);
  // The handlers the library holds read the newest data through here.
  const latest = useRef(data);
  useEffect(() => {
    latest.current = data;
  }, [data]);

  const flyNow = useCallback((id: string) => {
    const node = latest.current.nodes.find((n) => n.id === id);
    if (!graph.current || node?.x === undefined || node.y === undefined) return false;
    graph.current.centerAt(node.x, node.y, FLY_MS);
    graph.current.zoom(Math.max(graph.current.zoom(), FLY_ZOOM), FLY_MS);
    return true;
  }, []);

  useEffect(() => {
    if (!focus) return;
    if (engineRunning.current || !flyNow(focus.id)) pendingFly.current = focus.id;
  }, [focus, flyNow]);

  const fit = useCallback(() => graph.current?.zoomToFit(FLY_MS, 40), []);
  const zoomBy = useCallback((factor: number) => {
    if (!graph.current) return;
    graph.current.zoom(graph.current.zoom() * factor, FLY_MS / 2);
  }, []);

  // The forces, once the library is in: the rings, a charge that spreads a ring's nodes out,
  // and links that keep an institution by its place and a page by its institution. The
  // library's centring force is dropped: the pinned root is the centre.
  const configure = useCallback((instance: Methods | undefined) => {
    graph.current = instance;
    if (!instance) return;
    instance.d3Force("center", null);
    instance.d3Force(
      "radial",
      radialForce(() => layout.current),
    );
    instance.d3Force("charge")?.strength?.(-80)?.distanceMax?.(500);
    instance.d3Force("link")?.distance?.((link: GraphLinkObject) => LINK_DISTANCE[link.relation]);
  }, []);

  const fill = useCallback(
    (node: GraphNodeObject) => {
      if (!palette) return "transparent";
      switch (overlay) {
        case "kind":
          return palette.kind[node.kind];
        case "status":
          return palette.status[node.status];
        case "coverage": {
          const covered = coverage(node);
          return covered ? palette.coverage[covered] : palette.muted;
        }
        case "domains":
          return emphasis?.has(node.id) ? palette.kind[node.kind] : palette.muted;
      }
    },
    [palette, overlay, emphasis],
  );

  const drawNode = useCallback(
    (node: GraphNodeObject, ctx: CanvasRenderingContext2D, scale: number) => {
      if (!palette || node.x === undefined || node.y === undefined) return;
      const radius = nodeRadius(node);
      const lit = related === null || node.id === hovered?.id || related.has(node.id);
      const aside = emphasis !== null && !emphasis.has(node.id);
      const faded = node.status === "candidate" && overlay !== "status";
      const alpha = !lit ? DIM : aside ? ASIDE : faded ? 0.5 : 1;
      const colour = fill(node);
      ctx.globalAlpha = alpha;
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
      ctx.fillStyle = colour;
      ctx.fill();
      const ring =
        node.id === selectedId
          ? palette.selection
          : node.status === "needs_review" && overlay !== "status"
            ? palette.review
            : node.status === "rejected" && overlay !== "status"
              ? palette.rejected
              : null;
      if (ring) {
        ctx.globalAlpha = lit ? 1 : DIM;
        ctx.lineWidth = (node.id === selectedId ? 2.5 : 1.75) / scale;
        ctx.strokeStyle = ring;
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius + ctx.lineWidth, 0, 2 * Math.PI);
        ctx.stroke();
      }
      // The root: a second, wider ring, so it stands out at any distance.
      if (node.id === rootId) {
        ctx.globalAlpha = lit ? 0.85 : DIM;
        ctx.lineWidth = 1.5 / scale;
        ctx.strokeStyle = palette.selection;
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius + 7 / scale, 0, 2 * Math.PI);
        ctx.stroke();
      }
      const forced =
        node.id === hovered?.id ||
        node.id === selectedId ||
        node.id === rootId ||
        (related?.has(node.id) ?? false) ||
        (overlay === "domains" && node.kind === "domain" && !aside);
      const [from, to] = node.kind === "place" ? PLACE_LABEL_ZOOM : LABEL_ZOOM;
      const labelAlpha = forced ? 1 : Math.min(1, Math.max(0, (scale - from) / (to - from)));
      if (labelAlpha > 0 && lit && (!aside || forced)) {
        const px = LABEL_PX / scale;
        ctx.font = `${node.id === rootId ? "600 " : ""}${px}px ${palette.font}`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.globalAlpha = aside ? ASIDE * 2 : labelAlpha;
        ctx.lineWidth = px / 3;
        ctx.lineJoin = "round";
        ctx.strokeStyle = palette.halo;
        const label = shortLabel(node);
        const y = node.y + radius + (node.id === rootId ? 9 : 2) / scale;
        ctx.strokeText(label, node.x, y);
        ctx.fillStyle = palette.text;
        ctx.fillText(label, node.x, y);
      }
      ctx.globalAlpha = 1;
    },
    [palette, related, hovered, selectedId, rootId, overlay, emphasis, fill],
  );

  const paintPointerArea = useCallback(
    (node: GraphNodeObject, color: string, ctx: CanvasRenderingContext2D) => {
      if (node.x === undefined || node.y === undefined) return;
      ctx.fillStyle = color;
      ctx.beginPath();
      // A little more than the disc, so a small node is easy to hit.
      ctx.arc(node.x, node.y, nodeRadius(node) + 1.5, 0, 2 * Math.PI);
      ctx.fill();
    },
    [],
  );

  const linkColor = useCallback(
    (link: GraphLinkObject) => {
      if (!palette) return "transparent";
      const source = endId(link.source);
      const target = endId(link.target);
      if (related !== null) {
        const touches = source === hovered?.id || target === hovered?.id;
        return touches ? palette.linkStrong : palette.link;
      }
      if (emphasis !== null && !(emphasis.has(source) && emphasis.has(target))) {
        return palette.linkFaint;
      }
      return palette.link;
    },
    [palette, related, hovered, emphasis],
  );

  const linkWidth = useCallback(
    (link: GraphLinkObject) => {
      if (related === null) return 1;
      const touches = endId(link.source) === hovered?.id || endId(link.target) === hovered?.id;
      return touches ? 2 : 0.3;
    },
    [related, hovered],
  );

  const onNodeClick = useCallback((node: GraphNodeObject) => onSelect(node.id), [onSelect]);

  // A dragged node stays where it is dropped unless let go of; the root stays put regardless.
  const onNodeDragEnd = useCallback(
    (node: GraphNodeObject) => {
      if (node.id === rootId) return;
      delete node.fx;
      delete node.fy;
    },
    [rootId],
  );

  const onEngineStop = useCallback(() => {
    engineRunning.current = false;
    // An empty picture settles at once; the camera waits for one with nodes in it.
    if (latest.current.nodes.length === 0) return;
    if (pendingFly.current !== null) {
      if (flyNow(pendingFly.current)) pendingFly.current = null;
      fittedFor.current = rootId;
      return;
    }
    // The first settled picture of a root comes into view whole; later refetches keep the
    // camera where the user put it.
    if (fittedFor.current !== rootId) {
      fittedFor.current = rootId;
      graph.current?.zoomToFit(FLY_MS, 40);
    }
  }, [flyNow, rootId]);

  // While a new root's picture is still settling, the camera keeps it in view every so often,
  // so the user watches it take shape instead of a blank canvas.
  const ticks = useRef(0);
  const onEngineTick = useCallback(() => {
    engineRunning.current = true;
    if (fittedFor.current === rootId || pendingFly.current !== null) return;
    ticks.current += 1;
    if (ticks.current % PREFIT_EVERY === 1) graph.current?.zoomToFit(PREFIT_MS, 40);
  }, [rootId]);

  const tooltip = hovered && pointer && (
    <div
      role="tooltip"
      className="pointer-events-none absolute z-10 max-w-64 rounded-md bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-md ring-1 ring-foreground/10"
      style={{ left: pointer.x + 14, top: pointer.y + 14 }}
    >
      <div className="font-medium">{shortLabel(hovered)}</div>
      <div className="text-muted-foreground">
        {entityKindLabels[hovered.kind]} · {entityStatusLabels[hovered.status]}
      </div>
    </div>
  );

  return (
    <div
      ref={frame}
      className="relative size-full overflow-hidden"
      onPointerMove={(event) => {
        const rect = event.currentTarget.getBoundingClientRect();
        lastPointer.current = { x: event.clientX - rect.left, y: event.clientY - rect.top };
        if (hovered) setPointer(lastPointer.current);
      }}
      onPointerLeave={() => setPointer(null)}
    >
      {mounted && palette && size.width > 0 && (
        <Suspense fallback={<Skeleton className="size-full" />}>
          <ForceGraph2D
            ref={configure as unknown as RefObject<Methods | undefined>}
            graphData={data}
            width={size.width}
            height={size.height}
            nodeId="id"
            nodeCanvasObject={drawNode}
            nodePointerAreaPaint={paintPointerArea}
            nodeLabel=""
            linkColor={linkColor}
            linkWidth={linkWidth}
            d3VelocityDecay={0.3}
            warmupTicks={data.nodes.length > 500 ? 120 : 40}
            cooldownTime={6000}
            onNodeHover={onNodeHover}
            onNodeClick={onNodeClick}
            onNodeDrag={() => setPointer(null)}
            onNodeDragEnd={onNodeDragEnd}
            onBackgroundClick={() => onSelect(undefined)}
            onEngineTick={onEngineTick}
            onEngineStop={onEngineStop}
            minZoom={0.05}
            maxZoom={12}
          />
        </Suspense>
      )}
      {tooltip}
      <div
        role="group"
        aria-label="Zoom"
        className="absolute right-3 bottom-3 flex flex-col gap-1 rounded-md bg-background/80 p-1 shadow-sm ring-1 ring-foreground/10 backdrop-blur-sm"
      >
        <ZoomButton label="Zoom in" onClick={() => zoomBy(ZOOM_STEP)}>
          <PlusIcon />
        </ZoomButton>
        <ZoomButton label="Zoom out" onClick={() => zoomBy(1 / ZOOM_STEP)}>
          <MinusIcon />
        </ZoomButton>
        <ZoomButton label="Fit to view" onClick={fit}>
          <MaximizeIcon />
        </ZoomButton>
      </div>
    </div>
  );
}

/** One of the canvas corner's buttons, its label a tooltip and the accessible name. */
function ZoomButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={<Button variant="ghost" size="icon-sm" onClick={onClick} aria-label={label} />}
      >
        {children}
      </TooltipTrigger>
      <TooltipContent side="left">{label}</TooltipContent>
    </Tooltip>
  );
}

/** A d3 force that pulls each node to its ring; the rings themselves are read on each tick. */
function radialForce(
  lookup: () => { ring: ReadonlyMap<string, number>; radii: readonly number[] },
) {
  let nodes: GraphNodeObject[] = [];
  const force = (alpha: number) => {
    const { ring, radii } = lookup();
    for (const node of nodes) {
      const at = ring.get(node.id);
      if (at === undefined || node.x === undefined || node.y === undefined) continue;
      const target = ringRadius(radii, at);
      const dx = node.x || 1e-6;
      const dy = node.y || 1e-6;
      const distance = Math.hypot(dx, dy);
      const k = ((target - distance) * RADIAL_STRENGTH[node.kind] * alpha) / distance;
      node.vx = (node.vx ?? 0) + dx * k;
      node.vy = (node.vy ?? 0) + dy * k;
    }
  };
  force.initialize = (all: GraphNodeObject[]) => {
    nodes = all;
  };
  return force;
}

/** The element's size, kept current through a ResizeObserver. */
function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      const { width, height } = entry.contentRect;
      setSize((current) =>
        current.width === Math.round(width) && current.height === Math.round(height)
          ? current
          : { width: Math.round(width), height: Math.round(height) },
      );
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return { ref, size };
}

/** A CSS colour expression as the browser resolves it on this page: what a canvas can take. */
function resolveColor(probe: HTMLElement, expression: string): string {
  probe.style.color = expression;
  return getComputedStyle(probe).color;
}

/** The palette, read from the tokens again whenever the theme changes. */
function usePalette(): Palette | null {
  const { resolvedTheme } = useTheme();
  const [palette, setPalette] = useState<Palette | null>(null);
  useEffect(() => {
    const probe = document.createElement("span");
    document.body.append(probe);
    try {
      const read = (expression: string) => resolveColor(probe, expression);
      const kind = Object.fromEntries(
        graphKinds.map((name) => [name, read(`var(--graph-${name})`)]),
      ) as Record<EntityKind, string>;
      const muted = read("var(--muted-foreground)");
      setPalette({
        kind,
        status: {
          verified: read("var(--success)"),
          candidate: muted,
          needs_review: read("var(--warning)"),
          rejected: read("var(--destructive)"),
        },
        coverage: {
          covered: read("var(--success)"),
          partial: read("var(--warning)"),
          missing: read("var(--destructive)"),
        },
        muted,
        link: read("color-mix(in oklch, var(--muted-foreground) 30%, transparent)"),
        linkStrong: read("color-mix(in oklch, var(--foreground) 70%, transparent)"),
        linkFaint: read("color-mix(in oklch, var(--muted-foreground) 10%, transparent)"),
        review: read("var(--warning)"),
        rejected: read("var(--destructive)"),
        selection: read("var(--foreground)"),
        text: read("var(--foreground)"),
        halo: read("var(--background)"),
        font: getComputedStyle(document.body).fontFamily,
      });
    } finally {
      probe.remove();
    }
  }, [resolvedTheme]);
  return palette;
}
