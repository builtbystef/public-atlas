"use client";

import { Suspense } from "react";

import { TableSkeleton } from "@/components/shared/skeletons";

import { useReviewActions } from "../hooks/use-review-actions";
import type { ReviewSearch } from "../schemas";
import { ReviewTable } from "./review-table";

/** The queue's table and the one set of dialogs its decisions open. */
export function ReviewQueue({
  initialFilters,
  countries,
  timeZone,
}: {
  initialFilters: ReviewSearch;
  countries: { code: string; name: string }[];
  timeZone: string;
}) {
  const actions = useReviewActions();
  return (
    <>
      <Suspense fallback={<TableSkeleton />}>
        <ReviewTable
          initialFilters={initialFilters}
          countries={countries}
          timeZone={timeZone}
          actions={actions}
        />
      </Suspense>
      {actions.dialog}
    </>
  );
}
