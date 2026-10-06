import { z } from "zod";
import { expect, test } from "vite-plus/test";

import {
  ALL_ROWS,
  PICKER_ROWS,
  listPage,
  listSearch,
  optionalParam,
  paged,
  parseSearch,
  queryParams,
  toSearchString,
} from "./lists";

const schema = z.object({
  q: optionalParam(z.string().min(1)),
  ...listSearch(["name", "created"]),
});

test("search params keep valid values and drop the rest", () => {
  expect(parseSearch(schema, { q: "ada", sort: "bogus", order: ["x"] })).toEqual({ q: "ada" });
  expect(parseSearch(schema, new URLSearchParams("sort=name&q="))).toEqual({ sort: "name" });
});

test("search params carry the page and sort of a list", () => {
  expect(parseSearch(schema, { page: "3", sort: "created", order: "desc" })).toEqual({
    page: 3,
    sort: "created",
    order: "desc",
  });
  // The first page is the URL without one; anything unknown is dropped.
  expect(parseSearch(schema, { page: "1", sort: "email", order: "up" })).toEqual({});
  expect(parseSearch(schema, { page: "0" })).toEqual({});
  expect(parseSearch(schema, { page: "two" })).toEqual({});
});

test("a page number becomes the API's limit and offset", () => {
  expect(listPage(undefined)).toEqual({ limit: 50, offset: 0 });
  expect(listPage(3, 20)).toEqual({ limit: 20, offset: 40 });
  expect(paged({ q: "ada", page: 2, sort: "name" })).toEqual({
    q: "ada",
    sort: "name",
    limit: 50,
    offset: 50,
  });
});

test("a query string leaves out empty values", () => {
  expect(toSearchString({ q: "ada", status: undefined })).toBe("q=ada");
  expect(toSearchString({ q: "ada", page: 2, sort: undefined, order: "" })).toBe("q=ada&page=2");
});

test("query params drop undefined values but keep empty and false ones", () => {
  expect(queryParams({ q: "ada", status: undefined, page: 0, done: false, empty: "" })).toEqual({
    q: "ada",
    page: 0,
    done: false,
    empty: "",
  });
  expect(queryParams({})).toEqual({});
});

test("page constants agree with the API's limits", () => {
  expect(ALL_ROWS).toEqual({ limit: 500, offset: 0 });
  expect(PICKER_ROWS.limit).toBeLessThanOrEqual(ALL_ROWS.limit);
  expect(listPage(1).limit).toBeLessThanOrEqual(ALL_ROWS.limit);
});
