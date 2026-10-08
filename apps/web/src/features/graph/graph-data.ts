import type { EntityKind, GraphEdge, GraphNode, GraphOutput } from "@public-atlas/api-client";

/**
 * The graph view's data, between the API's payloads and the canvas: several
 * payloads folded into one picture, node objects kept across refetches so
 * the layout keeps its positions, and the figures the drawing follows.
 */

/** The kinds in the order the legend shows them: the hierarchy first, then the web. */
export const graphKinds = [
  "place",
  "institution",
  "homepage",
  "source",
  "domain",
] as const satisfies readonly EntityKind[];

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

/** The kinds a URL's `kinds` names, or every kind when it names none. */
export function parseKinds(text: string | undefined): EntityKind[] {
  if (!text) return [...graphKinds];
  const named = new Set(text.split(","));
  const kinds = graphKinds.filter((kind) => named.has(kind));
  return kinds.length > 0 ? kinds : [...graphKinds];
}

/** The `kinds` a URL carries for a choice: nothing when every kind is chosen. */
export function kindsParam(kinds: readonly EntityKind[]): string | undefined {
  const chosen = graphKinds.filter((kind) => kinds.includes(kind));
  return chosen.length === graphKinds.length ? undefined : chosen.join(",");
}
