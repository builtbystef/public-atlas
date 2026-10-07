import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import { PlusIcon } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { PageHeader } from "@/components/shared/layout/page-header";
import { TableSkeleton } from "@/components/shared/skeletons";
import { Button } from "@/components/ui/button";
import { RunsTable } from "@/features/runs/components/runs-table";
import { runListQuery } from "@/features/runs/queries";
import { parseRunSearch } from "@/features/runs/schemas";
import { getApi } from "@/lib/api/server";
import { paged, toSearchString, type SearchParams } from "@/lib/lists";
import { getQueryClient } from "@/lib/query-client";
import { paths } from "@/lib/routes";
import { getTimeZone } from "@/lib/time-zone/server";

export const metadata: Metadata = { title: "Runs" };

export default function RunsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  return (
    <>
      <PageHeader
        title="Runs"
        description="A run is a controlled batch of assignments: a filter, a mode, and a budget it spends."
      >
        <Button nativeButton={false} render={<Link href={paths.runNew} />}>
          <PlusIcon /> New run
        </Button>
      </PageHeader>
      <Suspense fallback={<TableSkeleton />}>
        <RunsContent searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function RunsContent({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const filters = parseRunSearch(await searchParams);
  const [api, timeZone] = await Promise.all([getApi(), getTimeZone()]);
  const queryClient = getQueryClient();
  await queryClient.prefetchQuery(runListQuery(api, paged(filters)));
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RunsTable key={toSearchString(filters)} initialFilters={filters} timeZone={timeZone} />
    </HydrationBoundary>
  );
}
