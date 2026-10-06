import { useDeferredValue, useEffect } from "react";

import { toSearchString } from "@/lib/lists";

/**
 * Keeps the address bar in sync with client-side filters without a server
 * round trip: `history.replaceState` integrates with the Next.js router, and
 * the deferred copy lets `useSuspenseQuery` keep showing the previous rows
 * while the next filter's data loads.
 */
export function useUrlFilters<T extends Record<string, string | number | undefined>>(
  filters: T,
  parse: (params: URLSearchParams) => T,
): { deferred: T; isStale: boolean } {
  const search = toSearchString(filters);
  const deferredSearch = useDeferredValue(search);

  useEffect(() => {
    const url = search ? `${window.location.pathname}?${search}` : window.location.pathname;
    if (url !== window.location.pathname + window.location.search) {
      window.history.replaceState(null, "", url);
    }
  }, [search]);

  return {
    deferred: parse(new URLSearchParams(deferredSearch)),
    isStale: search !== deferredSearch,
  };
}
