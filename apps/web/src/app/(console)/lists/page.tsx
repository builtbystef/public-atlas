import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/shared/layout/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { getFilterOptions } from "@/features/graph/server";
import { SavedListsOverview } from "@/features/saved-lists/components/saved-lists-overview";
import { getApi, getDatabase } from "@/lib/api/server";
import { getTimeZone } from "@/lib/time-zone/server";

export const metadata: Metadata = { title: "Saved lists" };

/** The console's front page: the institution queries saved in this browser. */
export default function SavedListsPage() {
  return (
    <Suspense fallback={<ListsSkeleton />}>
      <SavedListsContent />
    </Suspense>
  );
}

async function SavedListsContent() {
  const [api, database, timeZone] = await Promise.all([getApi(), getDatabase(), getTimeZone()]);
  const { countries, institutionTypes } = await getFilterOptions(api);
  return (
    <SavedListsOverview
      database={database}
      countries={countries}
      institutionTypes={institutionTypes}
      timeZone={timeZone}
    />
  );
}

function ListsSkeleton() {
  return (
    <>
      <PageHeader>
        <Skeleton className="h-8 w-64" />
      </PageHeader>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }, (_, i) => (
          <Skeleton key={i} className="h-36" />
        ))}
      </div>
    </>
  );
}
