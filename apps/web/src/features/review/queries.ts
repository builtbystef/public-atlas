import type { ApiClient, ReviewStatus } from "@public-atlas/api-client";
import { queryOptions } from "@tanstack/react-query";

import { unwrap } from "@/lib/api/errors";
import { queryParams, type ListPage } from "@/lib/lists";

export interface ReviewListFilters extends ListPage {
  status?: ReviewStatus | undefined;
  kind?: string | undefined;
  rule?: string | undefined;
}

export const reviewKeys = {
  all: ["review"] as const,
  kinds: () => [...reviewKeys.all, "kinds"] as const,
  list: (filters: ReviewListFilters) => [...reviewKeys.all, "list", filters] as const,
  detail: (id: string) => [...reviewKeys.all, "detail", id] as const,
};

/** The open items that ask a shared question, one row per question. */
export function reviewKindsQuery(api: ApiClient) {
  return queryOptions({
    queryKey: reviewKeys.kinds(),
    queryFn: async () => unwrap(await api.GET("/review-items/kinds")),
  });
}

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
