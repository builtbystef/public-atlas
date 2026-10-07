import type { ApiClient } from "@public-atlas/api-client";
import { queryOptions } from "@tanstack/react-query";

import { unwrap } from "@/lib/api/errors";
import type { ListPage } from "@/lib/lists";

export const runKeys = {
  all: ["runs"] as const,
  list: (page: ListPage) => [...runKeys.all, "list", page] as const,
  detail: (id: string) => [...runKeys.all, "detail", id] as const,
};

export function runListQuery(api: ApiClient, page: ListPage) {
  return queryOptions({
    queryKey: runKeys.list(page),
    queryFn: async () => unwrap(await api.GET("/runs", { params: { query: page } })),
  });
}

export function runQuery(api: ApiClient, id: string) {
  return queryOptions({
    queryKey: runKeys.detail(id),
    queryFn: async () =>
      unwrap(await api.GET("/runs/{run_id}", { params: { path: { run_id: id } } })),
  });
}
