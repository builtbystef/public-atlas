import type { GraphNode, GraphOutput } from "@public-atlas/api-client";
import { expect, test } from "vite-plus/test";

import {
  combine,
  connections,
  coverage,
  emptyGraph,
  neighbours,
  nodeRadius,
  RING_GAP,
  RING_OUTSET,
  ringRadii,
  ringRadius,
  rings,
  sharedDomainEmphasis,
  sharedDomains,
  shortLabel,
  withPositions,
} from "./graph-data";

const place = (id: string, population: number | null = null): GraphNode => ({
  id,
  kind: "place",
  label: id,
  status: "verified",
  population,
});
const institution = (id: string, source_count = 0): GraphNode => ({
  id,
  kind: "institution",
  label: id,
  status: "verified",
  source_count,
});

test("payloads fold into one picture, the first version of a node kept", () => {
  const root: GraphOutput = {
    root_id: "elm",
    ancestors: [],
    truncated: true,
    nodes: [place("elm"), place("oakville"), institution("county")],
    edges: [
      { source: "oakville", target: "elm", relation: "parent" },
      { source: "elm", target: "county", relation: "government" },
    ],
  };
  const expansion: GraphOutput = {
    root_id: "oakville",
    ancestors: [{ id: "elm", label: "elm" }],
    truncated: false,
    nodes: [{ ...place("oakville"), status: "candidate" }, institution("library", 2)],
    edges: [
      { source: "library", target: "oakville", relation: "place" },
      { source: "elm", target: "county", relation: "government" },
      // An end the expansion did not bring along.
      { source: "library", target: "town", relation: "parent" },
    ],
  };
  const picture = combine([root, expansion]);
  expect(picture.nodes.map((node) => node.id)).toEqual(["elm", "oakville", "county", "library"]);
  expect(picture.nodes[1]?.status).toBe("verified");
  expect(picture.edges).toEqual([
    { source: "oakville", target: "elm", relation: "parent" },
    { source: "elm", target: "county", relation: "government" },
    { source: "library", target: "oakville", relation: "place" },
  ]);
});

test("a refetch keeps the objects, and so the positions, of the nodes that stay", () => {
  const first = withPositions(
    emptyGraph,
    [place("elm"), place("oakville")],
    [{ source: "oakville", target: "elm", relation: "parent" }],
  );
  const elm = first.nodes[0]!;
  elm.x = 10;
  elm.y = 20;
  const second = withPositions(
    first,
    [{ ...place("elm", 5000) }, institution("county")],
    [{ source: "elm", target: "county", relation: "government" }],
  );
  expect(second.nodes[0]).toBe(elm);
  expect(elm).toMatchObject({ x: 10, y: 20, population: 5000 });
  expect(second.nodes.map((node) => node.id)).toEqual(["elm", "county"]);
  expect(second.links).toEqual([{ source: "elm", target: "county", relation: "government" }]);
});

test("a new node starts beside a neighbour that has a position", () => {
  const first = withPositions(emptyGraph, [place("elm")], []);
  first.nodes[0]!.x = 100;
  first.nodes[0]!.y = -50;
  const second = withPositions(
    first,
    [place("elm"), institution("county"), institution("far")],
    [{ source: "elm", target: "county", relation: "government" }],
  );
  const county = second.nodes.find((node) => node.id === "county")!;
  expect(Math.abs(county.x! - 100)).toBeLessThan(10);
  expect(Math.abs(county.y! + 50)).toBeLessThan(10);
  // Without a placed neighbour, the layout chooses.
  expect(second.nodes.find((node) => node.id === "far")?.x).toBeUndefined();
});

test("neighbours run either way along an edge, whichever form its ends are in", () => {
  const map = neighbours([
    { source: "a", target: "b" },
    { source: { id: "b", kind: "place", label: "b", status: "verified" }, target: "c" },
  ]);
  expect([...map.get("b")!]).toEqual(["a", "c"]);
  expect([...map.get("c")!]).toEqual(["b"]);
});

test("places grow with population, institutions with sources, and the web stays small", () => {
  expect(nodeRadius(place("p"))).toBe(4);
  expect(nodeRadius(place("p", 999_999))).toBeCloseTo(11.8, 1);
  expect(nodeRadius(institution("i"))).toBe(3);
  expect(nodeRadius(institution("i", 9))).toBeCloseTo(5.4, 1);
  expect(nodeRadius({ id: "s", kind: "source", label: "", status: "verified" })).toBeLessThan(
    nodeRadius({ id: "d", kind: "domain", label: "", status: "verified" }),
  );
});

test("a URL is labelled without its scheme, and a long label is cut short", () => {
  expect(
    shortLabel({
      id: "h",
      kind: "homepage",
      label: "https://www.elmcounty.ca/",
      status: "verified",
    }),
  ).toBe("elmcounty.ca");
  expect(
    shortLabel({
      id: "s",
      kind: "source",
      label: `https://elmcounty.ca/${"a".repeat(60)}`,
      status: "verified",
    }),
  ).toHaveLength(40);
  expect(shortLabel(place("Elm"))).toBe("Elm");
});

const web = (id: string, kind: "homepage" | "source" | "domain"): GraphNode => ({
  id,
  kind,
  label: id,
  status: "verified",
});

// A region with two municipalities; the county's homepage and a source on its domain; a library
// in one town whose claim sits on the same domain.
const picture = {
  nodes: [
    place("elm"),
    place("oakville"),
    place("milton"),
    institution("county", 1),
    institution("town"),
    institution("library"),
    web("county-home", "homepage"),
    web("tenders", "source"),
    web("library-home", "homepage"),
    web("elmcounty.ca", "domain"),
  ],
  edges: [
    { source: "oakville", target: "elm", relation: "parent" },
    { source: "milton", target: "elm", relation: "parent" },
    { source: "elm", target: "county", relation: "government" },
    { source: "oakville", target: "town", relation: "government" },
    { source: "library", target: "oakville", relation: "place" },
    { source: "library", target: "town", relation: "parent" },
    { source: "library", target: "milton", relation: "serves" },
    { source: "county-home", target: "county", relation: "homepage" },
    { source: "tenders", target: "county", relation: "source" },
    { source: "library-home", target: "library", relation: "homepage" },
    { source: "county-home", target: "elmcounty.ca", relation: "domain" },
    { source: "tenders", target: "elmcounty.ca", relation: "domain" },
    { source: "library-home", target: "elmcounty.ca", relation: "domain" },
  ],
} satisfies { nodes: GraphNode[]; edges: GraphOutput["edges"] };

test("each node sits on a ring by its depth, institutions and pages a step out from their place", () => {
  const ring = rings("elm", picture.nodes, picture.edges);
  expect(ring.get("elm")).toBe(0);
  expect(ring.get("oakville")).toBe(1);
  expect(ring.get("county")).toBe(0.5);
  expect(ring.get("library")).toBe(1.5);
  expect(ring.get("county-home")).toBeCloseTo(0.8);
  expect(ring.get("library-home")).toBeCloseTo(1.8);
  expect(ring.get("elmcounty.ca")).toBeCloseTo(1.95);
  // Nothing without a root, or on a node with no path to it.
  expect(rings(undefined, picture.nodes, picture.edges).size).toBe(0);
  expect(rings("elm", [...picture.nodes, place("far")], picture.edges).has("far")).toBe(false);
});

test("the rings are far enough apart, and long enough around for what is on them", () => {
  const few = ringRadii(
    new Map([
      ["a", 0],
      ["b", 1],
      ["c", 1.5],
    ]),
  );
  expect(few).toEqual([0, RING_GAP]);
  const many = new Map<string, number>([["root", 0]]);
  for (let i = 0; i < 400; i++) many.set(`n${i}`, 1);
  const [, crowded] = ringRadii(many);
  expect(crowded).toBeGreaterThan(RING_GAP * 5);
  expect(ringRadius([0, 100], 0.5)).toBe(RING_OUTSET / 2);
  expect(ringRadius([0, 100], 1.5)).toBe(100 + RING_OUTSET / 2);
  expect(ringRadius([0, 100], 3)).toBe(100 + 2 * RING_GAP);
});

test("coverage reads a government online, or a homepage, as covered", () => {
  expect(coverage({ ...place("p"), governed: true, online: true })).toBe("covered");
  expect(coverage({ ...place("p"), governed: true, online: false })).toBe("partial");
  expect(coverage({ ...place("p"), governed: false, online: false })).toBe("missing");
  expect(coverage({ ...institution("i"), has_homepage: true })).toBe("covered");
  expect(coverage({ ...institution("i"), has_homepage: false, homepage_count: 1 })).toBe("partial");
  expect(coverage({ ...institution("i"), has_homepage: false, homepage_count: 0 })).toBe("missing");
  expect(coverage(web("d", "domain"))).toBeNull();
});

test("a shared domain is one with pages of more than one institution", () => {
  const shared = sharedDomains(picture.nodes, picture.edges);
  expect([...shared.keys()]).toEqual(["elmcounty.ca"]);
  expect([...shared.get("elmcounty.ca")!]).toEqual(["county", "library"]);
  expect([...sharedDomainEmphasis(shared, picture.edges)].toSorted()).toEqual([
    "county",
    "county-home",
    "elmcounty.ca",
    "library",
    "library-home",
    "tenders",
  ]);
  const alone = sharedDomains(
    picture.nodes,
    picture.edges.filter((edge) => edge.source !== "library-home"),
  );
  expect(alone.size).toBe(0);
});

test("a node's connections are grouped by what they are to it", () => {
  const byId = new Map(picture.nodes.map((node) => [node.id, node]));
  const county = connections(byId.get("county")!, byId, picture.edges);
  expect(county.map((group) => [group.label, group.nodes.map((node) => node.id)])).toEqual([
    ["Governs", ["elm"]],
    ["Homepage", ["county-home"]],
    ["Sources", ["tenders"]],
  ]);
  const oakville = connections(byId.get("oakville")!, byId, picture.edges);
  expect(oakville.map((group) => group.label)).toEqual([
    "Parent place",
    "Government",
    "Institutions",
  ]);
  const library = connections(byId.get("library")!, byId, picture.edges);
  expect(library.map((group) => group.label)).toEqual([
    "Place",
    "Parent body",
    "Homepage",
    "Serves",
  ]);
  const domain = connections(byId.get("elmcounty.ca")!, byId, picture.edges);
  expect(domain[0]?.nodes.map((node) => node.id)).toEqual([
    "county-home",
    "library-home",
    "tenders",
  ]);
});
