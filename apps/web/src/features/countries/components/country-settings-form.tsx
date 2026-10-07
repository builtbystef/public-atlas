"use client";

import type { CountrySettingsInput } from "@public-atlas/api-client";
import { revalidateLogic } from "@tanstack/react-form";
import { useState } from "react";

import { Form, FormError, useAppForm } from "@/components/shared/form";
import { errorMessage } from "@/lib/api/errors";

import { useCountryMutation } from "../hooks/use-country-mutations";
import { putCountrySettings } from "../mutations";
import { namingRulesToForm, settingsSchema, type SettingsFormInput } from "../schemas";

/** The country's name and the naming rules the duplicate search and the name checks use. */
export function CountrySettingsForm({ settings }: { settings: CountrySettingsInput }) {
  const [serverError, setServerError] = useState<string | null>(null);
  const save = useCountryMutation(
    (body: CountrySettingsInput) => putCountrySettings(settings.country_code, body),
    "Settings saved",
  );
  const form = useAppForm({
    defaultValues: {
      name: settings.name,
      ...namingRulesToForm(settings.naming_rules),
    } satisfies SettingsFormInput,
    validationLogic: revalidateLogic(),
    validators: { onDynamic: settingsSchema },
    onSubmit: async ({ value, formApi }) => {
      setServerError(null);
      try {
        const saved = await save.mutateAsync({
          country_code: settings.country_code,
          ...settingsSchema.parse(value),
        });
        formApi.reset({ name: saved.name, ...namingRulesToForm(saved.naming_rules) });
      } catch (error) {
        setServerError(errorMessage(error));
      }
    },
  });
  return (
    <Form form={form}>
      <FormError message={serverError} />
      <form.AppField name="name">
        {(field) => <field.TextField label="Name" required autoComplete="off" />}
      </form.AppField>
      <form.AppField name="designators">
        {(field) => (
          <field.TextareaField
            label="Designators"
            rows={5}
            description="One group per line, its spellings separated by commas: “City, Ville”. Names that differ only by a designator in the same group are the same place."
          />
        )}
      </form.AppField>
      <form.AppField name="connectors">
        {(field) => (
          <field.TextField
            label="Connectors"
            description="Words between a designator and the name, comma-separated: “of, de”."
            autoComplete="off"
          />
        )}
      </form.AppField>
      <form.AppField name="leading">
        {(field) => (
          <field.TextField
            label="Leading words"
            description="Words a name may start with and still match, comma-separated: “The, La”."
            autoComplete="off"
          />
        )}
      </form.AppField>
      <form.AppField name="and_words">
        {(field) => (
          <field.TextField
            label="And words"
            description="Words that join two names, comma-separated: “and, et, &”."
            autoComplete="off"
          />
        )}
      </form.AppField>
      <div className="flex justify-end">
        <form.AppForm>
          <form.SubmitButton requireChanges>Save settings</form.SubmitButton>
        </form.AppForm>
      </div>
    </Form>
  );
}
