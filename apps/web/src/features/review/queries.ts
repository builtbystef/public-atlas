import type {
  ApiClient,
  ApproveInput,
  DecisionInput,
  EntityKind,
  KindApproveInput,
  KindDecisionInput,
  MergeInput,
  ReviewStatus,
} from "@public-atlas/api-client";
import { queryOptions } from "@tanstack/react-query";

import { unwrap } from "@/lib/api/errors";
import { queryParams, type ListPage, type SortOrder } from "@/lib/lists";

import type { ReviewAffects, ReviewSort } from "./schemas";

export interface ReviewListFilters extends ListPage {
  /** Any status when absent. */
  status?: ReviewStatus | undefined;
  q?: string | undefined;
  rule?: string | undefined;
  /** The items of one shared question. */
  kind?: string | undefined;
  entity_kind?: EntityKind | undefined;
  country_code?: string | undefined;
  affects?: ReviewAffects | undefined;
  sort?: ReviewSort | undefined;
  order?: SortOrder | undefined;
}

export const reviewKeys = {
  all: ["review"] as const,
  list: (filters: ReviewListFilters) => [...reviewKeys.all, "list", filters] as const,
  detail: (id: string) => [...reviewKeys.all, "detail", id] as const,
};

/**
 * A page of the queue: each item on its own row, except the items that ask
 * the same question (one `kind`), which share a row and are decided together.
 */
export function reviewListQuery(api: ApiClient, filters: ReviewListFilters) {
  return queryOptions({
    queryKey: reviewKeys.list(filters),
    queryFn: async () =>
      unwrap(await api.GET("/review-items", { params: { query: queryParams(filters) } })),
  });
}

export function reviewItemQuery(api: ApiClient, id: string) {
  return queryOptions({
    queryKey: reviewKeys.detail(id),
    queryFn: async () =>
      unwrap(
        await api.GET("/review-items/{review_item_id}", {
          params: { path: { review_item_id: id } },
        }),
      ),
  });
}

/** A decision to preview: the same body the decision itself takes. */
export type PreviewRequest =
  | { decision: "approve"; id: string; body: ApproveInput }
  | { decision: "reject"; id: string; body: DecisionInput }
  | { decision: "merge"; id: string; body: MergeInput }
  | { decision: "approve-all"; body: KindApproveInput }
  | { decision: "reject-all"; body: KindDecisionInput };

/**
 * What a decision would do: the server makes it, says what changed and what
 * work it would start, and rolls it back. A refusal comes back as the
 * decision's own error.
 */
export function decisionPreviewQuery(api: ApiClient, request: PreviewRequest) {
  return queryOptions({
    queryKey: [...reviewKeys.all, "preview", request] as const,
    retry: false,
    queryFn: async () => {
      switch (request.decision) {
        case "approve":
          return unwrap(
            await api.POST("/review-items/{review_item_id}/approve/preview", {
              params: { path: { review_item_id: request.id } },
              body: request.body,
            }),
          );
        case "reject":
          return unwrap(
            await api.POST("/review-items/{review_item_id}/reject/preview", {
              params: { path: { review_item_id: request.id } },
              body: request.body,
            }),
          );
        case "merge":
          return unwrap(
            await api.POST("/review-items/{review_item_id}/merge/preview", {
              params: { path: { review_item_id: request.id } },
              body: request.body,
            }),
          );
        case "approve-all":
          return unwrap(
            await api.POST("/review-items/kinds/approve/preview", { body: request.body }),
          );
        case "reject-all":
          return unwrap(
            await api.POST("/review-items/kinds/reject/preview", { body: request.body }),
          );
      }
    },
  });
}
