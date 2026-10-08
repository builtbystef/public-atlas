import { expect, test } from "vite-plus/test";

import { parseInstitutionSearch, parsePlaceSearch } from "./schemas";

test("the institutions list reads its filters from the URL", () => {
  expect(
    parseInstitutionSearch({
      q: "oak",
      status: "verified",
      place_id: "not-a-uuid",
      sort: "place",
      order: "desc",
      page: "3",
    }),
  ).toEqual({ q: "oak", status: "verified", sort: "place", order: "desc", page: 3 });
  expect(parseInstitutionSearch(new URLSearchParams("q=&status=bogus"))).toEqual({});
});

test("population bounds are whole numbers of people", () => {
  expect(parseInstitutionSearch({ min_population: "10000", max_population: "-5" })).toEqual({
    min_population: 10000,
  });
  expect(parseInstitutionSearch({ max_population: "12.5", sort: "population" })).toEqual({
    sort: "population",
  });
});

test("the places list reads its filters from the URL", () => {
  expect(
    parsePlaceSearch({
      q: "oak",
      administrative_level: "municipality",
      parent_place_id: "not-a-uuid",
      min_population: "5000",
      sort: "population",
      order: "desc",
      page: "2",
    }),
  ).toEqual({
    q: "oak",
    administrative_level: "municipality",
    min_population: 5000,
    sort: "population",
    order: "desc",
    page: 2,
  });
  expect(parsePlaceSearch(new URLSearchParams("sort=status"))).toEqual({});
});
