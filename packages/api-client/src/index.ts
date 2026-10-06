import createClient, { type ClientOptions } from "openapi-fetch";

import type { paths } from "./generated/schema";

export type * from "./generated/schema";

export type ApiClient = ReturnType<typeof createClient<paths>>;

/**
 * Create a client whose methods are typed against the API's OpenAPI schema:
 * paths, parameters, request bodies, and responses are all checked.
 *
 * @example
 * const api = createApiClient({ baseUrl: "http://127.0.0.1:8000" });
 * const { data, error } = await api.GET("/health");
 */
export function createApiClient(options: ClientOptions = {}): ApiClient {
  return createClient<paths>(options);
}

export { default as createClient } from "openapi-fetch";
export type { ClientOptions, Middleware } from "openapi-fetch";
