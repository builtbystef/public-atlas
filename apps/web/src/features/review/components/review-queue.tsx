"use client";

import { Suspense } from "react";

import { TableSkeleton } from "@/components/shared/skeletons";
import { Skeleton } from "@/components/ui/skeleton";

import { useReviewActions } from "../hooks/use-review-actions";
import type { ReviewSearch } from "../schemas";
import { ReviewKinds } from "./review-kinds";
import { ReviewTable } from "./review-table";

/** The kinds above, the items below, one set of dialogs for both. */
export function ReviewQueue({
  initialFilters,
  timeZone,
}: {
  initialFilters: ReviewSearch;
  timeZone: string;
}) {
  const actions = useReviewActions();
  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-4">
        <h3 className="text-lg font-semibold">Shared questions</h3>
        <Suspense fallback={<Skeleton className="h-40" />}>
          <ReviewKinds actions={actions} />
        </Suspense>
      </section>
      <section className="flex flex-col gap-4">
        <h3 className="text-lg font-semibold">Items</h3>
        <Suspense fallback={<TableSkeleton />}>
          <ReviewTable initialFilters={initialFilters} timeZone={timeZone} actions={actions} />
        </Suspense>
      </section>
      {actions.dialog}
    </div>
  );
}
