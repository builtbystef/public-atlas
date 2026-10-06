import "server-only";

import { cookies } from "next/headers";

import { isTimeZone, TIME_ZONE_COOKIE } from "./cookie";

/**
 * The IANA time zone that defines "today" for the user, from the cookie that
 * <TimeZoneSync> sets in the browser; UTC until then. Passed to the API's
 * `tz` parameter and used for every date shown, on the server and the client
 * alike, so the two render the same text.
 */
export async function getTimeZone(): Promise<string> {
  const value = (await cookies()).get(TIME_ZONE_COOKIE)?.value;
  return value && isTimeZone(value) ? value : "UTC";
}
