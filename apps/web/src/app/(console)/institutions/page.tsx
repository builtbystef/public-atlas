import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import type { Metadata } from "next";
import { Suspense } from "react";

import { TableSkeleton } from "@/components/shared/skeletons";
import { institutionListQuery, institutionTableFilters } from "@/features/graph/queries";
import { parseInstitutionSearch } from "@/features/graph/schemas";
import { getFilterOptions } from "@/features/graph/server";
import { SavableInstitutionsTable } from "@/features/saved-lists/components/savable-institutions-table";
import { getApi, getDatabase } from "@/lib/api/server";
import { toSearchString, type SearchParams } from "@/lib/lists";
import { getQueryClient } from "@/lib/query-client";
import { getTimeZone } from "@/lib/time-zone/server";

export const metadata: Metadata = { title: "Institutions" };

export default function InstitutionsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  return (
    <Suspense fallback={<TableSkeleton />}>
      <InstitutionsContent searchParams={searchParams} />
    </Suspense>
  );
}

async function InstitutionsContent({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const filters = parseInstitutionSearch(await searchParams);
  const [api, database, timeZone] = await Promise.all([getApi(), getDatabase(), getTimeZone()]);
  const queryClient = getQueryClient();
  const [{ countries, institutionTypes }] = await Promise.all([
    getFilterOptions(api),
    queryClient.prefetchQuery(institutionListQuery(api, institutionTableFilters(filters))),
  ]);
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <SavableInstitutionsTable
        key={toSearchString(filters)}
        database={database}
        initialFilters={filters}
        countries={countries}
        institutionTypes={institutionTypes}
        timeZone={timeZone}
      />
    </HydrationBoundary>
  );
}
