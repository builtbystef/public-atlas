"use client";

import type { CountryOutput } from "@public-atlas/api-client";
import { useQuery } from "@tanstack/react-query";
import { MapPinIcon, SearchIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { placeOptionQuery } from "@/features/graph/queries";
import type { InstitutionFilterValues } from "@/features/graph/schemas";
import { browserApi } from "@/lib/api/client";
import { entityStatusLabels, humanize } from "@/lib/labels";
import { cn } from "@/lib/utils";

import { describePopulation } from "../schemas";

/** A list's filters as a row of short labels; "Every institution" when it has none. */
export function FilterChips({
  filters,
  countries,
  className,
}: {
  filters: InstitutionFilterValues;
  countries: CountryOutput[];
  className?: string;
}) {
  const country = countries.find((c) => c.settings.country_code === filters.country_code);
  const population = describePopulation(filters.min_population, filters.max_population);
  const chips = [
    filters.q && (
      <Badge key="q" variant="outline">
        <SearchIcon />“{filters.q}”
      </Badge>
    ),
    filters.country_code && (
      <Badge key="country" variant="outline">
        {country?.settings.name ?? filters.country_code}
      </Badge>
    ),
    filters.place_id && <PlaceChip key="place" id={filters.place_id} />,
    filters.administrative_level && (
      <Badge key="level" variant="outline">
        {humanize(filters.administrative_level)}
      </Badge>
    ),
    filters.institution_type && (
      <Badge key="type" variant="outline">
        {humanize(filters.institution_type)}
      </Badge>
    ),
    filters.status && (
      <Badge key="status" variant="outline">
        {entityStatusLabels[filters.status]}
      </Badge>
    ),
    population && (
      <Badge key="population" variant="outline">
        {population}
      </Badge>
    ),
  ].filter(Boolean);

  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {chips.length > 0 ? (
        chips
      ) : (
        <Badge variant="outline" className="text-muted-foreground">
          Every institution
        </Badge>
      )}
    </div>
  );
}

/** The place's name, fetched; its id stays out of sight while it loads. */
function PlaceChip({ id }: { id: string }) {
  const { data, isError } = useQuery(placeOptionQuery(browserApi, id));
  return (
    <Badge variant="outline">
      <MapPinIcon />
      {data?.name ?? (isError ? "A place not in this database" : "…")}
    </Badge>
  );
}
