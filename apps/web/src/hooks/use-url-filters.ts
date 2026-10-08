import { useDeferredValue, useEffect } from "react";

import { toSearchString } from "@/lib/lists";

/**
 * Keeps the address bar in sync with client-side filters without a server
 * round trip: `history.replaceState` integrates with the Next.js router, and
 * the deferred copy lets `useSuspenseQuery` keep showing the previous rows
 * while the next filter's data loads. With `sync: false` the filters stay in
 * the component, for a second list on a page whose URL belongs to another.
 */
export function useUrlFilters<T extends Record<string, string | number | undefined>>(
  filters: T,
  parse: (params: URLSearchParams) => T,
  { sync = true }: { sync?: boolean } = {},
): { deferred: T; isStale: boolean } {
  const search = toSearchString(filters);
  const deferredSearch = useDeferredValue(search);

  useEffect(() => {
    if (!sync) return;
    const url = search ? `${window.location.pathname}?${search}` : window.location.pathname;
    if (url !== window.location.pathname + window.location.search) {
      window.history.replaceState(null, "", url);
    }
  }, [search, sync]);

  return {
    deferred: parse(new URLSearchParams(deferredSearch)),
    isStale: search !== deferredSearch,
  };
}
