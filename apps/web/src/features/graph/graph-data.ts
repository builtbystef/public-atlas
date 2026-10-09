import type { EntityKind, GraphEdge, GraphNode, GraphOutput } from "@public-atlas/api-client";

/**
 * The graph view's data, between the API's payloads and the canvas: several
 * payloads folded into one picture, node objects kept across refetches so
 * the layout keeps its positions, the rings the layout puts each node on,
 * and the figures the drawing and the panel follow.
 */

/** The kinds in the order the legend shows them: the hierarchy first, then the web. */
export const graphKinds = [
  "place",
  "institution",
  "homepage",
  "source",
  "domain",
] as const satisfies readonly EntityKind[];

/**
 * How much of the graph is drawn: the places and their governments, every
 * institution, or the web too. The picture starts simple and the user opens
 * it up.
 */
export const graphDetails = ["hierarchy", "institutions", "web"] as const;
export type GraphDetail = (typeof graphDetails)[number];

export const graphDetailLabels: Record<GraphDetail, string> = {
  hierarchy: "Places",
  institutions: "Institutions",
  web: "Everything",
};

/** The kinds a level of detail asks the API for. */
export function detailKinds(detail: GraphDetail): EntityKind[] {
  return detail === "web" ? [...graphKinds] : ["place", "institution"];
}

/**
 * What the colour says: the kind, the coverage (whether a place has a
 * government online and an institution a homepage), the status, or the
 * domains that several institutions share.
 */
export const graphOverlays = ["kind", "coverage", "status", "domains"] as const;
export type GraphOverlay = (typeof graphOverlays)[number];

export const graphOverlayLabels: Record<GraphOverlay, string> = {
  kind: "Kind",
  coverage: "Coverage",
  status: "Status",
  domains: "Shared domains",
};

/** A node as the canvas holds it: the API's node with the position the layout gives it. */
export interface GraphNodeObject extends GraphNode {
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number;
  fy?: number;
}

/** A link as the canvas holds it; the layout swaps the ids for the node objects. */
export interface GraphLinkObject {
  source: string | GraphNodeObject;
  target: string | GraphNodeObject;
  relation: GraphEdge["relation"];
}

export interface GraphData {
  nodes: GraphNodeObject[];
  links: GraphLinkObject[];
}

export const emptyGraph: GraphData = { nodes: [], links: [] };

type Edge = { source: string | GraphNodeObject; target: string | GraphNodeObject } & Pick<
  GraphEdge,
  "relation"
>;

/** The id of a link's end, whichever form the layout has left it in. */
export function endId(end: string | GraphNodeObject): string {
  return typeof end === "string" ? end : end.id;
}

/**
 * One picture out of the root's payload and each expansion's: every node
 * once, by id, the first payload's version of it kept; every edge once.
 */
export function combine(payloads: readonly GraphOutput[]): {
  nodes: GraphNode[];
  edges: GraphEdge[];
} {
  const nodes = new Map<string, GraphNode>();
  const edges = new Map<string, GraphEdge>();
  for (const payload of payloads) {
    for (const node of payload.nodes) {
      if (!nodes.has(node.id)) nodes.set(node.id, node);
    }
    for (const edge of payload.edges) {
      edges.set(`${edge.source}>${edge.target}:${edge.relation}`, edge);
    }
  }
  // An edge whose end a later payload did not bring along has nothing to draw to.
  return {
    nodes: [...nodes.values()],
    edges: [...edges.values()].filter((edge) => nodes.has(edge.source) && nodes.has(edge.target)),
  };
}

/** The spread a new node starts at around the neighbour it settles beside. */
const SPAWN_SPREAD = 12;

/**
 * The canvas's next data. A node that stays keeps its object, and with it the
 * position the layout gave it, so a refetch settles the picture instead of
 * redrawing it; its fields are refreshed in place. A new node starts beside a
 * neighbour that already has a position, so it grows out of the picture
 * rather than flying in from the origin.
 */
export function withPositions(
  previous: GraphData,
  nodes: readonly GraphNode[],
  edges: readonly GraphEdge[],
): GraphData {
  const kept = new Map(previous.nodes.map((node) => [node.id, node]));
  const next = new Map<string, GraphNodeObject>();
  const fresh: GraphNodeObject[] = [];
  for (const node of nodes) {
    const existing = kept.get(node.id);
    if (existing) {
      next.set(node.id, Object.assign(existing, node));
    } else {
      const made: GraphNodeObject = { ...node };
      next.set(node.id, made);
      fresh.push(made);
    }
  }
  const links: GraphLinkObject[] = edges.map((edge) => ({
    source: edge.source,
    target: edge.target,
    relation: edge.relation,
  }));
  if (fresh.length > 0) {
    const beside = neighbours(edges);
    for (const node of fresh) {
      const anchor = [...(beside.get(node.id) ?? [])]
        .map((id) => next.get(id))
        .find((other) => other?.x !== undefined && other.y !== undefined);
      if (anchor?.x !== undefined && anchor.y !== undefined) {
        node.x = anchor.x + (Math.random() - 0.5) * SPAWN_SPREAD;
        node.y = anchor.y + (Math.random() - 0.5) * SPAWN_SPREAD;
      }
    }
  }
  return { nodes: [...next.values()], links };
}

/** Each node's neighbours, by id, either way along an edge. */
export function neighbours(
  edges: readonly { source: string | GraphNodeObject; target: string | GraphNodeObject }[],
): Map<string, Set<string>> {
  const map = new Map<string, Set<string>>();
  const add = (from: string, to: string) => {
    let set = map.get(from);
    if (!set) {
      set = new Set();
      map.set(from, set);
    }
    set.add(to);
  };
  for (const edge of edges) {
    const source = endId(edge.source);
    const target = endId(edge.target);
    add(source, target);
    add(target, source);
  }
  return map;
}

// --- The rings ---

/** How far apart two rings are at least, in graph units. */
export const RING_GAP = 110;
/** How much of a ring's circumference each node on it gets. */
const RING_SPACING = 18;

/**
 * The ring each node sits on: a place's depth below the root, an institution
 * half a step out from its place, a page a little further, a domain just past
 * its pages. The layout pulls each node to its ring, so the picture reads as
 * the hierarchy it is: the root in the middle, each level a ring around it.
 * A node with no path to the root gets no ring and settles where the links
 * leave it.
 */
export function rings(
  rootId: string | undefined,
  nodes: readonly GraphNode[],
  edges: readonly Edge[],
): Map<string, number> {
  const ring = new Map<string, number>();
  if (rootId === undefined) return ring;
  const kind = new Map(nodes.map((node) => [node.id, node.kind]));
  const children = new Map<string, string[]>();
  const placeOf = new Map<string, string>();
  const parentBody = new Map<string, string>();
  const ownerOf = new Map<string, string>();
  const pagesOf = new Map<string, string[]>();
  for (const edge of edges) {
    const source = endId(edge.source);
    const target = endId(edge.target);
    switch (edge.relation) {
      case "parent":
        if (kind.get(source) === "place") {
          children.set(target, [...(children.get(target) ?? []), source]);
        } else {
          parentBody.set(source, target);
        }
        break;
      case "government":
        placeOf.set(target, source);
        break;
      case "place":
        placeOf.set(source, target);
        break;
      case "homepage":
      case "source":
        ownerOf.set(source, target);
        break;
      case "domain":
        pagesOf.set(target, [...(pagesOf.get(target) ?? []), source]);
        break;
      case "serves":
        break;
    }
  }
  if (kind.get(rootId) === "place") {
    const queue = [rootId];
    ring.set(rootId, 0);
    for (let i = 0; i < queue.length; i++) {
      const id = queue[i]!;
      const depth = ring.get(id)!;
      for (const child of children.get(id) ?? []) {
        if (ring.has(child)) continue;
        ring.set(child, depth + 1);
        queue.push(child);
      }
    }
  }
  for (const node of nodes) {
    if (node.kind !== "institution") continue;
    const place = placeOf.get(node.id);
    const placeRing = place === undefined ? undefined : ring.get(place);
    if (placeRing !== undefined) ring.set(node.id, placeRing + 0.5);
    else if (node.id === rootId) ring.set(node.id, 0);
  }
  for (const node of nodes) {
    if (node.kind !== "institution" || ring.has(node.id)) continue;
    const above = parentBody.get(node.id);
    const aboveRing = above === undefined ? undefined : ring.get(above);
    if (aboveRing !== undefined) ring.set(node.id, aboveRing + 0.1);
  }
  for (const node of nodes) {
    if (node.kind !== "homepage" && node.kind !== "source") continue;
    const owner = ownerOf.get(node.id);
    const ownerRing = owner === undefined ? undefined : ring.get(owner);
    if (ownerRing !== undefined) ring.set(node.id, ownerRing + 0.3);
  }
  for (const node of nodes) {
    if (node.kind !== "domain") continue;
    const pages = (pagesOf.get(node.id) ?? [])
      .map((id) => ring.get(id))
      .filter((value) => value !== undefined);
    if (pages.length > 0) ring.set(node.id, Math.max(...pages) + 0.15);
  }
  return ring;
}

/**
 * The radius of each whole ring: far enough out from the one before to be
 * read as its own, and long enough around for everything on it. Index by the
 * ring's whole part; the last entry stands for everything beyond.
 */
export function ringRadii(ring: ReadonlyMap<string, number>): number[] {
  const counts: number[] = [];
  for (const value of ring.values()) {
    const band = Math.floor(value);
    counts[band] = (counts[band] ?? 0) + 1;
  }
  const radii = [0];
  for (let band = 1; band < counts.length; band++) {
    const needed = ((counts[band] ?? 0) * RING_SPACING) / (2 * Math.PI);
    radii.push(Math.max(radii[band - 1]! + RING_GAP, needed));
  }
  return radii;
}

/** How far out from its place's ring a node a whole step out sits, in graph units. */
export const RING_OUTSET = 60;

/**
 * Where a ring lies: a whole ring at its radius, and a fraction of a ring a
 * fixed distance out from it, so an institution sits just beside its place
 * however far the next ring is.
 */
export function ringRadius(radii: readonly number[], ring: number): number {
  const band = Math.floor(ring);
  const inner = radii[band] ?? (radii.at(-1) ?? 0) + (band - radii.length + 1) * RING_GAP;
  return inner + (ring - band) * RING_OUTSET;
}

// --- The overlays ---

/**
 * A node's coverage: whether it has what the atlas is after. A place is
 * covered by a government with a verified homepage, partly by a government
 * without one; an institution by a verified homepage, partly by a claim
 * awaiting review. The web has no coverage of its own.
 */
export type Coverage = "covered" | "partial" | "missing";

export const coverageLabels: Record<Coverage, string> = {
  covered: "Covered",
  partial: "Partial",
  missing: "Missing",
};

export function coverage(node: GraphNode): Coverage | null {
  switch (node.kind) {
    case "place":
      return node.online ? "covered" : node.governed ? "partial" : "missing";
    case "institution":
      return node.has_homepage ? "covered" : (node.homepage_count ?? 0) > 0 ? "partial" : "missing";
    default:
      return null;
  }
}

/**
 * The domains that pages of more than one institution sit on, each with those
 * institutions: the one thing a graph shows that a table cannot.
 */
export function sharedDomains(
  nodes: readonly GraphNode[],
  edges: readonly Edge[],
): Map<string, Set<string>> {
  const ownerOf = new Map<string, string>();
  const domainOf = new Map<string, string>();
  for (const edge of edges) {
    const source = endId(edge.source);
    const target = endId(edge.target);
    if (edge.relation === "homepage" || edge.relation === "source") ownerOf.set(source, target);
    if (edge.relation === "domain") domainOf.set(source, target);
  }
  const served = new Map<string, Set<string>>();
  for (const node of nodes) {
    if (node.kind !== "homepage" && node.kind !== "source") continue;
    const owner = ownerOf.get(node.id);
    const domain = domainOf.get(node.id);
    if (owner === undefined || domain === undefined) continue;
    served.set(domain, (served.get(domain) ?? new Set()).add(owner));
  }
  return new Map([...served].filter(([, owners]) => owners.size > 1));
}

/** The nodes the shared-domains overlay lights: the domains, their institutions and the pages between. */
export function sharedDomainEmphasis(
  shared: ReadonlyMap<string, Set<string>>,
  edges: readonly Edge[],
): Set<string> {
  const lit = new Set<string>();
  for (const [domain, owners] of shared) {
    lit.add(domain);
    for (const owner of owners) lit.add(owner);
  }
  for (const edge of edges) {
    if (edge.relation === "domain" && lit.has(endId(edge.target))) lit.add(endId(edge.source));
  }
  return lit;
}

// --- The panel ---

export interface Connection {
  label: string;
  nodes: GraphNode[];
}

/** What each relation is called from each end: the panel's headings, in its order. */
const connectionLabels: Record<
  EntityKind,
  [relation: GraphEdge["relation"], out: boolean, label: string][]
> = {
  place: [
    ["parent", true, "Parent place"],
    ["parent", false, "Places within"],
    ["government", true, "Government"],
    ["place", false, "Institutions"],
    ["serves", false, "Served by"],
  ],
  institution: [
    ["place", true, "Place"],
    ["government", false, "Governs"],
    ["parent", true, "Parent body"],
    ["parent", false, "Child bodies"],
    ["homepage", false, "Homepage"],
    ["source", false, "Sources"],
    ["serves", true, "Serves"],
  ],
  homepage: [
    ["homepage", true, "Institution"],
    ["domain", true, "Domain"],
  ],
  source: [
    ["source", true, "Institution"],
    ["domain", true, "Domain"],
  ],
  domain: [["domain", false, "Pages"]],
};

/** A node's neighbours, grouped by what they are to it, in the panel's order. */
export function connections(
  node: GraphNode,
  byId: ReadonlyMap<string, GraphNode>,
  edges: readonly Edge[],
): Connection[] {
  const groups = new Map<string, GraphNode[]>();
  for (const edge of edges) {
    const source = endId(edge.source);
    const target = endId(edge.target);
    const out = source === node.id;
    if (!out && target !== node.id) continue;
    const other = byId.get(out ? target : source);
    if (!other) continue;
    const key = `${edge.relation}:${out ? "out" : "in"}`;
    groups.set(key, [...(groups.get(key) ?? []), other]);
  }
  const named = connectionLabels[node.kind].flatMap(([relation, out, label]) => {
    const nodes = groups.get(`${relation}:${out ? "out" : "in"}`);
    return nodes ? [{ label, nodes: nodes.toSorted(byLabel) }] : [];
  });
  return named;
}

function byLabel(a: GraphNode, b: GraphNode): number {
  return a.label.localeCompare(b.label);
}

// --- The drawing ---

/**
 * The radius a node is drawn with, in graph units: a place grows with its
 * population and an institution with its sources, on a log and a square root
 * so a capital and a hamlet both fit; the web is small and even.
 */
export function nodeRadius(node: GraphNode): number {
  switch (node.kind) {
    case "place":
      return 4 + 1.3 * Math.log10(1 + (node.population ?? 0));
    case "institution":
      return 3 + 0.8 * Math.sqrt(node.source_count ?? 0);
    case "domain":
      return 2.6;
    case "homepage":
      return 2.2;
    case "source":
      return 1.8;
  }
}

const LABEL_LENGTH = 40;

/** What a node is called on the canvas: a URL without its scheme and `www.`, cut short. */
export function shortLabel(node: GraphNode): string {
  const label =
    node.kind === "homepage" || node.kind === "source"
      ? node.label.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")
      : node.label;
  return label.length > LABEL_LENGTH ? `${label.slice(0, LABEL_LENGTH - 1)}…` : label;
}
