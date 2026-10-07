import { createApiClient, type ApiClient } from "@public-atlas/api-client";

import { DATABASE_HEADER, type Database } from "./database";

const DEV_API_URL = "http://127.0.0.1:8000";

/**
 * Where the API lives. Read from the server-side environment, so it is never inlined into the
 * browser bundle. Falls back to the local dev server; `assertApiUrl` stops a production deploy
 * from doing that silently.
 */
export function getApiUrl(): string {
  return process.env["API_URL"] ?? DEV_API_URL;
}

/**
 * Throws when a production server has no `API_URL`: without it every request would go to
 * localhost and fail one at a time. Run at startup.
 */
export function assertApiUrl(): void {
  if (process.env.NODE_ENV === "production" && !process.env["API_URL"]) {
    throw new Error("API_URL is not set; the web app cannot reach the API in production");
  }
}

/**
 * The typed client for apps/server, for use in Server Components, Route Handlers and Server
 * Actions, reading `database` (see lib/api/database.ts). Requests are memoized per render by
 * Next.js's `fetch`, so calling this in several components costs one request. Pages get one
 * through `getApi()` in lib/api/server.ts, which reads the database cookie.
 */
export function createApi(
  fetch: typeof globalThis.fetch = globalThis.fetch,
  database: Database = "main",
): ApiClient {
  return createApiClient({
    baseUrl: getApiUrl(),
    fetch,
    headers: { [DATABASE_HEADER]: database },
  });
}
