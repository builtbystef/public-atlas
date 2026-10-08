import type {
  DecisionPreviewOutput,
  EntityKind,
  EntityStatus,
  PlannedOutput,
} from "@public-atlas/api-client";
import { expect, test } from "vite-plus/test";

import { describeEffects } from "./effects";

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
