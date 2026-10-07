import { z } from "zod";

import { assignmentResults, assignmentStatuses, assignmentTypes } from "@/lib/labels";
import { listSearch, optionalParam, paged, parseSearch, type SearchParams } from "@/lib/lists";

const assignmentSearchSchema = z.object({
  run_id: optionalParam(z.uuid()),
  subject_id: optionalParam(z.uuid()),
  status: optionalParam(z.enum(assignmentStatuses)),
  result: optionalParam(z.enum(assignmentResults)),
  type: optionalParam(z.enum(assignmentTypes)),
  ...listSearch(["created_at"]),
});

export type AssignmentSearch = z.output<typeof assignmentSearchSchema>;

export function parseAssignmentSearch(params: SearchParams | URLSearchParams): AssignmentSearch {
  return parseSearch(assignmentSearchSchema, params);
}

/** Filters a page fixes (a run's page shows its own assignments) and keeps out of the URL. */
export interface FixedFilters {
  run_id?: string | undefined;
  subject_id?: string | undefined;
}

/** The API's list parameters for a parsed search: newest first, the fixed filters added. */
export function assignmentFilters(search: AssignmentSearch, fixed: FixedFilters = {}) {
  const { sort: _sort, ...rest } = search;
  return { ...paged(rest), ...fixed, order: "desc" as const };
}
