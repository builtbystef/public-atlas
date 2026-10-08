"use client";

import type { EntityKind } from "@public-atlas/api-client";
import { useTheme } from "next-themes";
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  useSyncExternalStore,
  type ComponentType,
  type Ref,
  type RefObject,
} from "react";
import type { ForceGraphMethods, ForceGraphProps } from "react-force-graph-2d";

import { Skeleton } from "@/components/ui/skeleton";

import {
  endId,
  graphKinds,
  neighbours,
  nodeRadius,
  shortLabel,
  type GraphData,
  type GraphLinkObject,
  type GraphNodeObject,
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

/** What the view asks of the canvas. */
export interface GraphCamera {
  /** Bring the whole picture into view. */
  fit: () => void;
}

/** The colours the canvas draws with, read from the console's tokens so both modes match. */
interface Palette {
  kind: Record<EntityKind, string>;
  link: string;
  linkStrong: string;
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
const DOUBLE_CLICK_MS = 350;
const FLY_MS = 600;
const FLY_ZOOM = 3;

/**
 * The picture itself: d3-force physics on a canvas. Each node is a disc
 * coloured by kind with its status as a fade or a ring, sized by its figure;
 * hovering one lights its neighbours and dims the rest. The canvas keeps the
 * node objects across payloads, so a refetch settles rather than jumps.
 */
export function GraphCanvas({
  data,
  rootId,
  selectedId,
  focus,
  onSelect,
  onExpand,
  cameraRef,
}: {
  data: GraphData;
  rootId: string | undefined;
  selectedId: string | undefined;
  /** The node to fly to, once the layout has settled; `key` asks again for the same node. */
  focus: { id: string; key: number } | null;
  onSelect: (id: string | undefined) => void;
  onExpand: (node: GraphNodeObject) => void;
  cameraRef: Ref<GraphCamera>;
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
  const related = hovered ? (neighbours(data.links).get(hovered.id) ?? new Set<string>()) : null;

  // The camera waits for the layout to settle before it moves: a node that is still being
  // pushed about would slide out from under it.
  const engineRunning = useRef(false);
  const pendingFly = useRef<string | null>(null);
  const fittedFor = useRef<string | undefined>(undefined);
  const lastClick = useRef<{ id: string; at: number } | null>(null);
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

  useImperativeHandle(cameraRef, () => ({ fit: () => graph.current?.zoomToFit(FLY_MS, 40) }), []);

  // The forces, once the library is in: a looser link for the hierarchy than for the web,
  // and enough charge that a region's municipalities spread out.
  const configure = useCallback((instance: Methods | undefined) => {
    graph.current = instance;
    if (!instance) return;
    instance.d3Force("charge")?.strength?.(-90)?.distanceMax?.(260);
    instance
      .d3Force("link")
      ?.distance?.((link: GraphLinkObject) =>
        link.relation === "parent" || link.relation === "government" || link.relation === "place"
          ? 60
          : 24,
      );
  }, []);

  const drawNode = useCallback(
    (node: GraphNodeObject, ctx: CanvasRenderingContext2D, scale: number) => {
      if (!palette || node.x === undefined || node.y === undefined) return;
      const radius = nodeRadius(node);
      const lit = related === null || node.id === hovered?.id || related.has(node.id);
      const faded = node.status === "candidate";
      ctx.globalAlpha = lit ? (faded ? 0.5 : 1) : 0.12;
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
      ctx.fillStyle = palette.kind[node.kind];
      ctx.fill();
      const ring =
        node.id === selectedId
          ? palette.selection
          : node.status === "needs_review"
            ? palette.review
            : node.status === "rejected"
              ? palette.rejected
              : null;
      if (ring) {
        ctx.globalAlpha = lit ? 1 : 0.12;
        ctx.lineWidth = (node.id === selectedId ? 2.5 : 1.75) / scale;
        ctx.strokeStyle = ring;
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius + ctx.lineWidth, 0, 2 * Math.PI);
        ctx.stroke();
      }
      const forced =
        node.id === hovered?.id ||
        node.id === selectedId ||
        node.id === rootId ||
        (related?.has(node.id) ?? false);
      const [from, to] = node.kind === "place" ? PLACE_LABEL_ZOOM : LABEL_ZOOM;
      const labelAlpha = forced ? 1 : Math.min(1, Math.max(0, (scale - from) / (to - from)));
      if (labelAlpha > 0 && lit) {
        const px = LABEL_PX / scale;
        ctx.font = `${px}px ${palette.font}`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.globalAlpha = labelAlpha;
        ctx.lineWidth = px / 3;
        ctx.lineJoin = "round";
        ctx.strokeStyle = palette.halo;
        const label = shortLabel(node);
        const y = node.y + radius + 2 / scale;
        ctx.strokeText(label, node.x, y);
        ctx.fillStyle = palette.text;
        ctx.fillText(label, node.x, y);
      }
      ctx.globalAlpha = 1;
    },
    [palette, related, hovered, selectedId, rootId],
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
      if (related === null) return palette.link;
      const touches = endId(link.source) === hovered?.id || endId(link.target) === hovered?.id;
      return touches ? palette.linkStrong : palette.link;
    },
    [palette, related, hovered],
  );

  const linkWidth = useCallback(
    (link: GraphLinkObject) => {
      if (related === null) return 1;
      const touches = endId(link.source) === hovered?.id || endId(link.target) === hovered?.id;
      return touches ? 2 : 0.3;
    },
    [related, hovered],
  );

  const onNodeClick = useCallback(
    (node: GraphNodeObject) => {
      const now = Date.now();
      const last = lastClick.current;
      lastClick.current = { id: node.id, at: now };
      if (last?.id === node.id && now - last.at < DOUBLE_CLICK_MS) {
        lastClick.current = null;
        onExpand(node);
        return;
      }
      onSelect(node.id);
    },
    [onExpand, onSelect],
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

  const onEngineTick = useCallback(() => {
    engineRunning.current = true;
  }, []);

  return (
    <div ref={frame} className="relative size-full overflow-hidden">
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
            warmupTicks={data.nodes.length > 500 ? 40 : 0}
            cooldownTime={6000}
            onNodeHover={setHovered}
            onNodeClick={onNodeClick}
            onBackgroundClick={() => onSelect(undefined)}
            onEngineTick={onEngineTick}
            onEngineStop={onEngineStop}
            minZoom={0.1}
            maxZoom={12}
          />
        </Suspense>
      )}
    </div>
  );
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
      setPalette({
        kind,
        link: read("color-mix(in oklch, var(--muted-foreground) 30%, transparent)"),
        linkStrong: read("color-mix(in oklch, var(--foreground) 70%, transparent)"),
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
