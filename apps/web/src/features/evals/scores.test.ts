import type { AssignmentType, EvalEntry, EvalScoreOutput } from "@public-atlas/api-client";
import { expect, test } from "vite-plus/test";

import { parseEvalRunSearch } from "./schemas";
import {
  byBucket,
  entriesByKind,
  floorsByType,
  groupStats,
  isBelowTarget,
  newLines,
  recallChange,
  sortRows,
  splitUrls,
  subjectRows,
} from "./scores";

function entry(kind: EvalEntry["kind"], line: string, bucket = "b", group: string | null = null) {
  return { kind, line, bucket, group };
}

function score(
  subject: string,
  assignment_type: AssignmentType,
  recall: number | null,
  extra: Partial<EvalScoreOutput> = {},
): EvalScoreOutput {
  return {
    id: `${subject}-${assignment_type}`,
    subject,
    assignment_type,
    recall,
    precision: null,
    hits: [],
    misses: [],
    false_positives: [],
    ...extra,
  };
}

test("scores pivot to a row per subject beside the compared run's", () => {
  const rows = subjectRows(
    [score("ottawa", "find_sources", 0.5), score("ottawa", "find_homepage", 1)],
    [score("ottawa", "find_sources", 0.75), score("gone", "find_sources", 1)],
  );
  expect(rows).toHaveLength(1);
  expect(rows[0]!.scores.find_homepage?.recall).toBe(1);
  expect(rows[0]!.baseline.find_sources?.recall).toBe(0.75);
  expect(recallChange(rows[0]!)).toBe(-0.25);
});

test("rows sort worst first, with nothing to sort by last", () => {
  const rows = subjectRows([
    score("a", "find_sources", 0.9),
    score("b", "find_sources", 0.2),
    score("c", "find_sources", null),
    score("c", "find_homepage", 0.5),
  ]);
  expect(sortRows(rows, "lowest").map((row) => row.subject)).toEqual(["b", "c", "a"]);
  expect(sortRows(rows, "find_sources").map((row) => row.subject)).toEqual(["b", "a", "c"]);
  expect(sortRows(rows, "subject").map((row) => row.subject)).toEqual(["a", "b", "c"]);
});

test("a subject is below target when a recall is under its type's gate", () => {
  const floors = floorsByType([
    {
      name: "sources",
      assignment_type: "find_sources",
      what: "",
      floor: 0.9,
      hits: null,
      misses: null,
      recall: null,
      verdict: null,
    },
  ]);
  const [low, high] = subjectRows([
    score("low", "find_sources", 0.85),
    score("high", "find_sources", 0.95),
  ]);
  expect(isBelowTarget(low!, floors)).toBe(true);
  expect(isBelowTarget(high!, floors)).toBe(false);
});

test("a wrong entry is listed once, apart from the plain misses", () => {
  const wrong = entry("wrong", "saved x, expected y");
  const kinds = entriesByKind(
    score("s", "find_homepage", 0, {
      misses: [entry("miss", "not found"), wrong],
      false_positives: [wrong, entry("false_positive", "out of scope")],
    }),
  );
  expect(kinds.missed.map((e) => e.line)).toEqual(["not found"]);
  expect(kinds.wrong).toEqual([wrong]);
  expect(kinds.falsePositives.map((e) => e.line)).toEqual(["out of scope"]);
});

test("groups count hits and misses, worst recall first, and need the hits", () => {
  const stats = groupStats(
    score("s", "find_sources", 0.5, {
      hits: [entry("hit", "1", "found", "budget"), entry("hit", "2", "found", "minutes")],
      misses: [entry("miss", "3", "not found", "budget"), entry("wrong", "4", "w", "budget")],
    }),
  );
  expect(stats).toEqual([
    { group: "budget", hits: 1, misses: 2 },
    { group: "minutes", hits: 1, misses: 0 },
  ]);
  expect(groupStats(score("s", "find_sources", 0.5, { hits: null }))).toBeNull();
});

test("buckets come largest first", () => {
  const buckets = byBucket([
    entry("miss", "1", "x"),
    entry("miss", "2", "y"),
    entry("miss", "3", "y"),
  ]);
  expect(buckets.map(([bucket, list]) => [bucket, list.length])).toEqual([
    ["y", 2],
    ["x", 1],
  ]);
});

test("new lines are those the compared score did not have", () => {
  const now = [entry("miss", "a"), entry("miss", "b")];
  expect(newLines(now, [entry("miss", "a")])).toEqual(new Set(["b"]));
  expect(newLines(now, undefined)).toBeNull();
});

test("the URLs in a line become links, without the punctuation after them", () => {
  expect(splitUrls("Budget: saved https://a.ca/x, expected https://b.ca/y.")).toEqual([
    { text: "Budget: saved " },
    { text: "https://a.ca/x", href: "https://a.ca/x" },
    { text: ", expected " },
    { text: "https://b.ca/y", href: "https://b.ca/y" },
    { text: "." },
  ]);
  expect(splitUrls("no links")).toEqual([{ text: "no links" }]);
});

test("the page's search keeps what it knows and drops the rest", () => {
  expect(
    parseEvalRunSearch({
      compare: "none",
      sort: "find_sources",
      below: "1",
      subject: "ottawa",
      type: "nope",
    }),
  ).toEqual({ compare: "none", sort: "find_sources", below: "1", subject: "ottawa" });
  expect(parseEvalRunSearch({ compare: "not-a-uuid" })).toEqual({});
});
