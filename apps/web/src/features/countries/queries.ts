import type { ApiClient } from "@public-atlas/api-client";
import { queryOptions } from "@tanstack/react-query";

import { unwrap } from "@/lib/api/errors";

export const countryKeys = {
  all: ["countries"] as const,
  list: () => [...countryKeys.all, "list"] as const,
  detail: (code: string) => [...countryKeys.all, "detail", code] as const,
  institutionTypes: () => [...countryKeys.all, "institution-types"] as const,
  sourceTypes: () => [...countryKeys.all, "source-types"] as const,
};

export function countriesQuery(api: ApiClient) {
  return queryOptions({
    queryKey: countryKeys.list(),
    queryFn: async () => unwrap(await api.GET("/countries")),
  });
}

/** A country's settings, levels and type rows: what a run's filter and the agent's rules read. */
export function countryQuery(api: ApiClient, code: string) {
  return queryOptions({
    queryKey: countryKeys.detail(code),
    queryFn: async () =>
      unwrap(
        await api.GET("/countries/{country_code}", { params: { path: { country_code: code } } }),
      ),
  });
}

export function institutionTypesQuery(api: ApiClient) {
  return queryOptions({
    queryKey: countryKeys.institutionTypes(),
    queryFn: async () => unwrap(await api.GET("/institution-types")),
  });
}

export function sourceTypesQuery(api: ApiClient) {
  return queryOptions({
    queryKey: countryKeys.sourceTypes(),
    queryFn: async () => unwrap(await api.GET("/source-types")),
  });
}
