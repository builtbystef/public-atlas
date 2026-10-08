import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import type { Metadata } from "next";
import { Suspense } from "react";

import { GraphLink } from "@/components/shared/graph-link";
import { DetailSkeleton, TableSkeleton } from "@/components/shared/skeletons";
import { PlaceDetail } from "@/features/graph/components/place-detail";
import { PlacesTable } from "@/features/graph/components/places-table";
import {
  institutionListQuery,
  institutionTableFilters,
  placeListQuery,
  placeTableFilters,
} from "@/features/graph/queries";
import { parseInstitutionSearch } from "@/features/graph/schemas";
import { getFilterOptions } from "@/features/graph/server";
import { SavableInstitutionsTable } from "@/features/saved-lists/components/savable-institutions-table";
import { getApi, getDatabase, unwrapOrNotFound } from "@/lib/api/server";
import { toSearchString, type SearchParams } from "@/lib/lists";
import { getQueryClient } from "@/lib/query-client";
import { getTimeZone } from "@/lib/time-zone/server";

export const metadata: Metadata = { title: "Place" };

type Params = Promise<{ id: string }>;

export default function PlacePage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Promise<SearchParams>;
}) {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <PlaceContent params={params} searchParams={searchParams} />
    </Suspense>
  );
}

async function PlaceContent({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Promise<SearchParams>;
}) {
  const [{ id }, api, timeZone] = await Promise.all([params, getApi(), getTimeZone()]);
  const place = unwrapOrNotFound(
    await api.GET("/places/{place_id}", { params: { path: { place_id: id } } }),
  );
  return (
    <PlaceDetail
      place={place}
      timeZone={timeZone}
      actions={<GraphLink search={{ place_id: place.id }} />}
    >
      <Suspense fallback={<TableSkeleton rows={3} />}>
        <ChildPlaces id={id} name={place.name} />
      </Suspense>
      <section id="institutions" className="flex scroll-mt-20 flex-col gap-4">
        <h3 className="text-lg font-semibold">Institutions in {place.name}</h3>
        <Suspense fallback={<TableSkeleton />}>
          <PlaceInstitutions id={id} searchParams={searchParams} timeZone={timeZone} />
        </Suspense>
      </section>
    </PlaceDetail>
  );
}

/** The places directly under this one; nothing at all for a place with none. */
async function ChildPlaces({ id, name }: { id: string; name: string }) {
  const api = await getApi();
  const queryClient = getQueryClient();
  const [children, { countries }] = await Promise.all([
    queryClient.fetchQuery(placeListQuery(api, placeTableFilters({}, { parent_place_id: id }))),
    getFilterOptions(api),
  ]);
  if (children.total === 0) return null;
  return (
    <section className="flex flex-col gap-4">
      <h3 className="text-lg font-semibold">Places in {name}</h3>
      <HydrationBoundary state={dehydrate(queryClient)}>
        <PlacesTable initialFilters={{}} parentPlaceId={id} countries={countries} />
      </HydrationBoundary>
    </section>
  );
}

/** The institutions in the place and every place under it; the URL is theirs. */
async function PlaceInstitutions({
  id,
  searchParams,
  timeZone,
}: {
  id: string;
  searchParams: Promise<SearchParams>;
  timeZone: string;
}) {
  const [search, api, database] = await Promise.all([searchParams, getApi(), getDatabase()]);
  const filters = parseInstitutionSearch(search);
  const fixed = { place_id: id };
  const queryClient = getQueryClient();
  const [{ countries, institutionTypes }] = await Promise.all([
    getFilterOptions(api),
    queryClient.prefetchQuery(institutionListQuery(api, institutionTableFilters(filters, fixed))),
  ]);
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <SavableInstitutionsTable
        key={toSearchString(filters)}
        database={database}
        initialFilters={filters}
        fixed={fixed}
        countries={countries}
        institutionTypes={institutionTypes}
        timeZone={timeZone}
      />
    </HydrationBoundary>
  );
}
