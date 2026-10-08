"use client";

import type { CountryOutput, InstitutionTypeInput } from "@public-atlas/api-client";
import { revalidateLogic, useStore } from "@tanstack/react-form";
import { useState } from "react";

import { useAppForm } from "@/components/shared/form";
import { FormDialog } from "@/components/shared/form-dialog";
import { placeOptionQuery, placePickerQuery } from "@/features/graph/queries";
import type { InstitutionFilterValues } from "@/features/graph/schemas";
import { browserApi } from "@/lib/api/client";
import type { Database } from "@/lib/api/database";
import { entityStatusLabels, entityStatuses, humanize } from "@/lib/labels";

import {
  fromFormValues,
  savedListFormSchema,
  toFormValues,
  type SavedList,
  type SavedListFormInput,
} from "../schemas";
import { savedListActions } from "../store";

/**
 * Creates a list, or edits one: its name, a line about it, and the filters
 * that make it. A new list starts from `filters`, the ones in force where
 * "Save as list" was pressed.
 */
export function SavedListDialog({
  database,
  list,
  filters = {},
  countries,
  institutionTypes,
  onClose,
  onSaved,
}: {
  database: Database;
  /** The list to edit; null for a new one. */
  list: SavedList | null;
  filters?: InstitutionFilterValues;
  countries: CountryOutput[];
  institutionTypes: InstitutionTypeInput[];
  onClose: () => void;
  onSaved?: (list: SavedList) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const form = useAppForm({
    defaultValues: toFormValues(list ?? { filters }) satisfies SavedListFormInput,
    validationLogic: revalidateLogic(),
    validators: { onDynamic: savedListFormSchema },
    onSubmit: ({ value }) => {
      setError(null);
      const input = fromFormValues(value);
      const actions = savedListActions(database);
      try {
        if (list) {
          actions.update(list.id, input);
          onSaved?.({ ...list, ...input });
        } else {
          onSaved?.(actions.create(input));
        }
        onClose();
      } catch {
        setError("This browser would not store the list. Its storage may be full or turned off.");
      }
    },
  });
  const countryCode = useStore(form.store, (state) => state.values.country_code);

  const levels = countries
    .filter((c) => !countryCode || c.settings.country_code === countryCode)
    .flatMap((c) => c.administrative_levels.map((l) => l.name));
  const levelOptions = [...new Set(levels)].map((name) => ({ value: name, label: humanize(name) }));

  return (
    <FormDialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={list ? "Edit list" : "Save a list"}
      form={form}
      serverError={error}
      submit={
        <form.AppForm>
          <form.SubmitButton requireChanges={list !== null}>
            {list ? "Save" : "Save list"}
          </form.SubmitButton>
        </form.AppForm>
      }
    >
      <form.AppField name="name">
        {(field) => (
          <field.TextField
            label="List name"
            required
            placeholder="Libraries in small towns"
            autoComplete="off"
            autoFocus
          />
        )}
      </form.AppField>
      <form.AppField name="description">
        {(field) => (
          <field.TextareaField label="Description" rows={2} placeholder="What the list is for" />
        )}
      </form.AppField>

      <div className="grid gap-4 sm:grid-cols-2">
        <form.AppField name="q">
          {(field) => <field.TextField label="Institution name contains" autoComplete="off" />}
        </form.AppField>
        {countries.length > 1 && (
          <form.AppField name="country_code">
            {(field) => (
              <field.SelectField
                label="Country"
                placeholder="Any country"
                options={countries.map((c) => ({
                  value: c.settings.country_code,
                  label: c.settings.name,
                }))}
              />
            )}
          </form.AppField>
        )}
        <form.AppField name="place_id">
          {(field) => (
            <field.ComboboxField
              label="Place"
              description="The place and every place under it."
              placeholder="Any place"
              search={(text) => placePickerQuery(browserApi, text, countryCode || undefined)}
              resolve={(id) => placeOptionQuery(browserApi, id)}
            />
          )}
        </form.AppField>
        <form.AppField name="administrative_level">
          {(field) => (
            <field.SelectField label="Level" placeholder="Any level" options={levelOptions} />
          )}
        </form.AppField>
        <form.AppField name="institution_type">
          {(field) => (
            <field.SelectField
              label="Type"
              placeholder="Any type"
              options={institutionTypes.map((t) => ({ value: t.name, label: humanize(t.name) }))}
            />
          )}
        </form.AppField>
        <form.AppField name="status">
          {(field) => (
            <field.SelectField
              label="Status"
              placeholder="Any status"
              options={entityStatuses.map((value) => ({
                value,
                label: entityStatusLabels[value],
              }))}
            />
          )}
        </form.AppField>
        <form.AppField name="min_population">
          {(field) => (
            <field.TextField
              label="Smallest population"
              type="number"
              inputMode="numeric"
              min={0}
              placeholder="Any"
              description="Of the institution's own place."
            />
          )}
        </form.AppField>
        <form.AppField name="max_population">
          {(field) => (
            <field.TextField
              label="Largest population"
              type="number"
              inputMode="numeric"
              min={0}
              placeholder="Any"
            />
          )}
        </form.AppField>
      </div>
    </FormDialog>
  );
}
