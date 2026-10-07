import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import { ChevronRightIcon } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/layout/page-header";
import { TableSkeleton } from "@/components/shared/skeletons";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { GlobalTypes } from "@/features/countries/components/global-types";
import { institutionTypesQuery, sourceTypesQuery } from "@/features/countries/queries";
import { unwrap } from "@/lib/api/errors";
import { getApi } from "@/lib/api/server";
import { getQueryClient } from "@/lib/query-client";
import { paths } from "@/lib/routes";

export const metadata: Metadata = { title: "Countries" };

export default function CountriesPage() {
  return (
    <>
      <PageHeader
        title="Countries"
        description="The tables the agent's rules are built from. Product data lives here, not in settings."
      />
      <div className="flex flex-col gap-8">
        <section className="flex flex-col gap-4">
          <h3 className="text-lg font-semibold">Countries</h3>
          <Suspense fallback={<Skeleton className="h-20" />}>
            <CountryList />
          </Suspense>
        </section>
        <Suspense fallback={<TableSkeleton />}>
          <GlobalTypesContent />
        </Suspense>
      </div>
    </>
  );
}

async function CountryList() {
  const api = await getApi();
  const countries = unwrap(await api.GET("/countries"));
  if (countries.length === 0) {
    return <EmptyState>No country seeded yet. Run `public-atlas seed canada`.</EmptyState>;
  }
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {countries.map((country) => (
        <Link
          key={country.country_code}
          href={paths.country(country.country_code)}
          className="block rounded-xl transition-colors hover:bg-muted/40"
        >
          <Card>
            <CardContent className="flex items-center justify-between">
              <span className="flex flex-col">
                <span className="font-medium">{country.name}</span>
                <span className="text-sm text-muted-foreground">{country.country_code}</span>
              </span>
              <ChevronRightIcon className="size-4 text-muted-foreground" />
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  );
}

async function GlobalTypesContent() {
  const api = await getApi();
  const queryClient = getQueryClient();
  await Promise.all([
    queryClient.prefetchQuery(institutionTypesQuery(api)),
    queryClient.prefetchQuery(sourceTypesQuery(api)),
  ]);
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <GlobalTypes />
    </HydrationBoundary>
  );
}
