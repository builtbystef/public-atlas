"use client";

import type {
  CountryInstitutionTypeInput,
  InstitutionTypeInput,
  SourceTypeInput,
} from "@public-atlas/api-client";
import { revalidateLogic } from "@tanstack/react-form";
import { useQuery } from "@tanstack/react-query";
import {
  CircleCheckIcon,
  Loader2Icon,
  PencilIcon,
  PlusIcon,
  Trash2Icon,
  TriangleAlertIcon,
} from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { CheckboxGroup } from "@/components/shared/checkbox-group";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { useAppForm } from "@/components/shared/form";
import { FormDialog } from "@/components/shared/form-dialog";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { browserApi } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { humanize } from "@/lib/labels";
import { paths } from "@/lib/routes";
import { cn } from "@/lib/utils";

import { useCountryMutation } from "../hooks/use-country-mutations";
import { deleteCountryInstitutionType, putCountryInstitutionType } from "../mutations";
import { namePatternCheckQuery } from "../queries";
import { countryTypeSchema, type CountryTypeFormInput } from "../schemas";

/**
 * The country's use of each institution type: the sources find_sources
 * expects on its homepage, and the name pattern a body of the type follows.
 */
export function CountryTypesTable({
  countryCode,
  countryName,
  rows,
  institutionTypes,
  sourceTypes,
  defaultSources,
}: {
  countryCode: string;
  countryName: string;
  rows: CountryInstitutionTypeInput[];
  institutionTypes: InstitutionTypeInput[];
  sourceTypes: SourceTypeInput[];
  /** The sources a newly added type starts with, by type. */
  defaultSources: Record<string, string[]>;
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
        {unused.length > 0 ? (
          <Button variant="outline" onClick={() => setEditing("new")}>
            <PlusIcon /> Add type
          </Button>
        ) : (
          // A disabled button takes no pointer events, so the tooltip hangs
          // on a focusable wrapper.
          <Tooltip>
            <TooltipTrigger
              render={<span tabIndex={0} className="inline-flex w-fit rounded-lg outline-none" />}
            >
              <Button variant="outline" disabled>
                <PlusIcon /> Add type
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              The country uses every institution type. Create a new one on the Country config page
              first.
            </TooltipContent>
          </Tooltip>
        )}
      </div>
      {editing && (
        <CountryTypeDialog
          countryCode={countryCode}
          countryName={countryName}
          row={editing === "new" ? null : editing}
          institutionTypes={editing === "new" ? unused : institutionTypes}
          sourceTypes={sourceTypes}
          defaultSources={defaultSources}
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
  countryName,
  row,
  institutionTypes,
  sourceTypes,
  defaultSources,
  onClose,
}: {
  countryCode: string;
  countryName: string;
  row: CountryInstitutionTypeInput | null;
  institutionTypes: InstitutionTypeInput[];
  sourceTypes: SourceTypeInput[];
  defaultSources: Record<string, string[]>;
  onClose: () => void;
}) {
  const [serverError, setServerError] = useState<string | null>(null);
  // While adding, the sources follow the chosen type's defaults until they
  // are edited by hand.
  const sourcesEdited = useRef(row !== null);
  const save = useCountryMutation(
    (body: CountryInstitutionTypeInput) => putCountryInstitutionType(countryCode, body),
    row ? "Type saved" : "Type added",
  );
  const allSources = sourceTypes.map((t) => t.name);
  /** `names` in the order the checkboxes list them, as the group keeps its value. */
  const inOrder = (names: readonly string[]) => allSources.filter((name) => names.includes(name));
  const defaultsFor = (type: string) => inOrder(defaultSources[type] ?? []);
  const typeNamed = (name: string) => institutionTypes.find((t) => t.name === name);

  const firstType = row?.institution_type ?? institutionTypes[0]?.name ?? "";
  const form = useAppForm({
    defaultValues: {
      institution_type: firstType,
      expected_source_types: row?.expected_source_types ?? defaultsFor(firstType),
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

  const description = row ? (
    <>
      <span className="font-mono text-xs">{row.institution_type}</span>
      {typeNamed(row.institution_type)?.description && (
        <> · {typeNamed(row.institution_type)?.description}</>
      )}
    </>
  ) : (
    "Choose a type for the country to use. It starts with the type's default sources."
  );

  return (
    <FormDialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={row ? `Edit ${humanize(row.institution_type).toLowerCase()}` : "Add a type"}
      description={description}
      className="sm:max-w-2xl"
      form={form}
      serverError={serverError}
      submit={
        <form.AppForm>
          <form.SubmitButton requireChanges={row !== null}>
            {row ? "Save" : "Add"}
          </form.SubmitButton>
        </form.AppForm>
      }
    >
      {/* Editing, the type is the dialog's subject: it cannot change. */}
      {row === null && (
        <form.AppField
          name="institution_type"
          listeners={{
            onChange: ({ value }) => {
              if (!sourcesEdited.current) {
                form.setFieldValue("expected_source_types", defaultsFor(value));
              }
            },
          }}
        >
          {(field) => (
            <field.SelectField
              label="Institution type"
              required
              options={institutionTypes.map((t) => ({ value: t.name, label: humanize(t.name) }))}
              description={typeNamed(field.state.value)?.description}
            />
          )}
        </form.AppField>
      )}
      <form.Subscribe selector={(state) => state.values.institution_type}>
        {(type) => (
          <form.Field name="expected_source_types">
            {(field) => {
              const value = field.state.value;
              const defaults = defaultsFor(type);
              const isDefault =
                value.length === defaults.length && defaults.every((s) => value.includes(s));
              const choose = (next: string[], edited = true) => {
                sourcesEdited.current = edited;
                field.handleChange(next);
              };
              return (
                <CheckboxGroup
                  name={field.name}
                  label="Expected source types"
                  description="What find_sources looks for on a body of this type."
                  clampDescriptions
                  options={sourceTypes.map((t) => ({
                    value: t.name,
                    label: humanize(t.name),
                    description: t.description || undefined,
                  }))}
                  value={value}
                  onChange={(next) => choose(next)}
                  errors={field.state.meta.errors}
                  actions={
                    <>
                      <span className="mr-1 text-xs text-muted-foreground tabular-nums">
                        {value.length} of {allSources.length}
                      </span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="xs"
                        disabled={value.length === allSources.length}
                        onClick={() => choose(allSources)}
                      >
                        All
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="xs"
                        disabled={value.length === 0}
                        onClick={() => choose([])}
                      >
                        None
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="xs"
                        disabled={defaults.length === 0 || isDefault}
                        title={
                          defaults.length === 0 ? "This type has no default sources" : undefined
                        }
                        onClick={() => choose(defaults, false)}
                      >
                        Reset to defaults
                      </Button>
                    </>
                  }
                />
              );
            }}
          </form.Field>
        )}
      </form.Subscribe>
      <form.AppField name="name_pattern">
        {(field) => (
          <field.TextField
            label="Name pattern"
            description="A regular expression searched for in a body's name, ignoring case. A name it misses goes to review."
            placeholder="\bschool board\b"
            autoComplete="off"
            spellCheck={false}
            className="font-mono"
          />
        )}
      </form.AppField>
      <form.Subscribe
        selector={(state) => [state.values.institution_type, state.values.name_pattern] as const}
      >
        {([type, pattern]) => (
          <NamePatternCheckPanel
            countryCode={countryCode}
            countryName={countryName}
            type={type}
            pattern={pattern}
          />
        )}
      </form.Subscribe>
    </FormDialog>
  );
}

/**
 * The name pattern as typed, tried on the country's institutions of the
 * type: how many match, and the ones that would go to review. The server
 * compiles it, so a pattern that works here works for the agent.
 */
function NamePatternCheckPanel({
  countryCode,
  countryName,
  type,
  pattern,
}: {
  countryCode: string;
  countryName: string;
  type: string;
  pattern: string;
}) {
  const typed = pattern.trim();
  const debounced = useDebouncedValue(typed, 400);
  const check = useQuery(namePatternCheckQuery(browserApi, countryCode, type, debounced));
  if (typed === "") {
    return <p className="-mt-2 text-xs text-muted-foreground">No pattern: every name passes.</p>;
  }
  if (check.isError) {
    return <p className="text-sm text-destructive">{errorMessage(check.error)}</p>;
  }
  if (check.data === undefined) {
    return (
      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2Icon className="size-3 animate-spin" aria-hidden="true" />
        Trying the pattern on {countryName}'s names…
      </p>
    );
  }
  const stale = typed !== debounced || check.isPlaceholderData;
  const { error, total, matching, misses } = check.data;
  const missed = total - matching;
  return (
    <div
      aria-live="polite"
      className={cn(
        "-mt-2 flex flex-col gap-2 rounded-lg border bg-muted/40 p-3 text-sm transition-opacity",
        stale && "opacity-60",
      )}
    >
      {error !== null ? (
        <p className="text-destructive">{error.charAt(0).toUpperCase() + error.slice(1)}</p>
      ) : total === 0 ? (
        <p className="text-muted-foreground">
          No {humanize(type).toLowerCase()} in {countryName} yet to try the pattern on.
        </p>
      ) : (
        <>
          <p className="flex items-center gap-2">
            {missed === 0 ? (
              <CircleCheckIcon className="size-4 text-success" aria-hidden="true" />
            ) : (
              <TriangleAlertIcon className="size-4 text-warning" aria-hidden="true" />
            )}
            <span>
              <span className="font-medium tabular-nums">
                {matching} of {total}
              </span>{" "}
              {humanize(type).toLowerCase()} names in {countryName} match
              {missed > 0 && (
                <>
                  ; <span className="tabular-nums">{missed}</span> would go to review
                </>
              )}
              .
            </span>
          </p>
          {misses.length > 0 && (
            <ul className="max-h-36 space-y-0.5 overflow-y-auto pl-6">
              {misses.map((miss) => (
                <li key={miss.id} className="truncate">
                  <Link
                    href={paths.institution(miss.id)}
                    target="_blank"
                    className="text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                  >
                    {miss.name}
                  </Link>
                </li>
              ))}
              {missed > misses.length && (
                <li className="text-xs text-muted-foreground">and {missed - misses.length} more</li>
              )}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
