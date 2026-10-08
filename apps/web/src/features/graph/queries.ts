import type { ApiClient, EntityStatus } from "@public-atlas/api-client";
import { queryOptions } from "@tanstack/react-query";

import type { EntityOption } from "@/components/shared/entity-combobox";
import { unwrap } from "@/lib/api/errors";
import { humanize } from "@/lib/labels";
import { paged, PICKER_ROWS, queryParams, type ListPage, type SortOrder } from "@/lib/lists";

import type {
  InstitutionFilterValues,
  InstitutionSearch,
  InstitutionSort,
  PlaceSearch,
  PlaceSort,
} from "./schemas";

export interface InstitutionListFilters extends ListPage {
  q?: string | undefined;
  country_code?: string | undefined;
  place_id?: string | undefined;
  administrative_level?: string | undefined;
  institution_type?: string | undefined;
  status?: EntityStatus | undefined;
  parent_institution_id?: string | undefined;
  min_population?: number | undefined;
  max_population?: number | undefined;
  sort?: InstitutionSort | undefined;
  order?: SortOrder | undefined;
}

export interface PlaceListFilters extends ListPage {
  q?: string | undefined;
  country_code?: string | undefined;
  administrative_level?: string | undefined;
  parent_place_id?: string | undefined;
  min_population?: number | undefined;
  max_population?: number | undefined;
  sort?: PlaceSort | undefined;
  order?: SortOrder | undefined;
}

export const graphKeys = {
  all: ["graph"] as const,
  institutions: (filters: InstitutionListFilters) =>
    [...graphKeys.all, "institutions", filters] as const,
  institution: (id: string) => [...graphKeys.all, "institution", id] as const,
  places: (filters: PlaceListFilters) => [...graphKeys.all, "places", filters] as const,
  place: (id: string) => [...graphKeys.all, "place", id] as const,
  subjects: (country: string | undefined, q: string) =>
    [...graphKeys.all, "subjects", country ?? "", q] as const,
  subject: (id: string) => [...graphKeys.all, "subject", id] as const,
  evidenceContext: (id: string) => [...graphKeys.all, "evidence-context", id] as const,
};

/**
 * The list an institutions table asks for: its URL search with the filters
 * the page holds fixed on top. Server prefetch and the table build the same
 * key through here.
 */
export function institutionTableFilters(
  search: InstitutionSearch,
  fixed: InstitutionFilterValues = {},
): InstitutionListFilters {
  return paged({ ...search, ...fixed });
}

/** The list a places table asks for, likewise. */
export function placeTableFilters(
  search: PlaceSearch,
  fixed: Pick<PlaceListFilters, "parent_place_id"> = {},
): PlaceListFilters {
  return paged({ ...search, ...fixed });
}

export function institutionListQuery(api: ApiClient, filters: InstitutionListFilters) {
  return queryOptions({
    queryKey: graphKeys.institutions(filters),
    queryFn: async () =>
      unwrap(await api.GET("/institutions", { params: { query: queryParams(filters) } })),
  });
}

export function institutionQuery(api: ApiClient, id: string) {
  return queryOptions({
    queryKey: graphKeys.institution(id),
    queryFn: async () =>
      unwrap(
        await api.GET("/institutions/{institution_id}", {
          params: { path: { institution_id: id } },
        }),
      ),
  });
}

export function placeListQuery(api: ApiClient, filters: PlaceListFilters) {
  return queryOptions({
    queryKey: graphKeys.places(filters),
    queryFn: async () =>
      unwrap(await api.GET("/places", { params: { query: queryParams(filters) } })),
  });
}

/** How many institutions match, without their rows: a saved list's count. */
export function institutionCountQuery(
  api: ApiClient,
  filters: Omit<InstitutionListFilters, keyof ListPage>,
) {
  return queryOptions({
    ...institutionListQuery(api, { ...filters, limit: 1, offset: 0 }),
    select: (page) => page.total,
  });
}

export function placeQuery(api: ApiClient, id: string) {
  return queryOptions({
    queryKey: graphKeys.place(id),
    queryFn: async () =>
      unwrap(await api.GET("/places/{place_id}", { params: { path: { place_id: id } } })),
  });
}

/** The place picker's matches: places by name, with their level. */
export function placePickerQuery(api: ApiClient, q: string, countryCode?: string) {
  const filters = { q: q || undefined, country_code: countryCode, ...PICKER_ROWS };
  return queryOptions({
    queryKey: [...graphKeys.places(filters), "picker"] as const,
    queryFn: async (): Promise<{ items: EntityOption[]; total: number }> => {
      const page = unwrap(await api.GET("/places", { params: { query: queryParams(filters) } }));
      return {
        items: page.items.map((p) => ({
          id: p.id,
          name: p.name,
          detail: humanize(p.administrative_level),
        })),
        total: page.total,
      };
    },
  });
}

/** The option behind a place id, so the picker can show a name for it. */
export function placeOptionQuery(api: ApiClient, id: string) {
  return queryOptions({
    queryKey: [...graphKeys.place(id), "option"] as const,
    queryFn: async (): Promise<EntityOption> => {
      const place = unwrap(
        await api.GET("/places/{place_id}", { params: { path: { place_id: id } } }),
      );
      return { id: place.id, name: place.name, detail: humanize(place.administrative_level) };
    },
  });
}

/** The institution picker's matches (a merge target, say): institutions by name or alias. */
export function institutionPickerQuery(api: ApiClient, q: string, countryCode?: string) {
  const filters = { q: q || undefined, country_code: countryCode, ...PICKER_ROWS };
  return queryOptions({
    queryKey: [...graphKeys.institutions(filters), "picker"] as const,
    queryFn: async (): Promise<{ items: EntityOption[]; total: number }> => {
      const page = unwrap(
        await api.GET("/institutions", { params: { query: queryParams(filters) } }),
      );
      return {
        items: page.items.map((i) => ({
          id: i.id,
          name: i.name,
          detail: `${humanize(i.institution_type)} · ${i.place.name}`,
        })),
        total: page.total,
      };
    },
  });
}

export function institutionOptionQuery(api: ApiClient, id: string) {
  return queryOptions({
    queryKey: [...graphKeys.institution(id), "option"] as const,
    queryFn: async (): Promise<EntityOption> => {
      const institution = unwrap(
        await api.GET("/institutions/{institution_id}", {
          params: { path: { institution_id: id } },
        }),
      );
      return {
        id: institution.id,
        name: institution.name,
        detail: `${humanize(institution.institution_type)} · ${institution.place.name}`,
      };
    },
  });
}

/** A run's subjects: places and institutions of a country, by name. */
export function subjectPickerQuery(api: ApiClient, q: string, countryCode?: string) {
  const filters = { q: q || undefined, country_code: countryCode, ...PICKER_ROWS };
  return queryOptions({
    queryKey: graphKeys.subjects(countryCode, q),
    queryFn: async (): Promise<{ items: EntityOption[]; total: number }> => {
      const [places, institutions] = await Promise.all([
        api.GET("/places", { params: { query: queryParams(filters) } }),
        api.GET("/institutions", { params: { query: queryParams(filters) } }),
      ]);
      const p = unwrap(places);
      const i = unwrap(institutions);
      return {
        items: [
          ...p.items.map((place) => ({
            id: place.id,
            name: place.name,
            detail: `Place · ${humanize(place.administrative_level)}`,
          })),
          ...i.items.map((institution) => ({
            id: institution.id,
            name: institution.name,
            detail: `Institution · ${humanize(institution.institution_type)}`,
          })),
        ],
        total: p.total + i.total,
      };
    },
  });
}

/** The option behind a subject id of either kind. */
export function subjectOptionQuery(api: ApiClient, id: string) {
  return queryOptions({
    queryKey: graphKeys.subject(id),
    queryFn: async (): Promise<EntityOption> => {
      const place = await api.GET("/places/{place_id}", { params: { path: { place_id: id } } });
      if (place.response.ok && place.data) {
        return {
          id,
          name: place.data.name,
          detail: `Place · ${humanize(place.data.administrative_level)}`,
        };
      }
      const institution = unwrap(
        await api.GET("/institutions/{institution_id}", {
          params: { path: { institution_id: id } },
        }),
      );
      return {
        id,
        name: institution.name,
        detail: `Institution · ${humanize(institution.institution_type)}`,
      };
    },
  });
}

/** The stored text around an evidence quote, for the highlighted view. */
export function evidenceContextQuery(api: ApiClient, evidenceId: string) {
  return queryOptions({
    queryKey: graphKeys.evidenceContext(evidenceId),
    queryFn: async () =>
      unwrap(
        await api.GET("/evidence/{evidence_id}/context", {
          params: { path: { evidence_id: evidenceId } },
        }),
      ),
    staleTime: Infinity,
  });
}
