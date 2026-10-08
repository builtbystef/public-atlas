import type { AdministrativeLevelInput, NamingRules } from "@public-atlas/api-client";
import { z } from "zod";

import { emptyToNull, requiredText, text, TYPE_NAME, typeNameMessage } from "@/lib/validation";

const typeName = text
  .min(1, "A name is required")
  .max(64, "At most 64 characters")
  .regex(TYPE_NAME, typeNameMessage);

/** Words entered as chips: trimmed, the empty ones dropped. */
const words = z
  .array(z.string())
  .transform((list) => list.map((word) => word.trim()).filter(Boolean));

export const countryNameSchema = z.object({ name: requiredText("Name", 100) });

export const namingRulesSchema = z.object({
  // One group per row; a row left empty is dropped.
  designators: z
    .array(z.array(z.string()))
    .transform((groups) =>
      groups
        .map((group) => group.map((word) => word.trim()).filter(Boolean))
        .filter((group) => group.length > 0),
    ),
  connectors: words,
  leading: words,
  and_words: words,
}) satisfies z.ZodType<NamingRules, unknown>;

export type NamingRulesFormInput = z.input<typeof namingRulesSchema>;

/** The form's values for the rules as stored, copied so the form never edits the cache. */
export function namingRulesToForm(rules: NamingRules): NamingRulesFormInput {
  return {
    designators: rules.designators.map((group) => [...group]),
    connectors: [...rules.connectors],
    leading: [...rules.leading],
    and_words: [...rules.and_words],
  };
}

/**
 * The words that sit in more than one designator group, by their case-folded
 * spelling: the first spelling met, and the rows it is in. A name using one
 * matches either kind of body.
 */
export function sharedDesignators(
  groups: readonly (readonly string[])[],
): Map<string, { word: string; rows: number[] }> {
  const seen = new Map<string, { word: string; rows: number[] }>();
  groups.forEach((group, row) => {
    for (const word of group.map((w) => w.trim()).filter(Boolean)) {
      const key = word.toLocaleLowerCase();
      const found = seen.get(key) ?? { word, rows: [] };
      if (!found.rows.includes(row)) found.rows.push(row);
      seen.set(key, found);
    }
  });
  return new Map([...seen].filter(([, { rows }]) => rows.length > 1));
}

export const levelSchema = z.object({
  name: typeName,
  rank: z.coerce.number().int("A whole number").min(1, "1 or more: the country is 1"),
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
