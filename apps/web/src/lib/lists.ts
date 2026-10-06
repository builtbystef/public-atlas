import { z } from "zod";

/**
 * Every list the API serves is a page: `{ items, total, limit, offset }`. The
 * tables ask for a page at a time and let the total drive the pager. Feeds
 * and pickers that show everything ask for the largest page the API allows
 * and say so when there was more.
 *
 * A paged list lives in the URL as `?page=&sort=&order=` plus its own
 * filters. This module is the two halves of that: reading a list's position
 * out of the URL, and turning it into the API's `limit`/`offset`.
 */

/** Rows per page in the tables. */
export const PAGE_SIZE = 50;

/** The largest page the API serves, for lists that want every row. */
export const ALL_ROWS = { limit: 500, offset: 0 } as const;

/** What a picker shows per search: enough to scan, few enough to be quick. */
export const PICKER_ROWS = { limit: 20, offset: 0 } as const;

export const sortOrders = ["asc", "desc"] as const;

/** The API's `order` parameter on every sorted list. */
export type SortOrder = (typeof sortOrders)[number];

export interface ListPage {
  limit: number;
  offset: number;
}

/** The API's `limit` and `offset` for a 1-based page number. */
export function listPage(page: number | undefined, pageSize = PAGE_SIZE): ListPage {
  return { limit: pageSize, offset: ((page ?? 1) - 1) * pageSize };
}

/** The page and sort part of a list's search, on its own. */
export interface ListSearch<S extends string> {
  page?: number | undefined;
  sort?: S | undefined;
  order?: SortOrder | undefined;
}

/**
 * API list parameters for a parsed URL search: `page` becomes `limit` and
 * `offset`; `sort` and `order` pass through. Server prefetch and client
 * query must build the same key, so both go through here.
 */
export function paged<S extends string, T extends ListSearch<S>>({
  page,
  ...filters
}: T): Omit<T, "page"> & ListPage {
  return { ...filters, ...listPage(page) };
}

/** Drops undefined entries, which openapi-fetch would otherwise serialize. */
export function queryParams<T extends object>(
  filters: T,
): { [K in keyof T]?: Exclude<T[K], undefined> } {
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== undefined)) as {
    [K in keyof T]?: Exclude<T[K], undefined>;
  };
}

// URL search params. Anything unexpected is dropped rather than rejected,
// so a stale link still shows the list.

export type SearchParams = Record<string, string | string[] | undefined>;

/** A search param that is absent, or valid, or ignored. */
export const optionalParam = <T extends z.ZodType>(schema: T) => schema.optional().catch(undefined);

/**
 * Where a paged list is: `page` (the first page is the URL without one, so
 * equal views build equal URLs and query keys), and the column and direction
 * it is sorted by (absent means the API's default order).
 */
export const listSearch = <S extends readonly [string, ...string[]]>(sorts: S) => ({
  page: optionalParam(z.coerce.number().int().min(2)),
  sort: optionalParam(z.enum(sorts)),
  order: optionalParam(z.enum(sortOrders)),
});

/**
 * Parse a list's search params with `schema`, from either Next's
 * `searchParams` or a `URLSearchParams`. Undefined values are stripped so
 * equal filters produce equal query keys.
 */
export function parseSearch<T extends object>(
  schema: z.ZodType<T>,
  params: SearchParams | URLSearchParams,
): T {
  const record = params instanceof URLSearchParams ? Object.fromEntries(params) : params;
  const value = schema.parse(record);
  return Object.fromEntries(Object.entries(value).filter(([, v]) => v !== undefined)) as T;
}

/** The query string for a filter object, without empty values. */
export function toSearchString(filters: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  return params.toString();
}
