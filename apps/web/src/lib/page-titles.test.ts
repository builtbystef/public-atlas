import { expect, test } from "vite-plus/test";

import { crumbsFor, titleFor } from "./page-titles";

test("the shell header names the section of the URL", () => {
  expect(titleFor("/lists")).toBe("Saved lists");
  expect(titleFor("/lists/abc")).toBe("Saved list");
  expect(titleFor("/places/abc")).toBe("Place");
  expect(titleFor("/graph")).toBe("Graph");
  expect(titleFor("/runs")).toBe("Runs");
  expect(titleFor("/runs/new")).toBe("New run");
  expect(titleFor("/runs/abc")).toBe("Run");
  expect(titleFor("/review")).toBe("Review queue");
  expect(titleFor("/review/abc")).toBe("Review item");
  expect(titleFor("/countries")).toBe("Country config");
  expect(titleFor("/countries/CA")).toBe("Country");
  expect(titleFor("/settings")).toBe("Settings");
  expect(titleFor("/elsewhere")).toBeNull();
});

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
