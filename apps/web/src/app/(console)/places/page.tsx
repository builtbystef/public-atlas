import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/shared/layout/page-header";
import { TableSkeleton } from "@/components/shared/skeletons";
import { PlacesTable } from "@/features/graph/components/places-table";
import { placeListQuery, placeTableFilters } from "@/features/graph/queries";
import { parsePlaceSearch } from "@/features/graph/schemas";
import { getFilterOptions } from "@/features/graph/server";
import { getApi } from "@/lib/api/server";
import { toSearchString, type SearchParams } from "@/lib/lists";
import { getQueryClient } from "@/lib/query-client";

export const metadata: Metadata = { title: "Places" };

export default function PlacesPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  return (
    <>
      <PageHeader
        title="Places"
        description="Every place in the graph, from the country down, with its level and population. Open one for the institutions in it."
      />
      <Suspense fallback={<TableSkeleton />}>
        <PlacesContent searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function PlacesContent({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const filters = parsePlaceSearch(await searchParams);
  const api = await getApi();
  const queryClient = getQueryClient();
  const [{ countries }] = await Promise.all([
    getFilterOptions(api),
    queryClient.prefetchQuery(placeListQuery(api, placeTableFilters(filters))),
  ]);
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <PlacesTable key={toSearchString(filters)} initialFilters={filters} countries={countries} />
    </HydrationBoundary>
  );
}
