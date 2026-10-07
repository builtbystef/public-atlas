import { createApiClient, type ApiClient, type Middleware } from "@public-atlas/api-client";

import { DATABASE_HEADER, readDatabaseCookie } from "./database";

/** Sends the database the `db` cookie chooses; see lib/api/database.ts. */
const databaseHeader: Middleware = {
  onRequest({ request }) {
    if (typeof document !== "undefined") {
      request.headers.set(DATABASE_HEADER, readDatabaseCookie(document.cookie));
    }
    return request;
  },
};

/**
 * The typed client for Client Components. It talks to `/api`, which next.config.ts rewrites to
 * the API, so the browser needs neither its address nor a CORS setup.
 */
export const browserApi: ApiClient = createApiClient({ baseUrl: "/api" });
browserApi.use(databaseHeader);
