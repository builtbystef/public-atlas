"use client";

import type { AdministrativeLevelInput, InstitutionTypeInput } from "@public-atlas/api-client";
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
import { deleteAdministrativeLevel, putAdministrativeLevel } from "../mutations";
import { levelSchema, type LevelFormInput } from "../schemas";
import { FormDialog } from "./form-dialog";

/**
 * The hierarchy of places, rank by rank, each with the type its government
 * has and the types of body expected under it (spec section 4.4).
 */
export function LevelsTable({
  countryCode,
  levels,
  institutionTypes,
}: {
  countryCode: string;
  levels: AdministrativeLevelInput[];
  institutionTypes: InstitutionTypeInput[];
}) {
  const [editing, setEditing] = useState<AdministrativeLevelInput | "new" | null>(null);
  const [deleting, setDeleting] = useState<AdministrativeLevelInput | null>(null);
  const remove = useCountryMutation(
    (name: string) => deleteAdministrativeLevel(countryCode, name),
    "Level deleted",
  );
  const sorted = [...levels].sort((a, b) => a.rank - b.rank);

  return (
    <div className="flex flex-col gap-3">
      {sorted.length === 0 ? (
        <EmptyState>No levels yet.</EmptyState>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-0">Rank</TableHead>
                <TableHead>Level</TableHead>
                <TableHead>Government</TableHead>
                <TableHead>Expected institution types</TableHead>
                <TableHead className="w-0" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((level) => (
                <TableRow key={level.name}>
                  <TableCell className="tabular-nums">{level.rank}</TableCell>
                  <TableCell className="font-medium">{humanize(level.name)}</TableCell>
                  <TableCell>{humanize(level.government_institution_type)}</TableCell>
                  <TableCell className="min-w-48 max-w-md whitespace-normal text-muted-foreground">
                    {level.expected_institution_types.map(humanize).join(", ") || "–"}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Edit ${level.name}`}
                        onClick={() => setEditing(level)}
                      >
                        <PencilIcon />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Delete ${level.name}`}
                        onClick={() => setDeleting(level)}
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
        <Button variant="outline" onClick={() => setEditing("new")}>
          <PlusIcon /> Add level
        </Button>
      </div>
      {editing && (
        <LevelDialog
          countryCode={countryCode}
          level={editing === "new" ? null : editing}
          institutionTypes={institutionTypes}
          onClose={() => setEditing(null)}
        />
      )}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title={`Delete the ${deleting ? humanize(deleting.name).toLowerCase() : ""} level?`}
        description="Places at this level keep their rows; the rules stop expecting anything under it."
        pending={remove.isPending}
        onConfirm={() =>
          deleting && remove.mutateAsync(deleting.name).then(() => setDeleting(null))
        }
      />
    </div>
  );
}

function LevelDialog({
  countryCode,
  level,
  institutionTypes,
  onClose,
}: {
  countryCode: string;
  level: AdministrativeLevelInput | null;
  institutionTypes: InstitutionTypeInput[];
  onClose: () => void;
}) {
  const [serverError, setServerError] = useState<string | null>(null);
  const save = useCountryMutation(
    (body: AdministrativeLevelInput) => putAdministrativeLevel(countryCode, body),
    level ? "Level saved" : "Level added",
  );
  const form = useAppForm({
    defaultValues: {
      name: level?.name ?? "",
      rank: String(level?.rank ?? 0),
      government_institution_type: level?.government_institution_type ?? "",
      expected_institution_types: level?.expected_institution_types ?? [],
    } satisfies LevelFormInput as LevelFormInput,
    validationLogic: revalidateLogic(),
    validators: { onDynamic: levelSchema },
    onSubmit: async ({ value }) => {
      setServerError(null);
      try {
        await save.mutateAsync(levelSchema.parse(value));
        onClose();
      } catch (error) {
        setServerError(errorMessage(error));
      }
    },
  });
  const typeOptions = institutionTypes.map((t) => ({
    value: t.name,
    label: humanize(t.name),
    description: t.description || undefined,
  }));
  return (
    <FormDialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={level ? `Edit ${humanize(level.name).toLowerCase()}` : "Add a level"}
      form={form}
      serverError={serverError}
      submit={
        <form.AppForm>
          <form.SubmitButton>{level ? "Save" : "Add"}</form.SubmitButton>
        </form.AppForm>
      }
    >
      <div className="grid gap-4 sm:grid-cols-[1fr_6rem]">
        <form.AppField name="name">
          {(field) => (
            <field.TextField
              label="Name"
              required
              placeholder="municipality"
              autoComplete="off"
              disabled={level !== null}
            />
          )}
        </form.AppField>
        <form.AppField name="rank">
          {(field) => <field.TextField label="Rank" required type="number" min={0} />}
        </form.AppField>
      </div>
      <form.AppField name="government_institution_type">
        {(field) => (
          <field.SelectField
            label="Government's type"
            required
            options={typeOptions}
            placeholder="Choose a type"
            description="The institution type of a place's own government at this level."
          />
        )}
      </form.AppField>
      <form.Field name="expected_institution_types">
        {(field) => (
          <CheckboxGroup
            name={field.name}
            label="Expected institution types"
            description="What find_institutions looks for under a place at this level."
            options={typeOptions}
            value={field.state.value}
            onChange={field.handleChange}
            errors={field.state.meta.errors}
          />
        )}
      </form.Field>
    </FormDialog>
  );
}
