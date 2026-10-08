import { z } from "zod";

import { institutionFilterShape, type InstitutionFilterValues } from "@/features/graph/schemas";

/**
 * A saved list is a named institutions query kept in this browser: the
 * filters of the institutions table, without its page or sort. It is a
 * query, not a set of rows, so what it shows follows the graph.
 */

const filtersSchema = z.object(institutionFilterShape);

export const savedListSchema = z.object({
  id: z.string().min(1),
  name: z.string().trim().min(1),
  description: z.string().trim().optional().catch(undefined),
  filters: filtersSchema.catch({}),
  createdAt: z.iso.datetime(),
  updatedAt: z.iso.datetime(),
});

export interface SavedList {
  id: string;
  name: string;
  description?: string | undefined;
  filters: InstitutionFilterValues;
  createdAt: string;
  updatedAt: string;
}

/** What a list's form edits: everything but its id and dates. */
export type SavedListInput = Pick<SavedList, "name" | "description" | "filters">;

/** The stored shape, versioned so a later change can read what an older console wrote. */
export const STORAGE_VERSION = 1;

const storedSchema = z.object({
  version: z.literal(STORAGE_VERSION),
  lists: z.array(z.unknown()),
});

/** Drops undefined entries, so equal filters are equal objects and equal query keys. */
export function cleanFilters(filters: InstitutionFilterValues): InstitutionFilterValues {
  return Object.fromEntries(
    Object.entries(filters).filter(([, value]) => value !== undefined && value !== ""),
  ) as InstitutionFilterValues;
}

function toSavedList(value: unknown): SavedList | null {
  const parsed = savedListSchema.safeParse(value);
  if (!parsed.success) return null;
  const { description, filters, ...rest } = parsed.data;
  return {
    ...rest,
    ...(description ? { description } : {}),
    filters: cleanFilters(filters),
  };
}

/**
 * The lists in a stored string, newest first. Anything unreadable is dropped
 * rather than rejected, so one bad entry, or a store written by hand, never
 * hides the rest.
 */
export function parseStoredLists(raw: string | null): SavedList[] {
  if (!raw) return [];
  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch {
    return [];
  }
  const stored = storedSchema.safeParse(json);
  if (!stored.success) return [];
  return sortLists(stored.data.lists.flatMap((value) => toSavedList(value) ?? []));
}

export function serializeLists(lists: SavedList[]): string {
  return JSON.stringify({ version: STORAGE_VERSION, lists });
}

/** Most recently changed first. */
export function sortLists(lists: SavedList[]): SavedList[] {
  return lists.toSorted((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export function addList(
  lists: SavedList[],
  input: SavedListInput,
  { id, now }: { id: string; now: string },
): { lists: SavedList[]; list: SavedList } {
  const list: SavedList = {
    id,
    name: input.name.trim(),
    ...(input.description?.trim() ? { description: input.description.trim() } : {}),
    filters: cleanFilters(input.filters),
    createdAt: now,
    updatedAt: now,
  };
  return { lists: sortLists([list, ...lists]), list };
}

export function replaceList(
  lists: SavedList[],
  id: string,
  input: SavedListInput,
  now: string,
): SavedList[] {
  return sortLists(
    lists.map((list) =>
      list.id === id
        ? {
            id: list.id,
            name: input.name.trim(),
            ...(input.description?.trim() ? { description: input.description.trim() } : {}),
            filters: cleanFilters(input.filters),
            createdAt: list.createdAt,
            updatedAt: now,
          }
        : list,
    ),
  );
}

export function removeList(lists: SavedList[], id: string): SavedList[] {
  return lists.filter((list) => list.id !== id);
}

/**
 * Lists from an exported file merged into these: an imported list replaces
 * the one with its id when it is newer, and is added otherwise. Returns how
 * many it took, so the console can say so.
 */
export function mergeLists(
  lists: SavedList[],
  raw: string,
): { lists: SavedList[]; imported: number } | null {
  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!storedSchema.safeParse(json).success) return null;
  const incoming = parseStoredLists(raw);
  const byId = new Map(lists.map((list) => [list.id, list]));
  let imported = 0;
  for (const list of incoming) {
    const current = byId.get(list.id);
    if (current && current.updatedAt >= list.updatedAt) continue;
    byId.set(list.id, list);
    imported += 1;
  }
  return { lists: sortLists([...byId.values()]), imported };
}

// The form. Every control holds text; the schema turns it into filters.

const populationText = z
  .string()
  .trim()
  .refine((value) => value === "" || /^\d+$/.test(value), "A whole number, or empty");

export const savedListFormSchema = z
  .object({
    name: z.string().trim().min(1, "Give the list a name").max(120, "At most 120 characters"),
    description: z.string().trim().max(500, "At most 500 characters"),
    q: z.string(),
    country_code: z.string(),
    place_id: z.string(),
    administrative_level: z.string(),
    institution_type: z.string(),
    status: z.string(),
    min_population: populationText,
    max_population: populationText,
  })
  .refine(
    ({ min_population: min, max_population: max }) =>
      min === "" || max === "" || Number(min) <= Number(max),
    { path: ["max_population"], message: "At least the smallest population" },
  );

export type SavedListFormInput = z.input<typeof savedListFormSchema>;

/** The form's text for a list, or for the filters a new list starts from. */
export function toFormValues(
  list: Pick<SavedList, "filters"> & Partial<SavedListInput>,
): SavedListFormInput {
  const { filters } = list;
  return {
    name: list.name ?? "",
    description: list.description ?? "",
    q: filters.q ?? "",
    country_code: filters.country_code ?? "",
    place_id: filters.place_id ?? "",
    administrative_level: filters.administrative_level ?? "",
    institution_type: filters.institution_type ?? "",
    status: filters.status ?? "",
    min_population: filters.min_population?.toString() ?? "",
    max_population: filters.max_population?.toString() ?? "",
  };
}

/** A submitted form as a list's name, description and filters. */
export function fromFormValues(values: SavedListFormInput): SavedListInput {
  const { name, description, ...filters } = values;
  // An empty control is no filter; read through the URL schema so a list holds what a URL can.
  const present = Object.fromEntries(
    Object.entries(filters)
      .map(([key, value]) => [key, value.trim()])
      .filter(([, value]) => value !== ""),
  );
  return {
    name: name.trim(),
    description: description.trim() || undefined,
    filters: cleanFilters(filtersSchema.parse(present)),
  };
}

/** "Pop. 10,000–50,000", "Pop. ≥ 10,000" or "Pop. ≤ 50,000"; null without a bound. */
export function describePopulation(min: number | undefined, max: number | undefined) {
  const count = new Intl.NumberFormat("en-US");
  if (min !== undefined && max !== undefined) {
    return `Pop. ${count.format(min)}–${count.format(max)}`;
  }
  if (min !== undefined) return `Pop. ≥ ${count.format(min)}`;
  if (max !== undefined) return `Pop. ≤ ${count.format(max)}`;
  return null;
}
