import { z } from "zod";

import { wallClockToIso } from "@/lib/formatting/dates";

/**
 * Zod field builders for the forms. They take the strings inputs produce
 * (`z.input`) and emit what the API's request bodies want (`z.output`): ""
 * becomes null, which a PATCH treats as "clear this field".
 */

export const text = z.string().trim();

export const emptyToNull = (value: string) => (value === "" ? null : value);

export const requiredText = (label: string, max: number) =>
  text.min(1, `${label} is required`).max(max, `${label} must be at most ${max} characters`);

export const optionalText = (max: number) =>
  text.max(max, `Must be at most ${max} characters`).transform(emptyToNull);

export const optionalNotes = text.transform(emptyToNull);

export const optionalEmail = text
  .transform(emptyToNull)
  .pipe(z.email("Enter a valid email address").nullable());

export const optionalWebsite = text
  .transform(emptyToNull)
  .pipe(z.httpUrl("Enter a URL starting with http:// or https://").max(500).nullable());

/** A <select> whose empty option means "none". */
export const optionalId = text.transform(emptyToNull).pipe(z.uuid("Choose an option").nullable());

/** A datetime-local value, read in the user's zone; see formatting/dates.ts. */
export const optionalDateTime = (timeZone: string) =>
  text.transform(emptyToNull).pipe(
    z
      .string()
      .transform((value, ctx) => {
        const iso = wallClockToIso(value, timeZone);
        if (iso === null) ctx.addIssue({ code: "custom", message: "Enter a valid date and time" });
        return iso;
      })
      .nullable(),
  );
