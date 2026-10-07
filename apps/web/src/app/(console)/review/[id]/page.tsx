import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import type { Metadata } from "next";
import { Suspense } from "react";

import { DetailSkeleton } from "@/components/shared/skeletons";
import { ReviewItemDetail } from "@/features/review/components/review-item-detail";
import { reviewItemQuery } from "@/features/review/queries";
import { getApi, unwrapOrNotFound } from "@/lib/api/server";
import { getQueryClient } from "@/lib/query-client";
import { getTimeZone } from "@/lib/time-zone/server";

export const metadata: Metadata = { title: "Review item" };

type Params = Promise<{ id: string }>;

export default function ReviewItemPage({ params }: { params: Params }) {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <ReviewItemContent params={params} />
    </Suspense>
  );
}

async function ReviewItemContent({ params }: { params: Params }) {
  const [{ id }, api, timeZone] = await Promise.all([params, getApi(), getTimeZone()]);
  const item = unwrapOrNotFound(
    await api.GET("/review-items/{review_item_id}", { params: { path: { review_item_id: id } } }),
  );
  const queryClient = getQueryClient();
  queryClient.setQueryData(reviewItemQuery(api, id).queryKey, item);
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <ReviewItemDetail id={id} timeZone={timeZone} />
    </HydrationBoundary>
  );
}
