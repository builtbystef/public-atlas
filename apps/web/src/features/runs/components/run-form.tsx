"use client";

import type { CountrySettingsInput, RunInput } from "@public-atlas/api-client";
import { revalidateLogic, useStore } from "@tanstack/react-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { CheckboxGroup } from "@/components/shared/checkbox-group";
import {
  Form,
  FormActions,
  FormError,
  FormSection,
  FormSections,
  useAppForm,
} from "@/components/shared/form";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { countryQuery } from "@/features/countries/queries";
import { browserApi } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import {
  assignmentTypeLabels,
  assignmentTypes,
  humanize,
  runModeLabels,
  runModes,
} from "@/lib/labels";
import { paths } from "@/lib/routes";

import { createRun } from "../mutations";
import { runKeys } from "../queries";
import { runSchema, type RunFormInput } from "../schemas";
import { SubjectsField } from "./subjects-field";

const modeOptions = runModes.map((value) => ({ value, label: runModeLabels[value] }));
const assignmentTypeOptions = assignmentTypes.map((value) => ({
  value,
  label: assignmentTypeLabels[value],
}));

/**
 * Starts a run: a name, a country, a mode, and the filter that says which
 * subjects and assignment types it covers (spec section 7.1). The levels
 * and institution types come from the chosen country's tables.
 */
export function RunForm({ countries }: { countries: CountrySettingsInput[] }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [serverError, setServerError] = useState<string | null>(null);
  const first = countries[0]?.country_code ?? "";

  const mutation = useMutation({
    mutationFn: (body: RunInput) => createRun(body),
    onSuccess: async (run) => {
      toast.success("Run created");
      await queryClient.invalidateQueries({ queryKey: runKeys.all });
      router.push(paths.run(run.id));
    },
    onError: (error) => setServerError(errorMessage(error)),
  });

  const form = useAppForm({
    defaultValues: {
      name: "",
      country_code: first,
      mode: "step",
      record_video: false,
      administrative_levels: [],
      institution_types: [],
      assignment_types: [],
      subject_ids: [],
    } satisfies RunFormInput as RunFormInput,
    validationLogic: revalidateLogic(),
    validators: { onDynamic: runSchema },
    onSubmit: async ({ value, formApi }) => {
      setServerError(null);
      const run = await mutation.mutateAsync(runSchema.parse(value)).catch(() => null);
      if (run) formApi.reset();
    },
  });

  const countryCode = useStore(form.store, (state) => state.values.country_code);
  const country = useQuery({
    ...countryQuery(browserApi, countryCode),
    enabled: countryCode !== "",
  });
  const levelOptions = (country.data?.administrative_levels ?? []).map((level) => ({
    value: level.name,
    label: humanize(level.name),
    description: `Rank ${level.rank} · government: ${humanize(level.government_institution_type)}`,
  }));
  const typeOptions = (country.data?.institution_types ?? []).map((type) => ({
    value: type.institution_type,
    label: humanize(type.institution_type),
  }));

  return (
    <Form form={form} warnOnLeave>
      <FormError message={serverError} />
      <FormSections>
        <FormSection title="Run">
          <form.AppField name="name">
            {(field) => (
              <field.TextField
                label="Name"
                required
                placeholder="Ontario homepages, October"
                autoComplete="off"
                autoFocus
              />
            )}
          </form.AppField>
          <div className="grid gap-5 sm:grid-cols-2">
            <form.AppField name="country_code">
              {(field) => (
                <field.SelectField
                  label="Country"
                  required
                  options={countries.map((c) => ({ value: c.country_code, label: c.name }))}
                  placeholder={countries.length === 0 ? "No country seeded" : undefined}
                />
              )}
            </form.AppField>
            <form.AppField name="mode">
              {(field) => <field.SelectField label="Mode" required options={modeOptions} />}
            </form.AppField>
          </div>
          <form.Field name="record_video">
            {(field) => (
              <Field orientation="horizontal">
                <Checkbox
                  id={field.name}
                  name={field.name}
                  checked={field.state.value}
                  onCheckedChange={(checked) => field.handleChange(checked === true)}
                />
                <div className="flex flex-col gap-1">
                  <FieldLabel htmlFor={field.name}>Record video</FieldLabel>
                  <FieldDescription>
                    Keeps a recording of each browser session for a week.
                  </FieldDescription>
                </div>
              </Field>
            )}
          </form.Field>
        </FormSection>
        <FormSection title="Filter">
          <form.Field name="assignment_types">
            {(field) => (
              <CheckboxGroup
                name={field.name}
                label="Assignment types"
                description="The kinds of work to do. Empty means all three."
                options={assignmentTypeOptions}
                value={field.state.value}
                onChange={(next) => field.handleChange(next as RunFormInput["assignment_types"])}
                columns={3}
              />
            )}
          </form.Field>
          <form.Field name="administrative_levels">
            {(field) => (
              <CheckboxGroup
                name={field.name}
                label="Administrative levels"
                description="Places at these levels, and the institutions under them."
                options={levelOptions}
                value={field.state.value}
                onChange={field.handleChange}
                emptyMessage={
                  country.isPending && countryCode
                    ? "Loading the country's levels…"
                    : "The country has no levels yet."
                }
              />
            )}
          </form.Field>
          <form.Field name="institution_types">
            {(field) => (
              <CheckboxGroup
                name={field.name}
                label="Institution types"
                options={typeOptions}
                value={field.state.value}
                onChange={field.handleChange}
                columns={3}
                emptyMessage={
                  country.isPending && countryCode
                    ? "Loading the country's types…"
                    : "The country uses no institution types yet."
                }
              />
            )}
          </form.Field>
          <form.Field name="subject_ids">
            {(field) => (
              <SubjectsField
                countryCode={countryCode}
                value={field.state.value}
                onChange={field.handleChange}
              />
            )}
          </form.Field>
        </FormSection>
      </FormSections>
      <FormActions className="border-t pt-8">
        <Button variant="outline" nativeButton={false} render={<Link href={paths.runs} />}>
          Cancel
        </Button>
        <form.AppForm>
          <form.SubmitButton>Create run</form.SubmitButton>
        </form.AppForm>
      </FormActions>
    </Form>
  );
}
