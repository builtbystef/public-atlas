import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import type { Metadata } from "next";
import { Suspense } from "react";

import { TableSkeleton } from "@/components/shared/skeletons";
import { ReviewQueue } from "@/features/review/components/review-queue";
import { reviewListQuery } from "@/features/review/queries";
import { parseReviewSearch, reviewFilters } from "@/features/review/schemas";
import { unwrap } from "@/lib/api/errors";
import { getApi } from "@/lib/api/server";
import { toSearchString, type SearchParams } from "@/lib/lists";
import { getQueryClient } from "@/lib/query-client";
import { getTimeZone } from "@/lib/time-zone/server";

export const metadata: Metadata = { title: "Review queue" };

export default function ReviewPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  return (
    <Suspense fallback={<TableSkeleton />}>
      <ReviewContent searchParams={searchParams} />
    </Suspense>
  );
}

async function ReviewContent({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const filters = parseReviewSearch(await searchParams);
  const [api, timeZone] = await Promise.all([getApi(), getTimeZone()]);
  const queryClient = getQueryClient();
  const [countries] = await Promise.all([
    api.GET("/countries").then(unwrap),
    queryClient.prefetchQuery(reviewListQuery(api, reviewFilters(filters))),
  ]);
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <ReviewQueue
        key={toSearchString(filters)}
        initialFilters={filters}
        countries={countries.map((c) => ({ code: c.country_code, name: c.name }))}
        timeZone={timeZone}
      />
    </HydrationBoundary>
  );
}
