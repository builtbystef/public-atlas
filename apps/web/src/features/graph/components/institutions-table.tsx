"use client";

import type {
  CountryOutput,
  EntityStatus,
  InstitutionOutput,
  InstitutionTypeInput,
} from "@public-atlas/api-client";
import { useSuspenseQuery } from "@tanstack/react-query";
import { SearchIcon } from "lucide-react";
import { useState, type ReactNode } from "react";

import { DataTable } from "@/components/shared/data-table";
import { EntityCombobox } from "@/components/shared/entity-combobox";
import { TableToolbar } from "@/components/shared/table-toolbar";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useListState } from "@/hooks/use-list-state";
import { useUrlFilters } from "@/hooks/use-url-filters";
import { browserApi } from "@/lib/api/client";
import { entityStatusLabels, entityStatuses, humanize } from "@/lib/labels";
import { cn } from "@/lib/utils";

import {
  institutionListQuery,
  institutionTableFilters,
  placeOptionQuery,
  placePickerQuery,
} from "../queries";
import {
  parseInstitutionSearch,
  type InstitutionFilterValues,
  type InstitutionSearch,
} from "../schemas";
import { institutionColumns } from "./institution-columns";
import { PopulationRange, populationBound } from "./population-range";

const SEARCH_DEBOUNCE_MS = 250;

export function InstitutionsTable({
  initialFilters,
  fixed = {},
  countries,
  institutionTypes,
  timeZone,
  actions,
}: {
  initialFilters: InstitutionSearch;
  /**
   * Filters the page holds, such as the place on a place's page or a saved
   * list's definition. Their controls are hidden and they stay out of the URL.
   */
  fixed?: InstitutionFilterValues;
  /** Every country with its levels, for the country and level filters. */
  countries: CountryOutput[];
  institutionTypes: InstitutionTypeInput[];
  timeZone: string;
  /** Rendered at the end of the toolbar with the filters in force: a "Save as list" button. */
  actions?: (filters: InstitutionFilterValues) => ReactNode;
}) {
  const [input, setInput] = useState(initialFilters.q ?? "");
  const q = useDebouncedValue(input.trim(), SEARCH_DEBOUNCE_MS);
  const [countryCode, setCountryCode] = useState(initialFilters.country_code ?? "");
  const [placeId, setPlaceId] = useState(initialFilters.place_id ?? "");
  const [level, setLevel] = useState(initialFilters.administrative_level ?? "");
  const [type, setType] = useState(initialFilters.institution_type ?? "");
  const [status, setStatus] = useState<EntityStatus | "">(initialFilters.status ?? "");
  const [minInput, setMinInput] = useState(initialFilters.min_population?.toString() ?? "");
  const [maxInput, setMaxInput] = useState(initialFilters.max_population?.toString() ?? "");
  const minPopulation = populationBound(useDebouncedValue(minInput, SEARCH_DEBOUNCE_MS));
  const maxPopulation = populationBound(useDebouncedValue(maxInput, SEARCH_DEBOUNCE_MS));

  const shows = (key: keyof InstitutionFilterValues) => fixed[key] === undefined;
  // What the controls choose, less what the page holds fixed.
  const chosen = Object.fromEntries(
    Object.entries({
      q: q || undefined,
      country_code: countryCode || undefined,
      place_id: placeId || undefined,
      administrative_level: level || undefined,
      institution_type: type || undefined,
      status: status || undefined,
      min_population: minPopulation,
      max_population: maxPopulation,
    }).filter(([key]) => shows(key as keyof InstitutionFilterValues)),
  ) as InstitutionFilterValues;

  const list = useListState({
    filterKey: JSON.stringify(chosen),
    initial: initialFilters,
    defaultSort: { sort: "name", order: "asc" },
  });
  const { deferred, isStale } = useUrlFilters(
    { ...chosen, ...list.search },
    parseInstitutionSearch,
  );
  const { data: institutions } = useSuspenseQuery(
    institutionListQuery(browserApi, institutionTableFilters(deferred, fixed)),
  );

  const country = fixed.country_code ?? countryCode;
  const levels = countries
    .filter((c) => !country || c.settings.country_code === country)
    .flatMap((c) => c.administrative_levels.map((l) => l.name));
  const levelOptions = [...new Set(levels)];
  const filtered = Object.values({ ...chosen, ...fixed }).some((value) => value !== undefined);
  const clear = () => {
    setInput("");
    setCountryCode("");
    setPlaceId("");
    setLevel("");
    setType("");
    setStatus("");
    setMinInput("");
    setMaxInput("");
  };

  return (
    <div className="flex flex-col gap-4">
      <TableToolbar
        search={
          shows("q") && (
            <InputGroup>
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
          )
        }
        filters={
          <>
            {shows("place_id") && (
              <div className="w-56">
                <EntityCombobox
                  id="place-filter"
                  name="place_id"
                  value={placeId}
                  onValueChange={setPlaceId}
                  placeholder="Any place"
                  search={(text) => placePickerQuery(browserApi, text, country || undefined)}
                  resolve={(id) => placeOptionQuery(browserApi, id)}
                />
              </div>
            )}
            {shows("country_code") && countries.length > 1 && (
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
            {shows("administrative_level") && (
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
            )}
            {shows("institution_type") && (
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
            )}
            {shows("status") && (
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
            )}
            {shows("min_population") && shows("max_population") && (
              <PopulationRange
                min={minInput}
                max={maxInput}
                onMinChange={setMinInput}
                onMaxChange={setMaxInput}
              />
            )}
          </>
        }
        count={`${institutions.total} ${institutions.total === 1 ? "institution" : "institutions"}`}
        actions={actions?.({ ...chosen, ...fixed })}
        onClear={Object.values(chosen).some((value) => value !== undefined) ? clear : undefined}
      />
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
