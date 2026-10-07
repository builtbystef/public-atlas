import { expect, test } from "vite-plus/test";

import { levelSchema, namingRulesToForm, settingsSchema, typeSchema } from "./schemas";

test("the settings form becomes naming rules", () => {
  expect(
    settingsSchema.parse({
      name: "Canada",
      designators: "City, Ville\nTown\n\nTownship, Canton",
      connectors: "of, de,",
      leading: "",
      and_words: "and, et",
    }),
  ).toEqual({
    name: "Canada",
    naming_rules: {
      designators: [["City", "Ville"], ["Town"], ["Township", "Canton"]],
      connectors: ["of", "de"],
      leading: [],
      and_words: ["and", "et"],
    },
  });
});

test("the stored rules fill the form back", () => {
  expect(
    namingRulesToForm({
      designators: [["City", "Ville"], ["Town"]],
      connectors: ["of"],
      leading: [],
      and_words: ["and"],
    }),
  ).toEqual({ designators: "City, Ville\nTown", connectors: "of", leading: "", and_words: "and" });
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
  expect(
    levelSchema.safeParse({
      name: "Municipality",
      rank: "2",
      government_institution_type: "x",
      expected_institution_types: [],
    }).success,
  ).toBe(false);
});

test("a type name is a slug", () => {
  expect(typeSchema.safeParse({ name: "school board", description: "" }).success).toBe(false);
  expect(typeSchema.parse({ name: "school_board", description: " Boards " })).toEqual({
    name: "school_board",
    description: "Boards",
  });
});
