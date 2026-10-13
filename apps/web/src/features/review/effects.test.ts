import type {
  DecisionPreviewOutput,
  EntityKind,
  EntityStatus,
  PlannedOutput,
} from "@public-atlas/api-client";
import { expect, test } from "vite-plus/test";

import { describeEffects, spawnSummary } from "./effects";

const ref = (label: string, entity_kind: EntityKind = "institution") => ({
  id: label,
  entity_kind,
  label,
});

const change = (label: string, after: EntityStatus, kind?: EntityKind) => ({
  entity: ref(label, kind),
  before: "needs_review" as const,
  after,
});

const planned = (
  type: PlannedOutput["type"],
  label: string,
  skipped: PlannedOutput["skipped"] = null,
): PlannedOutput => ({ type, subject: ref(label), skipped });

function preview(overrides: Partial<DecisionPreviewOutput>): DecisionPreviewOutput {
  return { changes: [], spawn: [], run: { id: "r", name: "Ontario" }, ...overrides };
}

test("an approval reads as what it verifies and the work it starts", () => {
  expect(
    describeEffects(
      preview({
        changes: [
          change("oakville.ca", "verified", "domain"),
          change("https://www.oakville.ca/", "verified", "homepage"),
        ],
        spawn: [
          planned("find_sources", "Town of Oakville"),
          planned("find_institutions", "Oakville", "already_open"),
        ],
      }),
    ),
  ).toEqual({
    changes: [
      "oakville.ca becomes a trusted domain",
      "https://www.oakville.ca/ becomes a verified homepage",
    ],
    starts: ["Find sources for Town of Oakville"],
    held: ["Find institutions for Oakville is under way already"],
  });
});

test("many of one kind read as a count", () => {
  const names = ["A", "B", "C", "D"];
  expect(
    describeEffects(
      preview({
        changes: names.map((name) => change(name, "verified")),
        spawn: names.map((name) => planned("find_homepage", name, "no_run")),
      }),
    ),
  ).toEqual({
    changes: ["4 institutions become verified"],
    starts: [],
    held: [
      "Find homepage for 4 institutions waits for the next run of the country, since none is going",
    ],
  });
});

test("the entity a merge folds away reads as merged", () => {
  expect(
    describeEffects(preview({ changes: [change("Oak Library", "rejected")] }), {
      id: "Oak Library",
      into: "Oakville Public Library",
    }).changes,
  ).toEqual(["Oak Library is merged into Oakville Public Library"]);
});

test("work the run's filter or a stopped run keeps out is listed as held, with its reason", () => {
  expect(
    describeEffects(
      preview({
        spawn: [
          planned("find_homepage", "Elm Library", "out_of_scope"),
          planned("find_sources", "Elm Library", "run_stopped"),
          planned("find_sources", "Oak Library", "run_stopped"),
          planned("find_homepage", "Oak Library"),
        ],
      }),
    ),
  ).toEqual({
    changes: [],
    starts: ["Find homepage for Oak Library"],
    held: [
      "Find homepage for Elm Library is outside the run's filter, so it won't start",
      "Find sources for Elm Library won't start, since the run is stopped",
      "Find sources for Oak Library won't start, since the run is stopped",
    ],
  });
});

test("rejections, reviews and reverted candidates each read in their own words", () => {
  expect(
    describeEffects(
      preview({
        changes: [
          change("Elm Library", "rejected"),
          change("elm.ca", "needs_review", "domain"),
          change("Oak Library", "candidate"),
        ],
      }),
    ).changes,
  ).toEqual([
    "Elm Library is rejected",
    "elm.ca goes to review",
    "Oak Library becomes a candidate again",
  ]);
});

test("more than three of one kind read as a count only when verified or rejected", () => {
  const names = ["A", "B", "C", "D"];
  expect(
    describeEffects(
      preview({
        changes: [
          ...names.map((name) => change(name, "rejected")),
          ...names.map((name) => change(`${name}.ca`, "verified", "domain")),
          ...names.map((name) => change(`${name}-review`, "needs_review")),
        ],
      }),
    ).changes,
  ).toEqual([
    "4 institutions are rejected",
    "4 domains become trusted",
    "A-review goes to review",
    "B-review goes to review",
    "C-review goes to review",
    "D-review goes to review",
  ]);
});

test("exactly three of a kind are still named", () => {
  expect(
    describeEffects(preview({ changes: ["A", "B", "C"].map((name) => change(name, "verified")) }))
      .changes,
  ).toEqual(["A becomes verified", "B becomes verified", "C becomes verified"]);
});

test("the work a decision started is counted by type for its toast", () => {
  expect(
    spawnSummary([
      { type: "find_sources", subject_id: "a" },
      { type: "find_homepage", subject_id: "b" },
      { type: "find_sources", subject_id: "c" },
    ]),
  ).toBe("2 Find sources, 1 Find homepage");
  expect(spawnSummary([])).toBe("");
});
