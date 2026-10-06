import { assertApiUrl } from "@/lib/api/server-client";

/**
 * Runs once when the server starts, before it serves a request. Environment that can be wrong
 * is checked here so a bad deploy fails at boot, not on the first request that needs it.
 */
export function register(): void {
  assertApiUrl();
}
