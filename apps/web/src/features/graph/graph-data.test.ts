import type { GraphNode, GraphOutput } from "@public-atlas/api-client";
import { expect, test } from "vite-plus/test";

import {
  combine,
  emptyGraph,
  kindsParam,
  neighbours,
  nodeRadius,
  parseKinds,
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
    truncated: true,
    nodes: [place("elm"), place("oakville"), institution("county")],
    edges: [
      { source: "oakville", target: "elm", relation: "parent" },
      { source: "elm", target: "county", relation: "government" },
    ],
  };
  const expansion: GraphOutput = {
    root_id: "oakville",
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

test("the kinds in the URL are the chosen ones, or every kind", () => {
  expect(parseKinds(undefined)).toEqual(["place", "institution", "homepage", "source", "domain"]);
  expect(parseKinds("domain,place,bogus")).toEqual(["place", "domain"]);
  expect(parseKinds("bogus")).toHaveLength(5);
  expect(kindsParam(["domain", "place"])).toBe("place,domain");
  expect(kindsParam(["source", "homepage", "place", "domain", "institution"])).toBeUndefined();
});
