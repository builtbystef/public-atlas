import type { RunInput } from "@public-atlas/api-client";
import { z } from "zod";

import { assignmentTypes, runModes } from "@/lib/labels";
import { listSearch, parseSearch, type SearchParams } from "@/lib/lists";
import { requiredText, text } from "@/lib/validation";

/** The create form's values, and the run they become. */
export const runSchema = z
  .object({
    name: requiredText("Name", 200),
    country_code: text.min(1, "Choose a country"),
    mode: z.enum(runModes),
    record_video: z.boolean(),
    administrative_levels: z.array(z.string()),
    institution_types: z.array(z.string()),
    assignment_types: z.array(z.enum(assignmentTypes)),
    subject_ids: z.array(z.uuid()),
  })
  .transform(
    ({
      administrative_levels,
      institution_types,
      assignment_types,
      subject_ids,
      ...run
    }): RunInput => ({
      ...run,
      filter: { administrative_levels, institution_types, assignment_types, subject_ids },
    }),
  );

export type RunFormInput = z.input<typeof runSchema>;

const runSearchSchema = z.object({ ...listSearch(["created_at"]) });

export type RunSearch = z.output<typeof runSearchSchema>;

export function parseRunSearch(params: SearchParams | URLSearchParams): RunSearch {
  return parseSearch(runSearchSchema, params);
}

export const releaseSchema = z.object({
  limit: z.coerce.number().int().min(1, "Release at least one").max(500, "At most 500 at once"),
  assignment_type: z.enum(assignmentTypes).or(z.literal("")),
});

export type ReleaseFormInput = z.input<typeof releaseSchema>;
