import { expect, test } from "vite-plus/test";

import { crumbsFor } from "./page-titles";

test("a record page's breadcrumb links back to its list", () => {
  expect(crumbsFor("/runs")).toEqual([{ label: "Runs" }]);
  expect(crumbsFor("/runs/abc")).toEqual([{ label: "Runs", href: "/runs" }, { label: "Run" }]);
  expect(crumbsFor("/runs/new")).toEqual([{ label: "Runs", href: "/runs" }, { label: "New run" }]);
  expect(crumbsFor("/institutions/abc")).toEqual([
    { label: "Institutions", href: "/institutions" },
    { label: "Institution" },
  ]);
  expect(crumbsFor("/places/abc")).toEqual([
    { label: "Places", href: "/places" },
    { label: "Place" },
  ]);
  expect(crumbsFor("/elsewhere")).toBeNull();
});
