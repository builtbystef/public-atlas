import { expect, test } from "vite-plus/test";

import { graphViewFilters, institutionTableFilters } from "./queries";
import { parseGraphSearch, parseInstitutionSearch } from "./schemas";

const PLACE = "0199e8b0-0000-7000-8000-000000000001";
const OTHER_PLACE = "0199e8b0-0000-7000-8000-000000000002";

test("the graph view draws the hierarchy by default: places, institutions and their governments", () => {
  expect(graphViewFilters(parseGraphSearch({}))).toEqual({
    place_id: undefined,
    country_code: undefined,
    kinds: ["place", "institution"],
    governments: true,
    administrative_level: undefined,
    institution_type: undefined,
    status: undefined,
    platforms: undefined,
  });
});

test("the institutions detail asks for both kinds without the governments", () => {
  expect(
    graphViewFilters(parseGraphSearch({ detail: "institutions", status: "verified" })),
  ).toEqual({
    place_id: undefined,
    country_code: undefined,
    kinds: ["place", "institution"],
    governments: undefined,
    administrative_level: undefined,
    institution_type: undefined,
    status: "verified",
    platforms: undefined,
  });
});

test("the web detail asks for every kind, with platforms only when the URL turns them on", () => {
  const hidden = graphViewFilters(parseGraphSearch({ detail: "web" }));
  expect(hidden.kinds).toBeUndefined();
  expect(hidden.governments).toBeUndefined();
  expect(hidden.platforms).toBeUndefined();
  const shown = graphViewFilters(parseGraphSearch({ detail: "web", platforms: "1" }));
  expect(shown.platforms).toBe(true);
});

test("the shared-domains overlay asks for the whole web with platforms, whatever the detail says", () => {
  expect(
    graphViewFilters(
      parseGraphSearch({
        place_id: PLACE,
        detail: "hierarchy",
        overlay: "domains",
        institution_type: "library",
      }),
    ),
  ).toEqual({
    place_id: PLACE,
    country_code: undefined,
    kinds: undefined,
    governments: undefined,
    administrative_level: undefined,
    institution_type: "library",
    status: undefined,
    platforms: true,
  });
});

test("the other overlays leave the detail alone", () => {
  const coverage = graphViewFilters(parseGraphSearch({ overlay: "coverage" }));
  expect(coverage.kinds).toEqual(["place", "institution"]);
  expect(coverage.governments).toBe(true);
  expect(coverage.platforms).toBeUndefined();
});

test("an institutions table's fixed filters win over the URL's", () => {
  const search = parseInstitutionSearch({
    q: "oak",
    place_id: OTHER_PLACE,
    status: "verified",
    sort: "name",
    order: "desc",
    page: "2",
  });
  expect(institutionTableFilters(search, { place_id: PLACE })).toEqual({
    q: "oak",
    place_id: PLACE,
    status: "verified",
    sort: "name",
    order: "desc",
    limit: 50,
    offset: 50,
  });
});

test("an institutions table without fixed filters is the URL's page of fifty", () => {
  expect(institutionTableFilters(parseInstitutionSearch({ country_code: "CA" }))).toEqual({
    country_code: "CA",
    limit: 50,
    offset: 0,
  });
});
