import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import type { Metadata } from "next";
import { Suspense } from "react";

import { DetailSkeleton } from "@/components/shared/skeletons";
import { assignmentListQuery } from "@/features/assignments/queries";
import { assignmentFilters, parseAssignmentSearch } from "@/features/assignments/schemas";
import { RunDetail } from "@/features/runs/components/run-detail";
import { runQuery } from "@/features/runs/queries";
import { getApi, unwrapOrNotFound } from "@/lib/api/server";
import { toSearchString, type SearchParams } from "@/lib/lists";
import { getQueryClient } from "@/lib/query-client";
import { getTimeZone } from "@/lib/time-zone/server";

export const metadata: Metadata = { title: "Run" };

type Params = Promise<{ id: string }>;

export default function RunPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Promise<SearchParams>;
}) {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <RunContent params={params} searchParams={searchParams} />
    </Suspense>
  );
}

async function RunContent({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Promise<SearchParams>;
}) {
  const [{ id }, search, api, timeZone] = await Promise.all([
    params,
    searchParams,
    getApi(),
    getTimeZone(),
  ]);
  const filters = parseAssignmentSearch(search);
  const queryClient = getQueryClient();
  // A missing run is a not-found page, so it is read here rather than prefetched.
  const run = unwrapOrNotFound(
    await api.GET("/runs/{run_id}", { params: { path: { run_id: id } } }),
  );
  queryClient.setQueryData(runQuery(api, id).queryKey, run);
  await queryClient.prefetchQuery(
    assignmentListQuery(api, assignmentFilters(filters, { run_id: id })),
  );
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RunDetail
        key={toSearchString(filters)}
        id={id}
        assignmentFilters={filters}
        timeZone={timeZone}
      />
    </HydrationBoundary>
  );
}
