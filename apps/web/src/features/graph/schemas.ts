import { z } from "zod";

import { entityStatuses } from "@/lib/labels";
import { listSearch, optionalParam, parseSearch, type SearchParams } from "@/lib/lists";

export const institutionSorts = [
  "name",
  "institution_type",
  "status",
  "created_at",
  "place",
  "population",
] as const;

export type InstitutionSort = (typeof institutionSorts)[number];

/** A population bound: a whole number of people, zero or more. */
const population = optionalParam(z.coerce.number().int().min(0));

/**
 * What narrows a list of institutions, without its page or sort: the part a
 * saved list keeps (features/saved-lists).
 */
export const institutionFilterShape = {
  q: optionalParam(z.string().trim().min(1)),
  country_code: optionalParam(z.string().trim().min(1)),
  place_id: optionalParam(z.uuid()),
  administrative_level: optionalParam(z.string().trim().min(1)),
  institution_type: optionalParam(z.string().trim().min(1)),
  status: optionalParam(z.enum(entityStatuses)),
  min_population: population,
  max_population: population,
};

const institutionSearchSchema = z.object({
  ...institutionFilterShape,
  ...listSearch(institutionSorts),
});

export type InstitutionSearch = z.output<typeof institutionSearchSchema>;

/** The filters of an institutions list, without its page or sort. */
export type InstitutionFilterValues = Omit<InstitutionSearch, "page" | "sort" | "order">;

export function parseInstitutionSearch(params: SearchParams | URLSearchParams): InstitutionSearch {
  return parseSearch(institutionSearchSchema, params);
}

export const placeSorts = ["name", "administrative_level", "population"] as const;

export type PlaceSort = (typeof placeSorts)[number];

const placeSearchSchema = z.object({
  q: optionalParam(z.string().trim().min(1)),
  country_code: optionalParam(z.string().trim().min(1)),
  administrative_level: optionalParam(z.string().trim().min(1)),
  parent_place_id: optionalParam(z.uuid()),
  min_population: population,
  max_population: population,
  ...listSearch(placeSorts),
});

export type PlaceSearch = z.output<typeof placeSearchSchema>;

export function parsePlaceSearch(params: SearchParams | URLSearchParams): PlaceSearch {
  return parseSearch(placeSearchSchema, params);
}
