// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { expect, test } from "vite-plus/test";

import { useListState } from "./use-list-state";

const DEFAULT_SORT = { sort: "created_at", order: "desc" } as const;

test("a filter change returns to page 1 but keeps the sort", () => {
  const { result, rerender } = renderHook(
    ({ filterKey }) =>
      useListState({ filterKey, initial: { page: 3, sort: "name" }, defaultSort: DEFAULT_SORT }),
    { initialProps: { filterKey: "q=oak" } },
  );
  expect(result.current.page).toBe(3);
  expect(result.current.search).toEqual({ page: 3, sort: "name", order: undefined });

  rerender({ filterKey: "q=elm" });

  expect(result.current.page).toBe(1);
  expect(result.current.search).toEqual({ page: undefined, sort: "name", order: undefined });
  expect(result.current.sorting).toEqual([{ id: "name", desc: false }]);
});

test("a page set after a filter change belongs to the new filters", () => {
  const { result, rerender } = renderHook(
    ({ filterKey }) => useListState({ filterKey, initial: {}, defaultSort: DEFAULT_SORT }),
    { initialProps: { filterKey: "q=oak" } },
  );
  rerender({ filterKey: "q=elm" });
  act(() => result.current.setPage(2));
  expect(result.current.page).toBe(2);
  expect(result.current.search.page).toBe(2);
  // Back to the first filters: they are new again, so page 1.
  rerender({ filterKey: "q=oak" });
  expect(result.current.page).toBe(1);
});

test("the default sort is stored as absent, and any other sort goes to page 1", () => {
  const { result } = renderHook(() =>
    useListState({ filterKey: "", initial: { page: 2 }, defaultSort: DEFAULT_SORT }),
  );
  expect(result.current.sorting).toEqual([{ id: "created_at", desc: true }]);

  act(() => result.current.setSorting([{ id: "name", desc: true }]));
  expect(result.current.search).toEqual({ page: undefined, sort: "name", order: "desc" });
  expect(result.current.sorting).toEqual([{ id: "name", desc: true }]);

  act(() => result.current.setSorting([{ id: "created_at", desc: true }]));
  expect(result.current.search).toEqual({ page: undefined, sort: undefined, order: undefined });
  expect(result.current.sorting).toEqual([{ id: "created_at", desc: true }]);

  // The default column in the other direction is a sort of its own.
  act(() => result.current.setSorting([{ id: "created_at", desc: false }]));
  expect(result.current.search).toEqual({ page: undefined, sort: "created_at", order: "asc" });
});

test("a sort without an order reads ascending, and clearing the sort is the default column ascending", () => {
  const { result } = renderHook(() =>
    useListState({ filterKey: "", initial: { sort: "name" }, defaultSort: DEFAULT_SORT }),
  );
  expect(result.current.sorting).toEqual([{ id: "name", desc: false }]);
  act(() => result.current.setSorting([]));
  // The default sort is descending, so ascending on its column is a sort of its own.
  expect(result.current.search).toEqual({ page: undefined, sort: "created_at", order: "asc" });
  expect(result.current.sorting).toEqual([{ id: "created_at", desc: false }]);
});
