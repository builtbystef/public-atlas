// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vite-plus/test";

import { savedListActions, useSavedList, useSavedLists } from "./store";

const MAIN_KEY = "public-atlas:saved-lists:v1:main";
const EVAL_KEY = "public-atlas:saved-lists:v1:eval";

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

test("a list saved in one database is not a list of the other", () => {
  const { result } = renderHook(() => ({
    main: useSavedLists("main"),
    eval: useSavedLists("eval"),
  }));
  expect(result.current).toEqual({ main: [], eval: [] });

  let created: ReturnType<ReturnType<typeof savedListActions>["create"]>;
  act(() => {
    created = savedListActions("eval").create({
      name: " Libraries ",
      description: "",
      filters: { institution_type: "library", q: "" },
    });
  });

  expect(result.current.main).toEqual([]);
  expect(result.current.eval).toEqual([
    {
      id: created!.id,
      name: "Libraries",
      filters: { institution_type: "library" },
      createdAt: created!.createdAt,
      updatedAt: created!.updatedAt,
    },
  ]);
  expect(JSON.parse(window.localStorage.getItem(EVAL_KEY)!)).toEqual({
    version: 1,
    lists: [created!],
  });
  expect(window.localStorage.getItem(MAIN_KEY)).toBeNull();
});

test("the lists keep their identity while nothing changed, and change when a list does", () => {
  const { result, rerender } = renderHook(() => useSavedLists("main"));
  const before = result.current;
  rerender();
  expect(result.current).toBe(before);

  let id = "";
  act(() => {
    id = savedListActions("main").create({ name: "Schools", filters: {} }).id;
  });
  const created = result.current;
  expect(created).not.toBe(before);
  expect(created?.map((list) => list.name)).toEqual(["Schools"]);
  rerender();
  expect(result.current).toBe(created);

  act(() => {
    savedListActions("main").update(id, { name: "School boards", filters: { q: "board" } });
  });
  expect(result.current?.map((list) => [list.name, list.filters])).toEqual([
    ["School boards", { q: "board" }],
  ]);

  act(() => {
    savedListActions("main").remove(id);
  });
  expect(result.current).toEqual([]);
});

test("one list is found by id, and a missing one is null", () => {
  let id = "";
  act(() => {
    id = savedListActions("main").create({ name: "Schools", filters: {} }).id;
  });
  const { result } = renderHook(() => ({
    found: useSavedList("main", id),
    missing: useSavedList("main", "nope"),
  }));
  expect(result.current.found?.name).toBe("Schools");
  expect(result.current.missing).toBeNull();
});

test("a change made in another tab is seen through the storage event", () => {
  const { result } = renderHook(() => useSavedLists("main"));
  expect(result.current).toEqual([]);
  const list = {
    id: "other-tab",
    name: "From elsewhere",
    filters: { status: "verified" },
    createdAt: "2026-10-01T00:00:00.000Z",
    updatedAt: "2026-10-01T00:00:00.000Z",
  };
  act(() => {
    window.localStorage.setItem(MAIN_KEY, JSON.stringify({ version: 1, lists: [list] }));
    window.dispatchEvent(new StorageEvent("storage", { key: MAIN_KEY }));
  });
  expect(result.current).toEqual([list]);
});

test("blocked storage reads as no lists, and a write says so", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new DOMException("blocked", "SecurityError");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("blocked", "SecurityError");
  });
  const { result } = renderHook(() => useSavedLists("main"));
  expect(result.current).toEqual([]);
  expect(() => savedListActions("main").create({ name: "Schools", filters: {} })).toThrow(
    /blocked/,
  );
  expect(result.current).toEqual([]);
});
