import type { Metadata } from "next";
import { Suspense } from "react";

import { DetailSkeleton } from "@/components/shared/skeletons";
import { parseInstitutionSearch } from "@/features/graph/schemas";
import { getFilterOptions } from "@/features/graph/server";
import { SavedListView } from "@/features/saved-lists/components/saved-list-view";
import { getApi, getDatabase } from "@/lib/api/server";
import type { SearchParams } from "@/lib/lists";
import { getTimeZone } from "@/lib/time-zone/server";

export const metadata: Metadata = { title: "Saved list" };

type Params = Promise<{ id: string }>;

/**
 * One saved list. The list itself is in the browser's storage, so the server
 * renders what the filters choose from and the table loads in the browser.
 */
export default function SavedListPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Promise<SearchParams>;
}) {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <SavedListContent params={params} searchParams={searchParams} />
    </Suspense>
  );
}

async function SavedListContent({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Promise<SearchParams>;
}) {
  const [{ id }, search, api, database, timeZone] = await Promise.all([
    params,
    searchParams,
    getApi(),
    getDatabase(),
    getTimeZone(),
  ]);
  const { countries, institutionTypes } = await getFilterOptions(api);
  return (
    <SavedListView
      database={database}
      id={id}
      initialFilters={parseInstitutionSearch(search)}
      countries={countries}
      institutionTypes={institutionTypes}
      timeZone={timeZone}
    />
  );
}
