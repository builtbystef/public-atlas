import { z } from "zod";

import { assignmentTypes } from "@/lib/labels";
import { listSearch, optionalParam, parseSearch, type SearchParams } from "@/lib/lists";

const evalSearchSchema = z.object({ ...listSearch(["started_at"]) });

export type EvalSearch = z.output<typeof evalSearchSchema>;

export function parseEvalSearch(params: SearchParams | URLSearchParams): EvalSearch {
  return parseSearch(evalSearchSchema, params);
}

/**
 * How the subjects of a run are ordered: by their lowest recall on any
 * type, by name, by the largest fall in recall since the run compared
 * against, or by their recall on one assignment type.
 */
export const subjectSorts = ["lowest", "subject", "change", ...assignmentTypes] as const;

export type SubjectSort = (typeof subjectSorts)[number];

/** `compare=none` turns the comparison off; absent compares with the previous run. */
export const NO_COMPARISON = "none";

const evalRunSearchSchema = z.object({
  compare: optionalParam(z.uuid().or(z.literal(NO_COMPARISON))),
  sort: optionalParam(z.enum(subjectSorts)),
  below: optionalParam(z.literal("1")),
  // The score open in the side panel: one subject on one assignment type.
  subject: optionalParam(z.string().min(1)),
  type: optionalParam(z.enum(assignmentTypes)),
});

/** One eval run's page: what it is compared with, how its subjects are listed, and the score open. */
export type EvalRunSearch = z.output<typeof evalRunSearchSchema>;

export function parseEvalRunSearch(params: SearchParams | URLSearchParams): EvalRunSearch {
  return parseSearch(evalRunSearchSchema, params);
}
