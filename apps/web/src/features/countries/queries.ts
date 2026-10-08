import type { ApiClient, NamingRules } from "@public-atlas/api-client";
import { keepPreviousData, queryOptions } from "@tanstack/react-query";

import { unwrap } from "@/lib/api/errors";

export const countryKeys = {
  all: ["countries"] as const,
  list: () => [...countryKeys.all, "list"] as const,
  detail: (code: string) => [...countryKeys.all, "detail", code] as const,
  institutionTypes: () => [...countryKeys.all, "institution-types"] as const,
  sourceTypes: () => [...countryKeys.all, "source-types"] as const,
  defaultSources: () => [...countryKeys.all, "default-sources"] as const,
};

/**
 * The previews of an unsaved edit. Not under `countryKeys.all`: a save
 * changes nothing they read from the form, so they need no re-read.
 */
export const previewKeys = {
  naming: (rules: NamingRules, name: string) => ["naming-preview", rules, name] as const,
  namePattern: (code: string, type: string, pattern: string) =>
    ["name-pattern-check", code, type, pattern] as const,
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

/** The sources a type newly added to a country starts with, by institution type. */
export function defaultSourcesQuery(api: ApiClient) {
  return queryOptions({
    queryKey: countryKeys.defaultSources(),
    queryFn: async () => unwrap(await api.GET("/default-expected-source-types")),
  });
}

/** How naming rules, saved or not, read one name. */
export function namingPreviewQuery(api: ApiClient, rules: NamingRules, name: string) {
  return queryOptions({
    queryKey: previewKeys.naming(rules, name),
    queryFn: async ({ signal }) => {
      const [preview] = unwrap(
        await api.POST("/naming-rules/preview", {
          body: { naming_rules: rules, names: [name] },
          signal,
        }),
      );
      if (preview === undefined) throw new Error("The preview came back empty");
      return preview;
    },
    enabled: name.trim() !== "",
    placeholderData: keepPreviousData,
  });
}

/** A name pattern, saved or not, tried on the country's institutions of a type. */
export function namePatternCheckQuery(api: ApiClient, code: string, type: string, pattern: string) {
  return queryOptions({
    queryKey: previewKeys.namePattern(code, type, pattern),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.POST(
          "/countries/{country_code}/institution-types/{institution_type}/name-pattern-check",
          {
            params: { path: { country_code: code, institution_type: type } },
            body: { name_pattern: pattern },
            signal,
          },
        ),
      ),
    enabled: type !== "" && pattern !== "",
    placeholderData: keepPreviousData,
  });
}
