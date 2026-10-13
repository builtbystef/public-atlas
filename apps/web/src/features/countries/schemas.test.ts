import { expect, test } from "vite-plus/test";

import {
  countryNameSchema,
  levelSchema,
  namingRulesSchema,
  namingRulesToForm,
  sharedDesignators,
  typeSchema,
} from "./schemas";

test("the naming rules form drops blank words and empty groups", () => {
  expect(
    namingRulesSchema.parse({
      designators: [["City", " Ville "], [], ["Township", "", "Canton"]],
      connectors: ["of the", " d'"],
      leading: [],
      and_words: ["and", " "],
    }),
  ).toEqual({
    designators: [
      ["City", "Ville"],
      ["Township", "Canton"],
    ],
    connectors: ["of the", "d'"],
    leading: [],
    and_words: ["and"],
  });
});

test("the stored rules fill the form back as copies", () => {
  const rules = {
    designators: [["City", "Ville"], ["Town"]],
    connectors: ["of"],
    leading: [],
    and_words: ["and"],
  };
  const form = namingRulesToForm(rules);
  expect(form).toEqual(rules);
  form.designators[0]?.push("Cité");
  expect(rules.designators[0]).toEqual(["City", "Ville"]);
});

test("a word in two designator groups is found, whatever its case", () => {
  const shared = sharedDesignators([["City", "Ville"], ["Town", "ville"], ["Township"]]);
  expect([...shared.values()]).toEqual([{ word: "Ville", rows: [0, 1] }]);
  expect(sharedDesignators([["City", "city"]]).size).toBe(0);
});

const TYPE_NAME_MESSAGE = "Lowercase letters, digits and underscores, starting with a letter";

test("a country needs a name", () => {
  expect(countryNameSchema.safeParse({ name: " " }).error?.issues[0]?.message).toBe(
    "Name is required",
  );
  expect(countryNameSchema.parse({ name: " Canada " })).toEqual({ name: "Canada" });
});

test("a level has a slug name and a rank", () => {
  expect(
    levelSchema.parse({
      name: "municipality",
      rank: "2",
      government_institution_type: "municipal_government",
      expected_institution_types: ["school_board"],
    }),
  ).toEqual({
    name: "municipality",
    rank: 2,
    government_institution_type: "municipal_government",
    expected_institution_types: ["school_board"],
  });
  const capitalised = levelSchema.safeParse({
    name: "Municipality",
    rank: "2",
    government_institution_type: "x",
    expected_institution_types: [],
  });
  expect(capitalised.error?.issues.map((issue) => [issue.path, issue.message])).toEqual([
    [["name"], TYPE_NAME_MESSAGE],
  ]);
  // The country is rank 1; nothing sits above it.
  const aboveTheCountry = levelSchema.safeParse({
    name: "municipality",
    rank: "0",
    government_institution_type: "",
    expected_institution_types: [],
  });
  expect(aboveTheCountry.error?.issues.map((issue) => [issue.path, issue.message])).toEqual([
    [["rank"], "1 or more: the country is 1"],
    [["government_institution_type"], "Choose the government's type"],
  ]);
});

test("a type name is a slug", () => {
  const spaced = typeSchema.safeParse({ name: "school board", description: "" });
  expect(spaced.error?.issues.map((issue) => [issue.path, issue.message])).toEqual([
    [["name"], TYPE_NAME_MESSAGE],
  ]);
  expect(typeSchema.safeParse({ name: "", description: "" }).error?.issues[0]?.message).toBe(
    "A name is required",
  );
  expect(typeSchema.parse({ name: "school_board", description: " Boards " })).toEqual({
    name: "school_board",
    description: "Boards",
  });
});
