import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import { ChevronRightIcon } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense, type ReactNode } from "react";

import { EmptyState } from "@/components/shared/empty-state";
import { TableSkeleton } from "@/components/shared/skeletons";
import { Skeleton } from "@/components/ui/skeleton";
import { CountryFlag } from "@/features/countries/components/country-flag";
import { GlobalTypes } from "@/features/countries/components/global-types";
import { institutionTypesQuery, sourceTypesQuery } from "@/features/countries/queries";
import { unwrap } from "@/lib/api/errors";
import { getApi } from "@/lib/api/server";
import { getQueryClient } from "@/lib/query-client";
import { paths } from "@/lib/routes";

export const metadata: Metadata = { title: "Country config" };

export default function CountryConfigPage() {
  return (
    <div className="flex flex-col gap-12">
      <Group title="Countries">
        <Suspense fallback={<Skeleton className="h-20" />}>
          <CountryList />
        </Suspense>
      </Group>
      <Group title="Shared across countries">
        <Suspense fallback={<TableSkeleton />}>
          <GlobalTypesContent />
        </Suspense>
      </Group>
    </div>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-5">
      <h2 className="border-b pb-3 text-lg font-semibold tracking-tight">{title}</h2>
      {children}
    </section>
  );
}

async function CountryList() {
  const api = await getApi();
  const countries = unwrap(await api.GET("/countries"));
  if (countries.length === 0) {
    return (
      <EmptyState boxed>
        No country seeded yet. Run <code className="font-mono">public-atlas seed canada</code>.
      </EmptyState>
    );
  }
  return (
    <ul className="divide-y overflow-hidden rounded-lg border">
      {countries.map((country) => (
        <li key={country.country_code}>
          <Link
            href={paths.country(country.country_code)}
            className="group/country flex items-center gap-3 px-3 py-2.5 text-sm transition-colors outline-none hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:ring-inset"
          >
            <CountryFlag code={country.country_code} className="h-4 w-6 rounded-[2px]" />
            <span className="flex min-w-0 gap-1.5">
              <span className="truncate font-medium">{country.name}</span>
              <span className="text-muted-foreground">({country.country_code})</span>
            </span>
            <ChevronRightIcon className="ml-auto size-4 shrink-0 text-muted-foreground transition-transform group-hover/country:translate-x-0.5" />
          </Link>
        </li>
      ))}
    </ul>
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
