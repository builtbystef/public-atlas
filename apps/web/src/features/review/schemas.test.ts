import { expect, test } from "vite-plus/test";

import { decisionSchema, kindTypeName, mergeSchema, parseReviewSearch } from "./schemas";

test("the queue reads its filters from the URL", () => {
  expect(parseReviewSearch({ status: "all", rule: "duplicate" })).toEqual({
    status: "all",
    rule: "duplicate",
  });
  expect(parseReviewSearch({ status: "bogus" })).toEqual({});
});

test("a decision's note and type become the API's body", () => {
  expect(decisionSchema.parse({ note: " ", institution_type: "" })).toEqual({
    note: null,
    institution_type: null,
  });
  expect(decisionSchema.parse({ note: "ok", institution_type: "school_board" })).toEqual({
    note: "ok",
    institution_type: "school_board",
  });
  expect(decisionSchema.safeParse({ note: "", institution_type: "School Board" }).success).toBe(
    false,
  );
});

test("a merge needs a target", () => {
  expect(mergeSchema.safeParse({ into_id: "", note: "" }).success).toBe(false);
});

test("the type a kind is about", () => {
  expect(kindTypeName("type_level:school_board@municipality")).toBe("school_board");
  expect(kindTypeName("new_type:housing_corporation")).toBe("housing_corporation");
  expect(kindTypeName("other")).toBe("");
});
