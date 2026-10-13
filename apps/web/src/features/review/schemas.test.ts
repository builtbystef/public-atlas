import { expect, test } from "vite-plus/test";

import {
  decisionSchema,
  kindTypeName,
  mergeSchema,
  parseReviewSearch,
  reviewFilters,
} from "./schemas";

const TYPE_NAME_MESSAGE = "Lowercase letters, digits and underscores, starting with a letter";

test("the queue reads its filters from the URL", () => {
  expect(
    parseReviewSearch({
      q: " library ",
      status: "all",
      rule: "duplicate",
      kind: "type_level:library@region",
      entity_kind: "institution",
      country_code: "CA",
      affects: "several",
      sort: "raised_at",
    }),
  ).toEqual({
    q: "library",
    status: "all",
    rule: "duplicate",
    kind: "type_level:library@region",
    entity_kind: "institution",
    country_code: "CA",
    affects: "several",
    sort: "raised_at",
  });
  expect(
    parseReviewSearch({ status: "bogus", country_code: "ca", affects: "many", q: " " }),
  ).toEqual({});
});

test("the queue asks for open items unless the URL says otherwise", () => {
  expect(reviewFilters({})).toEqual({ status: "open", limit: 50, offset: 0 });
  expect(reviewFilters({ status: "all", page: 2 })).toEqual({
    status: undefined,
    limit: 50,
    offset: 50,
  });
});

test("a decision's note and type become the API's body", () => {
  expect(decisionSchema.parse({ note: "", institution_type: "" })).toEqual({
    note: null,
    institution_type: null,
  });
  expect(decisionSchema.parse({ note: " ", institution_type: "" })).toEqual({
    note: null,
    institution_type: null,
  });
  expect(decisionSchema.parse({ note: "ok", institution_type: "school_board" })).toEqual({
    note: "ok",
    institution_type: "school_board",
  });
  const spaced = decisionSchema.safeParse({ note: "", institution_type: "School Board" });
  expect(spaced.error?.issues.map((issue) => [issue.path, issue.message])).toEqual([
    [["institution_type"], TYPE_NAME_MESSAGE],
  ]);
});

test("a merge needs a target that is an id, and its note may be empty", () => {
  const target = "0199e8b0-0000-7000-8000-000000000001";
  expect(mergeSchema.parse({ into_id: target, note: "" })).toEqual({ into_id: target, note: null });
  const blank = mergeSchema.safeParse({ into_id: "", note: "" });
  expect(blank.error?.issues.map((issue) => [issue.path, issue.message])).toEqual([
    [["into_id"], "Choose what to merge into"],
  ]);
  const notAnId = mergeSchema.safeParse({ into_id: "oakville", note: "" });
  expect(notAnId.error?.issues.map((issue) => [issue.path, issue.message])).toEqual([
    [["into_id"], "Choose what to merge into"],
  ]);
});

test("the type a kind is about", () => {
  expect(kindTypeName("type_level:school_board@municipality")).toBe("school_board");
  expect(kindTypeName("new_type:housing_corporation")).toBe("housing_corporation");
  expect(kindTypeName("other")).toBe("");
});
