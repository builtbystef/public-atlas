import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import type { Metadata } from "next";
import { Suspense } from "react";

import { GraphLink } from "@/components/shared/graph-link";
import { DetailSkeleton, TableSkeleton } from "@/components/shared/skeletons";
import { AssignmentsTable } from "@/features/assignments/components/assignments-table";
import { assignmentListQuery } from "@/features/assignments/queries";
import { assignmentFilters, parseAssignmentSearch } from "@/features/assignments/schemas";
import { InstitutionDetail } from "@/features/graph/components/institution-detail";
import { getApi, unwrapOrNotFound } from "@/lib/api/server";
import { toSearchString, type SearchParams } from "@/lib/lists";
import { getQueryClient } from "@/lib/query-client";
import { getTimeZone } from "@/lib/time-zone/server";

export const metadata: Metadata = { title: "Institution" };

type Params = Promise<{ id: string }>;

export default function InstitutionPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Promise<SearchParams>;
}) {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <InstitutionContent params={params} searchParams={searchParams} />
    </Suspense>
  );
}

async function InstitutionContent({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Promise<SearchParams>;
}) {
  const [{ id }, api, timeZone] = await Promise.all([params, getApi(), getTimeZone()]);
  const institution = unwrapOrNotFound(
    await api.GET("/institutions/{institution_id}", { params: { path: { institution_id: id } } }),
  );
  return (
    <InstitutionDetail
      institution={institution}
      timeZone={timeZone}
      actions={<GraphLink search={{ place_id: institution.place.id, node: institution.id }} />}
    >
      <section className="mt-8 flex flex-col gap-4">
        <h3 className="text-lg font-semibold">Assignments</h3>
        <Suspense fallback={<TableSkeleton rows={3} />}>
          <InstitutionAssignments id={id} searchParams={searchParams} timeZone={timeZone} />
        </Suspense>
      </section>
    </InstitutionDetail>
  );
}

async function InstitutionAssignments({
  id,
  searchParams,
  timeZone,
}: {
  id: string;
  searchParams: Promise<SearchParams>;
  timeZone: string;
}) {
  const [search, api] = await Promise.all([searchParams, getApi()]);
  const filters = parseAssignmentSearch(search);
  const queryClient = getQueryClient();
  await queryClient.prefetchQuery(
    assignmentListQuery(api, assignmentFilters(filters, { subject_id: id })),
  );
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <AssignmentsTable
        key={toSearchString(filters)}
        initialFilters={filters}
        fixed={{ subject_id: id }}
        timeZone={timeZone}
      />
    </HydrationBoundary>
  );
}
