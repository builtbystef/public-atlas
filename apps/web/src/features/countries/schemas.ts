import type { AdministrativeLevelInput, NamingRules } from "@public-atlas/api-client";
import { z } from "zod";

import {
  commaList,
  emptyToNull,
  requiredText,
  text,
  TYPE_NAME,
  typeNameMessage,
} from "@/lib/validation";

const typeName = text
  .min(1, "A name is required")
  .max(64, "At most 64 characters")
  .regex(TYPE_NAME, typeNameMessage);

/** Designator groups: one group per line, its spellings separated by commas. */
const designatorLines = text.transform((value) =>
  value
    .split("\n")
    .map((line) =>
      line
        .split(",")
        .map((word) => word.trim())
        .filter(Boolean),
    )
    .filter((group) => group.length > 0),
);

export const settingsSchema = z
  .object({
    name: requiredText("Name", 100),
    designators: designatorLines,
    connectors: commaList,
    leading: commaList,
    and_words: commaList,
  })
  .transform(({ name, ...naming_rules }) => ({ name, naming_rules }));

export type SettingsFormInput = z.input<typeof settingsSchema>;

/** The form's text for the rules as stored. */
export function namingRulesToForm(rules: NamingRules): Omit<SettingsFormInput, "name"> {
  return {
    designators: rules.designators.map((group) => group.join(", ")).join("\n"),
    connectors: rules.connectors.join(", "),
    leading: rules.leading.join(", "),
    and_words: rules.and_words.join(", "),
  };
}

export const levelSchema = z.object({
  name: typeName,
  rank: z.coerce.number().int("A whole number").min(0, "Zero or more"),
  government_institution_type: text.min(1, "Choose the government's type"),
  expected_institution_types: z.array(z.string()),
}) satisfies z.ZodType<AdministrativeLevelInput, unknown>;

export type LevelFormInput = z.input<typeof levelSchema>;

export const countryTypeSchema = z.object({
  institution_type: text.min(1, "Choose a type"),
  expected_source_types: z.array(z.string()),
  name_pattern: text.transform(emptyToNull),
});

export type CountryTypeFormInput = z.input<typeof countryTypeSchema>;

export const typeSchema = z.object({
  name: typeName,
  description: text,
});

export type TypeFormInput = z.input<typeof typeSchema>;
