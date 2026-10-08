import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { GraphView } from "@/features/graph/components/graph-view";
import { graphQuery, graphViewFilters } from "@/features/graph/queries";
import { parseGraphSearch } from "@/features/graph/schemas";
import { getFilterOptions } from "@/features/graph/server";
import { getApi } from "@/lib/api/server";
import { toSearchString, type SearchParams } from "@/lib/lists";
import { getQueryClient } from "@/lib/query-client";
import { getTimeZone } from "@/lib/time-zone/server";

export const metadata: Metadata = { title: "Graph" };

export default function GraphPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  return (
    <Suspense fallback={<GraphSkeleton />}>
      <GraphContent searchParams={searchParams} />
    </Suspense>
  );
}

async function GraphContent({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const search = parseGraphSearch(await searchParams);
  const [api, timeZone] = await Promise.all([getApi(), getTimeZone()]);
  const queryClient = getQueryClient();
  const [{ countries, institutionTypes }] = await Promise.all([
    getFilterOptions(api),
    queryClient.prefetchQuery(graphQuery(api, graphViewFilters(search))),
  ]);
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <GraphView
        key={toSearchString(search)}
        initialSearch={search}
        countries={countries}
        institutionTypes={institutionTypes}
        timeZone={timeZone}
      />
    </HydrationBoundary>
  );
}

function GraphSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-8 w-full" />
      <Skeleton className="h-[max(28rem,calc(100svh-16rem))] w-full" />
    </div>
  );
}
