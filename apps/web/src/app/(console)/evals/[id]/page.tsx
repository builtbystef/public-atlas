import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import type { Metadata } from "next";
import { Suspense } from "react";

import { DetailSkeleton } from "@/components/shared/skeletons";
import { EvalRunDetail } from "@/features/evals/components/eval-run-detail";
import { COMPARE_ROWS, evalRunListQuery, evalRunQuery } from "@/features/evals/queries";
import { NO_COMPARISON, parseEvalRunSearch } from "@/features/evals/schemas";
import { getApi, unwrapOrNotFound } from "@/lib/api/server";
import type { SearchParams } from "@/lib/lists";
import { getQueryClient } from "@/lib/query-client";
import { getTimeZone } from "@/lib/time-zone/server";

export const metadata: Metadata = { title: "Eval run" };

type Params = Promise<{ id: string }>;

export default function EvalRunPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Promise<SearchParams>;
}) {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <EvalRunContent params={params} searchParams={searchParams} />
    </Suspense>
  );
}

async function EvalRunContent({
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
  const initialSearch = parseEvalRunSearch(search);
  const queryClient = getQueryClient();
  // A missing run is a not-found page, so it is read here rather than prefetched.
  const run = unwrapOrNotFound(
    await api.GET("/eval-runs/{eval_run_id}", { params: { path: { eval_run_id: id } } }),
  );
  queryClient.setQueryData(evalRunQuery(api, id).queryKey, run);
  const baselineId =
    initialSearch.compare === NO_COMPARISON
      ? null
      : (initialSearch.compare ?? run.previous_id ?? null);
  await Promise.all([
    baselineId && queryClient.prefetchQuery(evalRunQuery(api, baselineId)),
    queryClient.prefetchQuery(evalRunListQuery(api, COMPARE_ROWS)),
  ]);
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <EvalRunDetail id={id} initialSearch={initialSearch} timeZone={timeZone} />
    </HydrationBoundary>
  );
}
