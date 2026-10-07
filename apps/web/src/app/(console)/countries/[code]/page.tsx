import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import type { Metadata } from "next";
import { Suspense } from "react";

import { DetailSkeleton } from "@/components/shared/skeletons";
import { CountryDetail } from "@/features/countries/components/country-detail";
import {
  countryQuery,
  institutionTypesQuery,
  sourceTypesQuery,
} from "@/features/countries/queries";
import { getApi, unwrapOrNotFound } from "@/lib/api/server";
import { getQueryClient } from "@/lib/query-client";

export const metadata: Metadata = { title: "Country" };

type Params = Promise<{ code: string }>;

export default function CountryPage({ params }: { params: Params }) {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <CountryContent params={params} />
    </Suspense>
  );
}

async function CountryContent({ params }: { params: Params }) {
  const [{ code }, api] = await Promise.all([params, getApi()]);
  const country = unwrapOrNotFound(
    await api.GET("/countries/{country_code}", { params: { path: { country_code: code } } }),
  );
  const queryClient = getQueryClient();
  queryClient.setQueryData(countryQuery(api, code).queryKey, country);
  await Promise.all([
    queryClient.prefetchQuery(institutionTypesQuery(api)),
    queryClient.prefetchQuery(sourceTypesQuery(api)),
  ]);
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <CountryDetail code={code} />
    </HydrationBoundary>
  );
}
