"use client";

import type {
  CountryInstitutionTypeInput,
  InstitutionTypeInput,
  SourceTypeInput,
} from "@public-atlas/api-client";
import { revalidateLogic } from "@tanstack/react-form";
import { PencilIcon, PlusIcon, Trash2Icon } from "lucide-react";
import { useState } from "react";

import { CheckboxGroup } from "@/components/shared/checkbox-group";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { useAppForm } from "@/components/shared/form";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { errorMessage } from "@/lib/api/errors";
import { humanize } from "@/lib/labels";

import { useCountryMutation } from "../hooks/use-country-mutations";
import { deleteCountryInstitutionType, putCountryInstitutionType } from "../mutations";
import { countryTypeSchema, type CountryTypeFormInput } from "../schemas";
import { FormDialog } from "@/components/shared/form-dialog";

/**
 * The country's use of each institution type: the sources find_sources
 * expects on its homepage, and the name pattern a body of the type follows.
 */
export function CountryTypesTable({
  countryCode,
  rows,
  institutionTypes,
  sourceTypes,
}: {
  countryCode: string;
  rows: CountryInstitutionTypeInput[];
  institutionTypes: InstitutionTypeInput[];
  sourceTypes: SourceTypeInput[];
}) {
  const [editing, setEditing] = useState<CountryInstitutionTypeInput | "new" | null>(null);
  const [deleting, setDeleting] = useState<CountryInstitutionTypeInput | null>(null);
  const remove = useCountryMutation(
    (type: string) => deleteCountryInstitutionType(countryCode, type),
    "Type removed from the country",
  );
  const sorted = [...rows].sort((a, b) => a.institution_type.localeCompare(b.institution_type));
  const unused = institutionTypes.filter(
    (t) => !rows.some((row) => row.institution_type === t.name),
  );

  return (
    <div className="flex flex-col gap-3">
      {sorted.length === 0 ? (
        <EmptyState>The country uses no institution types yet.</EmptyState>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Institution type</TableHead>
                <TableHead>Expected source types</TableHead>
                <TableHead>Name pattern</TableHead>
                <TableHead className="w-0" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((row) => (
                <TableRow key={row.institution_type}>
                  <TableCell className="font-medium">{humanize(row.institution_type)}</TableCell>
                  <TableCell className="min-w-48 max-w-md whitespace-normal text-muted-foreground">
                    {row.expected_source_types.map(humanize).join(", ") || "–"}
                  </TableCell>
                  <TableCell className="max-w-xs font-mono text-xs break-all whitespace-normal">
                    {row.name_pattern ?? "–"}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Edit ${row.institution_type}`}
                        onClick={() => setEditing(row)}
                      >
                        <PencilIcon />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Remove ${row.institution_type}`}
                        onClick={() => setDeleting(row)}
                      >
                        <Trash2Icon />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <div>
        <Button variant="outline" onClick={() => setEditing("new")} disabled={unused.length === 0}>
          <PlusIcon /> Add type
        </Button>
      </div>
      {editing && (
        <CountryTypeDialog
          countryCode={countryCode}
          row={editing === "new" ? null : editing}
          institutionTypes={editing === "new" ? unused : institutionTypes}
          sourceTypes={sourceTypes}
          onClose={() => setEditing(null)}
        />
      )}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title={`Remove ${deleting ? humanize(deleting.institution_type).toLowerCase() : ""} from the country?`}
        description="Institutions of the type keep their rows; the rules stop expecting it and its sources."
        confirmLabel="Remove"
        pending={remove.isPending}
        onConfirm={() =>
          deleting && remove.mutateAsync(deleting.institution_type).then(() => setDeleting(null))
        }
      />
    </div>
  );
}

function CountryTypeDialog({
  countryCode,
  row,
  institutionTypes,
  sourceTypes,
  onClose,
}: {
  countryCode: string;
  row: CountryInstitutionTypeInput | null;
  institutionTypes: InstitutionTypeInput[];
  sourceTypes: SourceTypeInput[];
  onClose: () => void;
}) {
  const [serverError, setServerError] = useState<string | null>(null);
  const save = useCountryMutation(
    (body: CountryInstitutionTypeInput) => putCountryInstitutionType(countryCode, body),
    row ? "Type saved" : "Type added",
  );
  const form = useAppForm({
    defaultValues: {
      institution_type: row?.institution_type ?? institutionTypes[0]?.name ?? "",
      expected_source_types: row?.expected_source_types ?? [],
      name_pattern: row?.name_pattern ?? "",
    } satisfies CountryTypeFormInput as CountryTypeFormInput,
    validationLogic: revalidateLogic(),
    validators: { onDynamic: countryTypeSchema },
    onSubmit: async ({ value }) => {
      setServerError(null);
      try {
        await save.mutateAsync(countryTypeSchema.parse(value));
        onClose();
      } catch (error) {
        setServerError(errorMessage(error));
      }
    },
  });
  return (
    <FormDialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={row ? `Edit ${humanize(row.institution_type).toLowerCase()}` : "Add a type"}
      form={form}
      serverError={serverError}
      submit={
        <form.AppForm>
          <form.SubmitButton>{row ? "Save" : "Add"}</form.SubmitButton>
        </form.AppForm>
      }
    >
      <form.AppField name="institution_type">
        {(field) => (
          <field.SelectField
            label="Institution type"
            required
            options={institutionTypes.map((t) => ({ value: t.name, label: humanize(t.name) }))}
            disabled={row !== null}
          />
        )}
      </form.AppField>
      <form.Field name="expected_source_types">
        {(field) => (
          <CheckboxGroup
            name={field.name}
            label="Expected source types"
            description="What find_sources looks for on a body of this type."
            options={sourceTypes.map((t) => ({
              value: t.name,
              label: humanize(t.name),
              description: t.description || undefined,
            }))}
            value={field.state.value}
            onChange={field.handleChange}
            errors={field.state.meta.errors}
          />
        )}
      </form.Field>
      <form.AppField name="name_pattern">
        {(field) => (
          <field.TextField
            label="Name pattern"
            description="A regular expression a body's name should match; a miss raises a review item."
            placeholder="(?i)\bschool board\b"
            autoComplete="off"
            className="font-mono"
          />
        )}
      </form.AppField>
    </FormDialog>
  );
}
