import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/shared/layout/page-header";
import { TableSkeleton } from "@/components/shared/skeletons";
import { InstitutionsTable } from "@/features/graph/components/institutions-table";
import { institutionListQuery } from "@/features/graph/queries";
import { parseInstitutionSearch } from "@/features/graph/schemas";
import { unwrap } from "@/lib/api/errors";
import { getApi } from "@/lib/api/server";
import { paged, toSearchString, type SearchParams } from "@/lib/lists";
import { getQueryClient } from "@/lib/query-client";
import { getTimeZone } from "@/lib/time-zone/server";

export const metadata: Metadata = { title: "Institutions" };

export default function InstitutionsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  return (
    <>
      <PageHeader
        title="Institutions"
        description="Every public body in the graph, with its place, type, status and homepage."
      />
      <Suspense fallback={<TableSkeleton />}>
        <InstitutionsContent searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function InstitutionsContent({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const filters = parseInstitutionSearch(await searchParams);
  const [api, timeZone] = await Promise.all([getApi(), getTimeZone()]);
  const queryClient = getQueryClient();
  const [countryList, institutionTypes] = await Promise.all([
    api.GET("/countries").then(unwrap),
    api.GET("/institution-types").then(unwrap),
    queryClient.prefetchQuery(institutionListQuery(api, paged(filters))),
  ]);
  const countries = await Promise.all(
    countryList.map((c) =>
      api
        .GET("/countries/{country_code}", { params: { path: { country_code: c.country_code } } })
        .then(unwrap),
    ),
  );
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <InstitutionsTable
        key={toSearchString(filters)}
        initialFilters={filters}
        countries={countries}
        institutionTypes={institutionTypes}
        timeZone={timeZone}
      />
    </HydrationBoundary>
  );
}
