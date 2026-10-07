import { expect, test } from "vite-plus/test";

import { parseInstitutionSearch } from "./schemas";

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
