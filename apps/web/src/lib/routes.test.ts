import { expect, test } from "vite-plus/test";

import { paths } from "./routes";

test("record pages are built from their id", () => {
  expect(paths.run("r1")).toBe("/runs/r1");
  expect(paths.assignment("a1")).toBe("/assignments/a1");
  expect(paths.institution("i1")).toBe("/institutions/i1");
  expect(paths.reviewItem("v1")).toBe("/review/v1");
  expect(paths.country("CA")).toBe("/countries/CA");
  expect(paths.evalRun("e1")).toBe("/evals/e1");
});
