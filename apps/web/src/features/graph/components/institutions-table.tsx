"use client";

import type {
  CountryOutput,
  EntityStatus,
  InstitutionOutput,
  InstitutionTypeInput,
} from "@public-atlas/api-client";
import { useSuspenseQuery } from "@tanstack/react-query";
import { SearchIcon } from "lucide-react";
import { useState } from "react";

import { DataTable } from "@/components/shared/data-table";
import { EntityCombobox } from "@/components/shared/entity-combobox";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useListState } from "@/hooks/use-list-state";
import { useUrlFilters } from "@/hooks/use-url-filters";
import { browserApi } from "@/lib/api/client";
import { entityStatusLabels, entityStatuses, humanize } from "@/lib/labels";
import { paged } from "@/lib/lists";
import { cn } from "@/lib/utils";

import { institutionListQuery, placeOptionQuery, placePickerQuery } from "../queries";
import { parseInstitutionSearch, type InstitutionSearch } from "../schemas";
import { institutionColumns } from "./institution-columns";

const SEARCH_DEBOUNCE_MS = 250;

export function InstitutionsTable({
  initialFilters,
  countries,
  institutionTypes,
  timeZone,
}: {
  initialFilters: InstitutionSearch;
  /** Every country with its levels, for the country and level filters. */
  countries: CountryOutput[];
  institutionTypes: InstitutionTypeInput[];
  timeZone: string;
}) {
  const [input, setInput] = useState(initialFilters.q ?? "");
  const q = useDebouncedValue(input.trim(), SEARCH_DEBOUNCE_MS);
  const [countryCode, setCountryCode] = useState(initialFilters.country_code ?? "");
  const [placeId, setPlaceId] = useState(initialFilters.place_id ?? "");
  const [level, setLevel] = useState(initialFilters.administrative_level ?? "");
  const [type, setType] = useState(initialFilters.institution_type ?? "");
  const [status, setStatus] = useState<EntityStatus | "">(initialFilters.status ?? "");

  const list = useListState({
    filterKey: [q, countryCode, placeId, level, type, status].join("\0"),
    initial: initialFilters,
    defaultSort: { sort: "name", order: "asc" },
  });
  const { deferred, isStale } = useUrlFilters(
    {
      q: q || undefined,
      country_code: countryCode || undefined,
      place_id: placeId || undefined,
      administrative_level: level || undefined,
      institution_type: type || undefined,
      status: status || undefined,
      ...list.search,
    },
    parseInstitutionSearch,
  );
  const { data: institutions } = useSuspenseQuery(
    institutionListQuery(browserApi, paged(deferred)),
  );

  const levels = countries
    .filter((c) => !countryCode || c.settings.country_code === countryCode)
    .flatMap((c) => c.administrative_levels.map((l) => l.name));
  const levelOptions = [...new Set(levels)];
  const filtered = Boolean(q || countryCode || placeId || level || type || status);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <InputGroup className="w-64">
          <InputGroupAddon>
            <SearchIcon />
          </InputGroupAddon>
          <InputGroupInput
            type="search"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Name or alias"
            aria-label="Search institutions"
          />
        </InputGroup>
        <div className="w-56">
          <EntityCombobox
            id="place-filter"
            name="place_id"
            value={placeId}
            onValueChange={setPlaceId}
            placeholder="Any place"
            search={(text) => placePickerQuery(browserApi, text, countryCode || undefined)}
            resolve={(id) => placeOptionQuery(browserApi, id)}
          />
        </div>
        {countries.length > 1 && (
          <NativeSelect
            value={countryCode}
            onChange={(event) => setCountryCode(event.target.value)}
            aria-label="Filter by country"
          >
            <NativeSelectOption value="">Any country</NativeSelectOption>
            {countries.map((c) => (
              <NativeSelectOption key={c.settings.country_code} value={c.settings.country_code}>
                {c.settings.name}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        )}
        <NativeSelect
          value={level}
          onChange={(event) => setLevel(event.target.value)}
          aria-label="Filter by administrative level"
        >
          <NativeSelectOption value="">Any level</NativeSelectOption>
          {levelOptions.map((name) => (
            <NativeSelectOption key={name} value={name}>
              {humanize(name)}
            </NativeSelectOption>
          ))}
        </NativeSelect>
        <NativeSelect
          value={type}
          onChange={(event) => setType(event.target.value)}
          aria-label="Filter by institution type"
        >
          <NativeSelectOption value="">Any type</NativeSelectOption>
          {institutionTypes.map((t) => (
            <NativeSelectOption key={t.name} value={t.name}>
              {humanize(t.name)}
            </NativeSelectOption>
          ))}
        </NativeSelect>
        <NativeSelect
          value={status}
          onChange={(event) => setStatus(event.target.value as EntityStatus | "")}
          aria-label="Filter by status"
        >
          <NativeSelectOption value="">Any status</NativeSelectOption>
          {entityStatuses.map((value) => (
            <NativeSelectOption key={value} value={value}>
              {entityStatusLabels[value]}
            </NativeSelectOption>
          ))}
        </NativeSelect>
        <span className="ml-auto text-sm text-muted-foreground">
          {institutions.total} {institutions.total === 1 ? "institution" : "institutions"}
        </span>
      </div>
      <DataTable<InstitutionOutput>
        columns={institutionColumns({ timeZone })}
        data={institutions.items}
        total={institutions.total}
        page={list.page}
        onPageChange={list.setPage}
        sorting={list.sorting}
        onSortingChange={list.setSorting}
        emptyMessage={
          filtered
            ? "No institutions match these filters."
            : "No institutions yet. Seed a country and load a list."
        }
        className={cn(isStale && "opacity-60 transition-opacity")}
      />
    </div>
  );
}
