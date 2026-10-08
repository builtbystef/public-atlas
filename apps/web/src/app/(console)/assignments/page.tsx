import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import type { Metadata } from "next";
import { Suspense } from "react";

import { TableSkeleton } from "@/components/shared/skeletons";
import { AssignmentsTable } from "@/features/assignments/components/assignments-table";
import { assignmentListQuery } from "@/features/assignments/queries";
import { assignmentFilters, parseAssignmentSearch } from "@/features/assignments/schemas";
import { getApi } from "@/lib/api/server";
import { toSearchString, type SearchParams } from "@/lib/lists";
import { getQueryClient } from "@/lib/query-client";
import { getTimeZone } from "@/lib/time-zone/server";

export const metadata: Metadata = { title: "Assignments" };

export default function AssignmentsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  return (
    <Suspense fallback={<TableSkeleton />}>
      <AssignmentsContent searchParams={searchParams} />
    </Suspense>
  );
}

async function AssignmentsContent({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const filters = parseAssignmentSearch(await searchParams);
  const [api, timeZone] = await Promise.all([getApi(), getTimeZone()]);
  const queryClient = getQueryClient();
  await queryClient.prefetchQuery(assignmentListQuery(api, assignmentFilters(filters)));
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <AssignmentsTable
        key={toSearchString(filters)}
        initialFilters={filters}
        timeZone={timeZone}
      />
    </HydrationBoundary>
  );
}
