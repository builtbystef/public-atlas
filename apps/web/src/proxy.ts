import { NextResponse, type NextRequest } from "next/server";

import { getApiUrl } from "@/lib/api/server-client";

/**
 * The browser reaches the API through `/api/*` on this same origin, so it needs neither the
 * API's address nor a CORS setup. The address is read on every request, not fixed at build
 * time as a `next.config.ts` rewrite would be, so one build serves any `API_URL`. The API's
 * routes have no trailing slash (a rewrite would drop one), and it does not redirect on a
 * missing or extra slash.
 */
export function proxy(request: NextRequest): NextResponse {
  const { pathname, search } = request.nextUrl;
  const target = new URL(getApiUrl());
  target.pathname = `${target.pathname.replace(/\/$/, "")}${pathname.slice("/api".length)}`;
  target.search = search;
  return NextResponse.rewrite(target);
}

export const config = {
  matcher: "/api/:path*",
};
