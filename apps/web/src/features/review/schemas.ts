import { z } from "zod";

import { reviewRules, reviewStatuses } from "@/lib/labels";
import { listSearch, optionalParam, paged, parseSearch, type SearchParams } from "@/lib/lists";
import { emptyToNull, text, TYPE_NAME, typeNameMessage } from "@/lib/validation";

import type { ReviewListFilters } from "./queries";

/** The list shows open items unless the URL says which status, or `all`. */
export const reviewStatusFilters = [...reviewStatuses, "all"] as const;

const reviewSearchSchema = z.object({
  status: optionalParam(z.enum(reviewStatusFilters)),
  rule: optionalParam(z.enum(reviewRules)),
  ...listSearch(["created_at"]),
});

export type ReviewSearch = z.output<typeof reviewSearchSchema>;

export function parseReviewSearch(params: SearchParams | URLSearchParams): ReviewSearch {
  return parseSearch(reviewSearchSchema, params);
}

/** A type name as the country tables spell it: `school_board`. */
export const typeName = text
  .transform(emptyToNull)
  .pipe(z.string().max(64, "At most 64 characters").regex(TYPE_NAME, typeNameMessage).nullable());

export const decisionSchema = z.object({
  note: text.transform(emptyToNull),
  institution_type: typeName,
});

export type DecisionFormInput = z.input<typeof decisionSchema>;

export const mergeSchema = z.object({
  into_id: text.min(1, "Choose what to merge into").pipe(z.uuid("Choose what to merge into")),
  note: text.transform(emptyToNull),
});

export type MergeFormInput = z.input<typeof mergeSchema>;

/** "type_level:school_board@municipality" → the type the kind is about, for the approve form. */
export function kindTypeName(kind: string): string {
  const [, rest = ""] = kind.split(":", 2);
  return rest.split("@", 1)[0] ?? "";
}

/** The API's list parameters for a parsed search: open items unless the URL says otherwise. */
export function reviewFilters(search: ReviewSearch): ReviewListFilters {
  const { status = "open", sort: _sort, order: _order, ...rest } = search;
  return { ...paged(rest), status: status === "all" ? undefined : status };
}
