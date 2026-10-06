import { createApiClient, type ApiClient } from "@public-atlas/api-client";

/**
 * The typed client for Client Components. It talks to `/api`, which next.config.ts rewrites to
 * the API, so the browser needs neither its address nor a CORS setup.
 */
export const browserApi: ApiClient = createApiClient({ baseUrl: "/api" });
