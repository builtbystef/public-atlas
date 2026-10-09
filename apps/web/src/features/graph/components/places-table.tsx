"use client";

import type { CountryOutput, PlaceOutput } from "@public-atlas/api-client";
import { useSuspenseQuery } from "@tanstack/react-query";
import { SearchIcon } from "lucide-react";
import { useState } from "react";

import { OptionSelect } from "@/components/shared/option-select";
import { DataTable } from "@/components/shared/data-table";
import { EntityCombobox } from "@/components/shared/entity-combobox";
import { TableToolbar } from "@/components/shared/table-toolbar";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useListState } from "@/hooks/use-list-state";
import { useUrlFilters } from "@/hooks/use-url-filters";
import { browserApi } from "@/lib/api/client";
import { humanize } from "@/lib/labels";
import { cn } from "@/lib/utils";

import { placeListQuery, placeOptionQuery, placePickerQuery, placeTableFilters } from "../queries";
import { parsePlaceSearch, type PlaceSearch } from "../schemas";
import { placeColumns } from "./place-columns";
import { PopulationRange, populationBound } from "./population-range";

const SEARCH_DEBOUNCE_MS = 250;

/**
 * Places by name, level, parent and population, each a link to its page and
 * the institutions under it. On a place's own page it lists the places
 * directly under that one, with `parentPlaceId` fixed and the URL left to the
 * page's institutions.
 */
export function PlacesTable({
  initialFilters,
  parentPlaceId,
  countries,
}: {
  initialFilters: PlaceSearch;
  parentPlaceId?: string;
  /** Every country with its levels, for the country and level filters. */
  countries: CountryOutput[];
}) {
  const nested = parentPlaceId !== undefined;
  const [input, setInput] = useState(initialFilters.q ?? "");
  const q = useDebouncedValue(input.trim(), SEARCH_DEBOUNCE_MS);
  const [countryCode, setCountryCode] = useState(initialFilters.country_code ?? "");
  const [parentId, setParentId] = useState(initialFilters.parent_place_id ?? "");
  const [level, setLevel] = useState(initialFilters.administrative_level ?? "");
  const [minInput, setMinInput] = useState(initialFilters.min_population?.toString() ?? "");
  const [maxInput, setMaxInput] = useState(initialFilters.max_population?.toString() ?? "");
  const minPopulation = populationBound(useDebouncedValue(minInput, SEARCH_DEBOUNCE_MS));
  const maxPopulation = populationBound(useDebouncedValue(maxInput, SEARCH_DEBOUNCE_MS));

  const chosen = {
    q: q || undefined,
    country_code: nested ? undefined : countryCode || undefined,
    parent_place_id: nested ? undefined : parentId || undefined,
    administrative_level: level || undefined,
    min_population: minPopulation,
    max_population: maxPopulation,
  };
  const list = useListState({
    filterKey: JSON.stringify(chosen),
    initial: initialFilters,
    defaultSort: { sort: "name", order: "asc" },
  });
  const { deferred, isStale } = useUrlFilters({ ...chosen, ...list.search }, parsePlaceSearch, {
    sync: !nested,
  });
  const { data: places } = useSuspenseQuery(
    placeListQuery(
      browserApi,
      placeTableFilters(deferred, nested ? { parent_place_id: parentPlaceId } : {}),
    ),
  );

  const levels = countries
    .filter((c) => !countryCode || c.settings.country_code === countryCode)
    .flatMap((c) => c.administrative_levels.toSorted((a, b) => a.rank - b.rank))
    .map((l) => l.name);
  const levelOptions = [...new Set(levels)];
  const filtered = Object.values(chosen).some((value) => value !== undefined);
  const clear = () => {
    setInput("");
    setCountryCode("");
    setParentId("");
    setLevel("");
    setMinInput("");
    setMaxInput("");
  };

  return (
    <div className="flex flex-col gap-4">
      <TableToolbar
        search={
          <InputGroup>
            <InputGroupAddon>
              <SearchIcon />
            </InputGroupAddon>
            <InputGroupInput
              type="search"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Name or alias"
              aria-label="Search places"
            />
          </InputGroup>
        }
        filters={
          <>
            {!nested && (
              <div className="w-56">
                <EntityCombobox
                  id="parent-filter"
                  name="parent_place_id"
                  value={parentId}
                  onValueChange={setParentId}
                  placeholder="Directly under any place"
                  search={(text) => placePickerQuery(browserApi, text, countryCode || undefined)}
                  resolve={(id) => placeOptionQuery(browserApi, id)}
                />
              </div>
            )}
            {!nested && countries.length > 1 && (
              <OptionSelect
                value={countryCode}
                onValueChange={setCountryCode}
                aria-label="Filter by country"
                options={[
                  { value: "", label: "Any country" },
                  ...countries.map((c) => ({
                    value: c.settings.country_code,
                    label: c.settings.name,
                  })),
                ]}
              />
            )}
            <OptionSelect
              value={level}
              onValueChange={setLevel}
              aria-label="Filter by administrative level"
              options={[
                { value: "", label: "Any level" },
                ...levelOptions.map((name) => ({ value: name, label: humanize(name) })),
              ]}
            />
            <PopulationRange
              idPrefix={nested ? "child-population" : "population"}
              min={minInput}
              max={maxInput}
              onMinChange={setMinInput}
              onMaxChange={setMaxInput}
            />
          </>
        }
        count={`${places.total} ${places.total === 1 ? "place" : "places"}`}
        onClear={filtered ? clear : undefined}
      />
      <DataTable<PlaceOutput>
        columns={placeColumns({ showCountry: !nested && countries.length > 1 })}
        data={places.items}
        total={places.total}
        page={list.page}
        onPageChange={list.setPage}
        sorting={list.sorting}
        onSortingChange={list.setSorting}
        emptyMessage={
          filtered
            ? "No places match these filters."
            : nested
              ? "No places under this one."
              : "No places yet. Seed a country and load a list."
        }
        className={cn(isStale && "opacity-60 transition-opacity")}
      />
    </div>
  );
}
