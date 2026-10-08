import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import type { Metadata } from "next";
import { Suspense } from "react";

import { TableSkeleton } from "@/components/shared/skeletons";
import { EvalRunsTable } from "@/features/evals/components/eval-runs-table";
import { evalRunListQuery } from "@/features/evals/queries";
import { parseEvalSearch } from "@/features/evals/schemas";
import { getApi } from "@/lib/api/server";
import { paged, toSearchString, type SearchParams } from "@/lib/lists";
import { getQueryClient } from "@/lib/query-client";
import { getTimeZone } from "@/lib/time-zone/server";

export const metadata: Metadata = { title: "Evals" };

export default function EvalsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  return (
    <Suspense fallback={<TableSkeleton />}>
      <EvalsContent searchParams={searchParams} />
    </Suspense>
  );
}

async function EvalsContent({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const filters = parseEvalSearch(await searchParams);
  const [api, timeZone] = await Promise.all([getApi(), getTimeZone()]);
  const queryClient = getQueryClient();
  await queryClient.prefetchQuery(evalRunListQuery(api, paged(filters)));
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <EvalRunsTable key={toSearchString(filters)} initialFilters={filters} timeZone={timeZone} />
    </HydrationBoundary>
  );
}
