import { expect, test } from "vite-plus/test";

import { parseRunSearch, releaseSchema, runSchema } from "./schemas";

test("the run form becomes the API's run input", () => {
  const run = runSchema.parse({
    name: " Ontario homepages ",
    country_code: "CA",
    mode: "step",
    record_video: true,
    administrative_levels: ["municipality"],
    institution_types: [],
    assignment_types: ["find_homepage"],
    subject_ids: [],
  });
  expect(run).toEqual({
    name: "Ontario homepages",
    country_code: "CA",
    mode: "step",
    record_video: true,
    filter: {
      administrative_levels: ["municipality"],
      institution_types: [],
      assignment_types: ["find_homepage"],
      subject_ids: [],
    },
  });
});

test("a run needs a name and a country", () => {
  const result = runSchema.safeParse({
    name: "",
    country_code: "",
    mode: "auto",
    record_video: false,
    administrative_levels: [],
    institution_types: [],
    assignment_types: [],
    subject_ids: [],
  });
  expect(result.success).toBe(false);
  expect(result.error?.issues.map((issue) => issue.path[0])).toEqual(["name", "country_code"]);
});

test("the release dialog takes a count and an optional type", () => {
  expect(releaseSchema.parse({ limit: "3", assignment_type: "" })).toEqual({
    limit: 3,
    assignment_type: "",
  });
  expect(releaseSchema.safeParse({ limit: "0", assignment_type: "" }).success).toBe(false);
});

test("the runs list is paged", () => {
  expect(parseRunSearch({ page: "2" })).toEqual({ page: 2 });
});
