import type { SortingState } from "@tanstack/react-table";
import { useState } from "react";

import type { ListSearch, SortOrder } from "@/lib/lists";

/**
 * Page and sort of a list whose rows the API pages. The page belongs to the
 * filters it was reached with: when `filterKey` changes, the list is back on
 * page 1, without an effect. The sort survives a filter change.
 *
 * The API's default order is "no sort" in the URL and the query key, so a
 * sort equal to `defaultSort` is stored as absent.
 */
export function useListState<S extends string>({
  filterKey,
  initial,
  defaultSort,
}: {
  filterKey: string;
  initial: ListSearch<S>;
  defaultSort: { sort: S; order: SortOrder };
}) {
  const [state, setState] = useState({
    key: filterKey,
    page: initial.page ?? 1,
    sort: initial.sort,
    order: initial.order,
  });
  const page = state.key === filterKey ? state.page : 1;

  const sorting: SortingState = [
    {
      id: state.sort ?? defaultSort.sort,
      desc: (state.order ?? (state.sort ? "asc" : defaultSort.order)) === "desc",
    },
  ];

  return {
    /** 1-based. */
    page,
    /** The table's view of the sort; always one column. */
    sorting,
    /** What goes in the URL and the query key. */
    search: {
      page: page > 1 ? page : undefined,
      sort: state.sort,
      order: state.order,
    } satisfies ListSearch<S>,
    setPage: (next: number) => setState((s) => ({ ...s, key: filterKey, page: next })),
    setSorting: (next: SortingState) => {
      const [first] = next;
      const sort = (first?.id as S | undefined) ?? defaultSort.sort;
      const order: SortOrder = first?.desc ? "desc" : "asc";
      const isDefault = sort === defaultSort.sort && order === defaultSort.order;
      setState({
        key: filterKey,
        page: 1,
        sort: isDefault ? undefined : sort,
        order: isDefault ? undefined : order,
      });
    },
  };
}
