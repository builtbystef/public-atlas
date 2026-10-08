import type {
  AssignmentType,
  EvalEntry,
  EvalScoreOutput,
  GateOutput,
} from "@public-atlas/api-client";

import { assignmentTypes } from "@/lib/labels";

import type { SubjectSort } from "./schemas";

/**
 * The arithmetic behind an eval run's page: its scores pivoted to a row per
 * subject, ordered and filtered, set against the run it is compared with,
 * and one score's entries taken apart by kind, bucket and group.
 */

type ByType<T> = Partial<Record<AssignmentType, T>>;

/** Each assignment type's recall floor: the gate on it, when there is one. */
export function floorsByType(gates: readonly GateOutput[]): ByType<number> {
  const floors: ByType<number> = {};
  for (const gate of gates) floors[gate.assignment_type] ??= gate.floor;
  return floors;
}

/** One subject's scores on each type it was judged on, and the compared run's. */
export interface SubjectRow {
  subject: string;
  scores: ByType<EvalScoreOutput>;
  baseline: ByType<EvalScoreOutput>;
}

export function subjectRows(
  scores: readonly EvalScoreOutput[],
  baseline: readonly EvalScoreOutput[] = [],
): SubjectRow[] {
  const rows = new Map<string, SubjectRow>();
  for (const score of scores) {
    const row = rows.get(score.subject) ?? { subject: score.subject, scores: {}, baseline: {} };
    row.scores[score.assignment_type] = score;
    rows.set(score.subject, row);
  }
  for (const score of baseline) {
    const row = rows.get(score.subject);
    if (row) row.baseline[score.assignment_type] = score;
  }
  return [...rows.values()];
}

/** `value - before`, or null unless both are numbers. */
export function change(
  value: number | null | undefined,
  before: number | null | undefined,
): number | null {
  if (value === null || value === undefined || before === null || before === undefined) {
    return null;
  }
  return value - before;
}

/** The subject's lowest recall on any type; null when no recall was judged. */
export function lowestRecall(row: SubjectRow): number | null {
  const recalls = assignmentTypes
    .map((type) => row.scores[type]?.recall)
    .filter((recall): recall is number => typeof recall === "number");
  return recalls.length ? Math.min(...recalls) : null;
}

/** The subject's largest fall (or smallest rise) in recall since the compared run. */
export function recallChange(row: SubjectRow): number | null {
  const changes = assignmentTypes
    .map((type) => change(row.scores[type]?.recall, row.baseline[type]?.recall))
    .filter((value): value is number => value !== null);
  return changes.length ? Math.min(...changes) : null;
}

/** Whether any of the subject's recalls is under its type's floor. */
export function isBelowTarget(row: SubjectRow, floors: ByType<number>): boolean {
  return assignmentTypes.some((type) => {
    const recall = row.scores[type]?.recall;
    const floor = floors[type];
    return typeof recall === "number" && floor !== undefined && recall < floor;
  });
}

/** The rows in `sort` order, worst first; a subject with nothing to sort by goes last. */
export function sortRows(rows: readonly SubjectRow[], sort: SubjectSort): SubjectRow[] {
  const key = (row: SubjectRow): number | null => {
    if (sort === "lowest") return lowestRecall(row);
    if (sort === "change") return recallChange(row);
    if (sort === "subject") return null;
    return row.scores[sort]?.recall ?? null;
  };
  return [...rows].sort((a, b) => {
    const [x, y] = [key(a), key(b)];
    if (x !== y) {
      if (x === null) return 1;
      if (y === null) return -1;
      return x - y;
    }
    return a.subject.localeCompare(b.subject);
  });
}

/** How many entries back a score: hits are null on scores recorded before they were kept. */
export interface ScoreCounts {
  hits: number | null;
  misses: number;
  falsePositives: number;
}

export function scoreCounts(score: EvalScoreOutput): ScoreCounts {
  return {
    hits: score.hits?.length ?? null,
    misses: score.misses.length,
    falsePositives: score.false_positives.length,
  };
}

/** One group of a score (an institution or source type, `parent`, `homepage`, `domain`). */
export interface GroupStat {
  group: string;
  hits: number;
  misses: number;
}

/** Hits and misses by group, worst recall first; null when the score kept no hits. */
export function groupStats(score: EvalScoreOutput): GroupStat[] | null {
  if (score.hits === null) return null;
  const groups = new Map<string, GroupStat>();
  const tally = (entry: EvalEntry, key: "hits" | "misses") => {
    if (!entry.group) return;
    const stat = groups.get(entry.group) ?? { group: entry.group, hits: 0, misses: 0 };
    stat[key] += 1;
    groups.set(entry.group, stat);
  };
  for (const entry of score.hits) tally(entry, "hits");
  for (const entry of score.misses) tally(entry, "misses");
  const recall = (stat: GroupStat) => stat.hits / (stat.hits + stat.misses);
  return [...groups.values()].sort(
    (a, b) => recall(a) - recall(b) || a.group.localeCompare(b.group),
  );
}

/**
 * A score's entries as the side panel lists them. A `wrong` entry is in
 * both the misses and the false positives; it is listed once, on its own.
 */
export function entriesByKind(score: EvalScoreOutput) {
  return {
    missed: score.misses.filter((entry) => entry.kind === "miss"),
    wrong: score.misses.filter((entry) => entry.kind === "wrong"),
    falsePositives: score.false_positives.filter((entry) => entry.kind === "false_positive"),
    found: score.hits ?? [],
  };
}

/** Entries in the order of their buckets, most first, each bucket with its entries. */
export function byBucket(entries: readonly EvalEntry[]): [string, EvalEntry[]][] {
  const buckets = new Map<string, EvalEntry[]>();
  for (const entry of entries) {
    const list = buckets.get(entry.bucket) ?? [];
    list.push(entry);
    buckets.set(entry.bucket, list);
  }
  return [...buckets.entries()].sort(([a, x], [b, y]) => y.length - x.length || a.localeCompare(b));
}

/**
 * The lines among `entries` that the compared score did not have: what this
 * run newly got wrong. Null without a compared score to tell by.
 */
export function newLines(
  entries: readonly EvalEntry[],
  before: readonly EvalEntry[] | undefined,
): Set<string> | null {
  if (before === undefined) return null;
  const seen = new Set(before.map((entry) => entry.line));
  return new Set(entries.filter((entry) => !seen.has(entry.line)).map((entry) => entry.line));
}

const URL_PATTERN = /https?:\/\/[^\s,;()<>]+/g;

/** A scorer's line cut into text and the URLs in it, so the URLs can be links. */
export function splitUrls(line: string): { text: string; href?: string }[] {
  const parts: { text: string; href?: string }[] = [];
  let last = 0;
  for (const match of line.matchAll(URL_PATTERN)) {
    // A sentence's full stop is not part of the URL before it.
    const href = match[0].replace(/[.:]+$/, "");
    const start = match.index;
    if (start > last) parts.push({ text: line.slice(last, start) });
    parts.push({ text: href, href });
    last = start + href.length;
  }
  if (last < line.length) parts.push({ text: line.slice(last) });
  return parts;
}
