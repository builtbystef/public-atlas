import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import type { Metadata } from "next";
import { Suspense } from "react";

import { DetailSkeleton } from "@/components/shared/skeletons";
import { AssignmentDetail } from "@/features/assignments/components/assignment-detail";
import {
  assignmentEventsQuery,
  assignmentFindingsQuery,
  assignmentQuery,
} from "@/features/assignments/queries";
import { getApi, unwrapOrNotFound } from "@/lib/api/server";
import { getQueryClient } from "@/lib/query-client";
import { getTimeZone } from "@/lib/time-zone/server";

export const metadata: Metadata = { title: "Assignment" };

type Params = Promise<{ id: string }>;

export default function AssignmentPage({ params }: { params: Params }) {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <AssignmentContent params={params} />
    </Suspense>
  );
}

async function AssignmentContent({ params }: { params: Params }) {
  const [{ id }, api, timeZone] = await Promise.all([params, getApi(), getTimeZone()]);
  const queryClient = getQueryClient();
  const assignment = unwrapOrNotFound(
    await api.GET("/assignments/{assignment_id}", { params: { path: { assignment_id: id } } }),
  );
  queryClient.setQueryData(assignmentQuery(api, id).queryKey, assignment);
  await Promise.all([
    queryClient.prefetchQuery(assignmentFindingsQuery(api, id)),
    queryClient.prefetchQuery(assignmentEventsQuery(api, id)),
  ]);
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <AssignmentDetail id={id} timeZone={timeZone} />
    </HydrationBoundary>
  );
}
