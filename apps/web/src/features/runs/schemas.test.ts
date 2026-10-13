import { expect, test } from "vite-plus/test";

import { releaseSchema, runSchema } from "./schemas";

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

test("a run needs a name, a country and subjects that are ids", () => {
  const result = runSchema.safeParse({
    name: "",
    country_code: "",
    mode: "auto",
    record_video: false,
    administrative_levels: [],
    institution_types: [],
    assignment_types: [],
    subject_ids: ["oakville"],
  });
  expect(result.error?.issues.map((issue) => [issue.path, issue.message])).toEqual([
    [["name"], "Name is required"],
    [["country_code"], "Choose a country"],
    [["subject_ids", 0], "Invalid UUID"],
  ]);
});

test("the release dialog takes a count between one and the API's page and an optional type", () => {
  expect(releaseSchema.parse({ limit: "3", assignment_type: "" })).toEqual({
    limit: 3,
    assignment_type: "",
  });
  expect(releaseSchema.parse({ limit: "500", assignment_type: "find_sources" })).toEqual({
    limit: 500,
    assignment_type: "find_sources",
  });
  const tooFew = releaseSchema.safeParse({ limit: "0", assignment_type: "" });
  expect(tooFew.error?.issues.map((issue) => [issue.path, issue.message])).toEqual([
    [["limit"], "Release at least one"],
  ]);
  const tooMany = releaseSchema.safeParse({ limit: "501", assignment_type: "" });
  expect(tooMany.error?.issues.map((issue) => [issue.path, issue.message])).toEqual([
    [["limit"], "At most 500 at once"],
  ]);
  const unknownType = releaseSchema.safeParse({ limit: "1", assignment_type: "find_castles" });
  expect(unknownType.error?.issues.map((issue) => issue.path)).toEqual([["assignment_type"]]);
});
