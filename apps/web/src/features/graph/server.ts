import "server-only";

import type { ApiClient } from "@public-atlas/api-client";

import { unwrap } from "@/lib/api/errors";

/**
 * What the institution filters choose from: every country with its levels,
 * and the institution types. Read on the server for each page that filters.
 */
export async function getFilterOptions(api: ApiClient) {
  const [countryList, institutionTypes] = await Promise.all([
    api.GET("/countries").then(unwrap),
    api.GET("/institution-types").then(unwrap),
  ]);
  const countries = await Promise.all(
    countryList.map((c) =>
      api
        .GET("/countries/{country_code}", { params: { path: { country_code: c.country_code } } })
        .then(unwrap),
    ),
  );
  return { countries, institutionTypes };
}

export type FilterOptions = Awaited<ReturnType<typeof getFilterOptions>>;
