import { expect, test } from "vite-plus/test";

import {
  addList,
  describePopulation,
  fromFormValues,
  mergeLists,
  parseStoredLists,
  removeList,
  replaceList,
  savedListFormSchema,
  serializeLists,
  toFormValues,
  type SavedList,
} from "./schemas";

const PLACE = "0199a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b";

const libraries: SavedList = {
  id: "a",
  name: "Libraries in Ontario",
  filters: { institution_type: "library", place_id: PLACE },
  createdAt: "2026-10-01T10:00:00.000Z",
  updatedAt: "2026-10-01T10:00:00.000Z",
};

const towns: SavedList = {
  id: "b",
  name: "Small towns",
  description: "Under 10,000 people",
  filters: { administrative_level: "municipality", max_population: 10000 },
  createdAt: "2026-10-02T10:00:00.000Z",
  updatedAt: "2026-10-02T10:00:00.000Z",
};

test("stored lists read back newest first", () => {
  expect(parseStoredLists(serializeLists([libraries, towns]))).toEqual([towns, libraries]);
});

test("an unreadable store is no lists, and a bad entry does not hide the rest", () => {
  expect(parseStoredLists(null)).toEqual([]);
  expect(parseStoredLists("{not json")).toEqual([]);
  expect(parseStoredLists(JSON.stringify({ version: 99, lists: [libraries] }))).toEqual([]);
  const raw = JSON.stringify({
    version: 1,
    lists: [
      libraries,
      { id: "c", name: "", filters: {} },
      { ...towns, filters: { status: "bogus", max_population: -1, institution_type: "school" } },
    ],
  });
  expect(parseStoredLists(raw)).toEqual([
    { ...towns, filters: { institution_type: "school" } },
    libraries,
  ]);
});

test("adding, editing and removing keep the newest first", () => {
  const { lists, list } = addList(
    [libraries],
    { name: "  Big cities ", description: " ", filters: { min_population: 100000, q: "" } },
    { id: "n", now: "2026-10-03T00:00:00.000Z" },
  );
  expect(list).toEqual({
    id: "n",
    name: "Big cities",
    filters: { min_population: 100000 },
    createdAt: "2026-10-03T00:00:00.000Z",
    updatedAt: "2026-10-03T00:00:00.000Z",
  });
  expect(lists.map((l) => l.id)).toEqual(["n", "a"]);

  const edited = replaceList(
    [towns, libraries],
    "a",
    { name: "Ontario libraries", filters: { institution_type: "library" } },
    "2026-10-04T00:00:00.000Z",
  );
  expect(edited[0]).toEqual({
    ...libraries,
    name: "Ontario libraries",
    filters: { institution_type: "library" },
    updatedAt: "2026-10-04T00:00:00.000Z",
  });
  expect(removeList(edited, "a")).toEqual([towns]);
});

test("an import adds new lists and replaces older copies of the same list", () => {
  const newer = { ...libraries, name: "Renamed", updatedAt: "2026-10-05T00:00:00.000Z" };
  const older = { ...towns, name: "Stale", updatedAt: "2026-09-01T00:00:00.000Z" };
  const fresh = { ...towns, id: "c", updatedAt: "2026-09-02T00:00:00.000Z" };
  const merged = mergeLists([libraries, towns], serializeLists([newer, older, fresh]));
  expect(merged?.imported).toBe(2);
  expect(merged?.lists.map((l) => [l.id, l.name])).toEqual([
    ["a", "Renamed"],
    ["b", "Small towns"],
    ["c", "Small towns"],
  ]);
  expect(mergeLists([libraries], "[1, 2]")).toBeNull();
  expect(mergeLists([libraries], "nope")).toBeNull();
});

test("the form round-trips a list and leaves empty controls out", () => {
  const values = toFormValues(towns);
  expect(values).toMatchObject({ max_population: "10000", min_population: "", status: "" });
  expect(fromFormValues(values)).toEqual({
    name: towns.name,
    description: towns.description,
    filters: towns.filters,
  });
});

test("the form wants a name and a sensible population range", () => {
  const values = { ...toFormValues(towns), name: " " };
  expect(savedListFormSchema.safeParse(values).success).toBe(false);
  const backwards = { ...toFormValues(towns), min_population: "20000" };
  const result = savedListFormSchema.safeParse(backwards);
  expect(result.success).toBe(false);
  expect(result.error?.issues[0]?.path).toEqual(["max_population"]);
  expect(
    savedListFormSchema.safeParse({ ...toFormValues(towns), min_population: "1.5" }).success,
  ).toBe(false);
});

test("a population range reads as one short label", () => {
  expect(describePopulation(10000, 50000)).toBe("Pop. 10,000–50,000");
  expect(describePopulation(0, undefined)).toBe("Pop. ≥ 0");
  expect(describePopulation(undefined, 2500)).toBe("Pop. ≤ 2,500");
  expect(describePopulation(undefined, undefined)).toBeNull();
});
