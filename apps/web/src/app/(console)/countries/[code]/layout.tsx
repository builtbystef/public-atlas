import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import type { Metadata } from "next";
import { Suspense, type ReactNode } from "react";

import { DetailSkeleton } from "@/components/shared/skeletons";
import { CountryShell } from "@/features/countries/components/country-detail";
import { CountryFlag } from "@/features/countries/components/country-flag";
import {
  countryQuery,
  defaultSourcesQuery,
  institutionTypesQuery,
  sourceTypesQuery,
} from "@/features/countries/queries";
import { getApi, unwrapOrNotFound } from "@/lib/api/server";
import { getQueryClient } from "@/lib/query-client";

export const metadata: Metadata = { title: "Country" };

type Params = Promise<{ code: string }>;

/**
 * A country's pages share its header and the list of them. Everything they
 * show is read here once, so moving between them makes no request.
 */
export default function CountryLayout({
  params,
  children,
}: {
  params: Params;
  children: ReactNode;
}) {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <CountryContent params={params}>{children}</CountryContent>
    </Suspense>
  );
}

async function CountryContent({ params, children }: { params: Params; children: ReactNode }) {
  const [{ code }, api] = await Promise.all([params, getApi()]);
  const country = unwrapOrNotFound(
    await api.GET("/countries/{country_code}", { params: { path: { country_code: code } } }),
  );
  const queryClient = getQueryClient();
  queryClient.setQueryData(countryQuery(api, code).queryKey, country);
  await Promise.all([
    queryClient.prefetchQuery(institutionTypesQuery(api)),
    queryClient.prefetchQuery(sourceTypesQuery(api)),
    queryClient.prefetchQuery(defaultSourcesQuery(api)),
  ]);
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <CountryShell
        code={code}
        // Rendered here: the flags module is server-only.
        flag={<CountryFlag code={country.settings.country_code} className="h-7 w-[2.625rem]" />}
      >
        {children}
      </CountryShell>
    </HydrationBoundary>
  );
}
