import type { ApiClient } from "@public-atlas/api-client";
import { queryOptions } from "@tanstack/react-query";

import { unwrap } from "@/lib/api/errors";
import type { ListPage } from "@/lib/lists";

export const evalKeys = {
  all: ["evals"] as const,
  list: (page: ListPage) => [...evalKeys.all, "list", page] as const,
  detail: (id: string) => [...evalKeys.all, "detail", id] as const,
};

/** The runs a run can be compared with: the newest, a page's worth. */
export const COMPARE_ROWS = { limit: 100, offset: 0 } as const;

/** Eval runs newest first, each with its mean scores per assignment type. */
export function evalRunListQuery(api: ApiClient, page: ListPage) {
  return queryOptions({
    queryKey: evalKeys.list(page),
    queryFn: async () => unwrap(await api.GET("/eval-runs", { params: { query: page } })),
  });
}

export function evalRunQuery(api: ApiClient, id: string) {
  return queryOptions({
    queryKey: evalKeys.detail(id),
    queryFn: async () =>
      unwrap(await api.GET("/eval-runs/{eval_run_id}", { params: { path: { eval_run_id: id } } })),
  });
}
