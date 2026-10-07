import "server-only";

import type { ApiClient } from "@public-atlas/api-client";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";

import { ApiError, unwrap } from "./errors";
import { DATABASE_COOKIE, parseDatabase, type Database } from "./database";
import { createApi } from "./server-client";

/** The database the `db` cookie chooses for this request; the live one by default. */
export async function getDatabase(): Promise<Database> {
  return parseDatabase((await cookies()).get(DATABASE_COOKIE)?.value);
}

/** The server-side API client for this request, reading the database its cookie chooses. */
export async function getApi(): Promise<ApiClient> {
  return createApi(globalThis.fetch, await getDatabase());
}

/** The shape openapi-fetch returns from every request. */
interface ApiResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** `unwrap`, except that a 404 renders the nearest not-found page instead of the error page. */
export function unwrapOrNotFound<T>(result: ApiResult<T>): T {
  try {
    return unwrap(result);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
}
