"use client";

import type { AdministrativeLevelInput, InstitutionTypeInput } from "@public-atlas/api-client";
import { revalidateLogic } from "@tanstack/react-form";
import { PencilIcon, PlusIcon, Trash2Icon } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { useAppForm } from "@/components/shared/form";
import { Button } from "@/components/ui/button";
import { FieldSeparator } from "@/components/ui/field";
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
import { FormDialog } from "@/components/shared/form-dialog";

/**
 * The hierarchy of places, rank by rank, each with the type its government
 * has and the types of body expected under it (spec section 4.4).
 */
export function LevelsTable({
  countryCode,
  countryName,
  levels,
  institutionTypes,
  countryTypes,
}: {
  countryCode: string;
  countryName: string;
  levels: AdministrativeLevelInput[];
  institutionTypes: InstitutionTypeInput[];
  /** The types the country uses: a level may only name these. */
  countryTypes: readonly string[];
}) {
  const [editing, setEditing] = useState<AdministrativeLevelInput | "new" | null>(null);
  const [deleting, setDeleting] = useState<AdministrativeLevelInput | null>(null);
  const remove = useCountryMutation(
    (name: string) => deleteAdministrativeLevel(countryCode, name),
    "Level deleted",
  );
  const sorted = [...levels].sort((a, b) => a.rank - b.rank);
  // A new level goes below the lowest one, the usual place to add one.
  const nextRank = Math.max(0, ...levels.map((level) => level.rank)) + 1;

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
          countryName={countryName}
          level={editing === "new" ? null : editing}
          nextRank={nextRank}
          institutionTypes={institutionTypes}
          countryTypes={countryTypes}
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

/** A type for a place's own government, by the shared seed's naming: `municipal_government`. */
function isGovernmentType(name: string) {
  return name.endsWith("_government");
}

function LevelDialog({
  countryCode,
  countryName,
  level,
  nextRank,
  institutionTypes,
  countryTypes,
  onClose,
}: {
  countryCode: string;
  countryName: string;
  level: AdministrativeLevelInput | null;
  nextRank: number;
  institutionTypes: InstitutionTypeInput[];
  countryTypes: readonly string[];
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
      rank: String(level?.rank ?? nextRank),
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

  const describe = (name: string) =>
    institutionTypes.find((type) => type.name === name)?.description || undefined;
  const option = (name: string) => ({
    value: name,
    label: humanize(name),
    description: describe(name),
  });
  // Only the types the country uses: the API refuses any other. A level being edited keeps
  // the types it has, so none of them drops out of view.
  const governmentOptions = countryTypes
    .filter((name) => isGovernmentType(name) || name === level?.government_institution_type)
    .map(option);
  const expectedOptions = countryTypes
    .filter((name) => !isGovernmentType(name) || level?.expected_institution_types.includes(name))
    .map(option);

  return (
    <FormDialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={level ? `Edit the ${humanize(level.name).toLowerCase()} level` : "Add a level"}
      description={
        level ? (
          <>
            <span className="font-mono text-xs">{level.name}</span> · rank {level.rank} in{" "}
            {countryName}&apos;s hierarchy of places
          </>
        ) : (
          `A step in ${countryName}'s hierarchy of places, with the bodies to look for at each place on it.`
        )
      }
      className="sm:max-w-xl"
      form={form}
      serverError={serverError}
      submit={
        <form.AppForm>
          <form.SubmitButton requireChanges={level !== null}>
            {level ? "Save" : "Add level"}
          </form.SubmitButton>
        </form.AppForm>
      }
    >
      <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_7rem]">
        <form.AppField name="name">
          {(field) => (
            <field.TextField
              label="Name"
              required
              placeholder="regional_district"
              autoComplete="off"
              disabled={level !== null}
              description={
                field.state.value.trim()
                  ? `Shown as “${humanize(field.state.value.trim())}”.`
                  : "Lower case, words joined by underscores."
              }
            />
          )}
        </form.AppField>
        <form.AppField name="rank">
          {(field) => (
            <field.TextField
              label="Rank"
              required
              type="number"
              min={1}
              description="The country is 1."
            />
          )}
        </form.AppField>
      </div>
      <FieldSeparator />
      <form.AppField name="government_institution_type">
        {(field) => (
          <field.SelectField
            label="Government"
            required
            options={governmentOptions}
            placeholder="Choose the government's type"
            description={
              governmentOptions.length === 0
                ? `${countryName} uses no government type yet. Add one under Institution types first.`
                : (describe(field.state.value) ??
                  "The type of a place's own government at this level.")
            }
          />
        )}
      </form.AppField>
      <form.AppField name="expected_institution_types">
        {(field) => (
          <field.MultiSelectField
            label="Expected institution types"
            options={expectedOptions}
            placeholder="Search the country's types…"
            description="The checklist find_institutions works through under each place at this level. The government is found on its own."
          />
        )}
      </form.AppField>
    </FormDialog>
  );
}
