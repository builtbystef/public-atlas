"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { TIME_ZONE_COOKIE } from "@/lib/time-zone/cookie";

/**
 * Tells the server which zone the browser is in. The server reads the cookie
 * (see lib/time-zone/server.ts) for the API's `tz` parameter and for every date it
 * renders; until the cookie exists it assumes UTC, so the first visit
 * re-renders once with the right zone.
 */
export function TimeZoneSync({ serverTimeZone }: { serverTimeZone: string }) {
  const router = useRouter();
  useEffect(() => {
    const browserTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (browserTimeZone && browserTimeZone !== serverTimeZone) {
      document.cookie = `${TIME_ZONE_COOKIE}=${encodeURIComponent(browserTimeZone)}; path=/; max-age=31536000; samesite=lax`;
      router.refresh();
    }
  }, [router, serverTimeZone]);
  return null;
}
