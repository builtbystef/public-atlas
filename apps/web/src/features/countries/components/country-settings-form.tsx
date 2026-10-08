"use client";

import type { CountrySettingsInput, NamingRules } from "@public-atlas/api-client";
import { revalidateLogic } from "@tanstack/react-form";
import { useQuery } from "@tanstack/react-query";
import { CheckIcon, Loader2Icon, PencilIcon, PlusIcon, Trash2Icon, XIcon } from "lucide-react";
import { useRef, useState, type FormEvent, type ReactNode } from "react";

import { ChipInput } from "@/components/shared/chip-input";
import { Form, FormError, useAppForm } from "@/components/shared/form";
import { Button } from "@/components/ui/button";
import { FieldDescription, FieldLegend, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { browserApi } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

import { useCountryMutation } from "../hooks/use-country-mutations";
import { putCountrySettings } from "../mutations";
import { namingPreviewQuery } from "../queries";
import {
  countryNameSchema,
  namingRulesSchema,
  namingRulesToForm,
  sharedDesignators,
  type NamingRulesFormInput,
} from "../schemas";

/**
 * The country's name as the page's title, with a pen beside it that turns it
 * into an input: Enter saves, Escape puts the name back. Saved on its own,
 * with the naming rules as they are stored.
 */
export function CountryNameTitle({
  settings,
  flag,
}: {
  settings: CountrySettingsInput;
  flag: ReactNode;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(settings.name);
  const [error, setError] = useState<string | null>(null);
  const pen = useRef<HTMLButtonElement>(null);
  const save = useCountryMutation(
    (body: CountrySettingsInput) => putCountrySettings(settings.country_code, body),
    "Name saved",
  );

  const open = () => {
    setDraft(settings.name);
    setError(null);
    setEditing(true);
  };
  const close = () => {
    setEditing(false);
    // Back to the pen, which renders again once the input is gone.
    requestAnimationFrame(() => pen.current?.focus());
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const parsed = countryNameSchema.safeParse({ name: draft });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Not a name");
      return;
    }
    if (parsed.data.name !== settings.name) {
      try {
        await save.mutateAsync({ ...settings, ...parsed.data });
      } catch {
        return; // The mutation says why.
      }
    }
    close();
  };

  if (!editing) {
    return (
      <span className="flex items-center gap-3">
        {flag}
        <span className="min-w-0 truncate">{settings.name}</span>
        <Button
          ref={pen}
          variant="ghost"
          size="icon-sm"
          aria-label="Rename the country"
          title="Rename"
          onClick={open}
          className="text-muted-foreground"
        >
          <PencilIcon aria-hidden="true" />
        </Button>
      </span>
    );
  }
  return (
    <span className="flex items-start gap-3">
      {/* Level with the input's first line. */}
      <span className="flex h-10 shrink-0 items-center">{flag}</span>
      <form onSubmit={submit} className="flex min-w-0 flex-col gap-1">
        <span className="flex items-center gap-1">
          <Input
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value);
              setError(null);
            }}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                close();
              }
            }}
            aria-label="Country name"
            aria-invalid={error !== null}
            aria-describedby={error ? "country-name-error" : undefined}
            autoFocus
            autoComplete="off"
            maxLength={100}
            disabled={save.isPending}
            className="h-10 w-80 max-w-full px-2 text-2xl font-semibold tracking-tight md:text-2xl"
          />
          <Button
            type="submit"
            variant="ghost"
            size="icon-sm"
            aria-label="Save the name"
            title="Save"
            disabled={save.isPending}
          >
            {save.isPending ? (
              <Loader2Icon className="animate-spin" aria-hidden="true" />
            ) : (
              <CheckIcon aria-hidden="true" />
            )}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Cancel renaming"
            title="Cancel"
            onClick={close}
            disabled={save.isPending}
            className="text-muted-foreground"
          >
            <XIcon aria-hidden="true" />
          </Button>
        </span>
        {error && (
          <span
            id="country-name-error"
            role="alert"
            className="text-sm font-normal tracking-normal text-destructive"
          >
            {error}
          </span>
        )}
      </form>
    </span>
  );
}

/**
 * The naming rules the duplicate search and the name checks use, each list
 * as chips, with a preview of how the rules as edited read a name. Saved on
 * their own, from a bar that stays in view while there are changes.
 */
export function NamingRulesForm({ settings }: { settings: CountrySettingsInput }) {
  const [serverError, setServerError] = useState<string | null>(null);
  const save = useCountryMutation(
    (body: CountrySettingsInput) => putCountrySettings(settings.country_code, body),
    "Naming rules saved",
  );
  const form = useAppForm({
    defaultValues: namingRulesToForm(settings.naming_rules) satisfies NamingRulesFormInput,
    validationLogic: revalidateLogic(),
    validators: { onDynamic: namingRulesSchema },
    onSubmit: async ({ value, formApi }) => {
      setServerError(null);
      try {
        const saved = await save.mutateAsync({
          ...settings,
          naming_rules: namingRulesSchema.parse(value),
        });
        formApi.reset(namingRulesToForm(saved.naming_rules));
      } catch (error) {
        setServerError(errorMessage(error));
      }
    },
  });
  return (
    <Form form={form} warnOnLeave>
      <FormError message={serverError} />
      <form.Subscribe selector={(state) => state.values}>
        {(values) => <NamingPreviewPanel values={values} />}
      </form.Subscribe>
      <form.Field name="designators">
        {(field) => (
          <DesignatorGroups
            value={field.state.value}
            onChange={field.handleChange}
            onBlur={field.handleBlur}
          />
        )}
      </form.Field>
      <form.AppField name="connectors">
        {(field) => (
          <field.ChipsField
            label="Connectors"
            placeholder="of the, de la, d'"
            description="What joins a designator to the place name: the “of” in “Township of Elmwood”."
          />
        )}
      </form.AppField>
      <form.AppField name="leading">
        {(field) => (
          <field.ChipsField
            label="Leading words"
            placeholder="The Corporation of the, The"
            description="Words before a body's name that are not part of it."
          />
        )}
      </form.AppField>
      <form.AppField name="and_words">
        {(field) => (
          <field.ChipsField
            label="And words"
            placeholder="and, et"
            description="Read as “&”, so “Elm & Oak” and “Elm and Oak” are one name."
          />
        )}
      </form.AppField>
      <p className="text-xs text-muted-foreground">
        Order does not matter: the longest phrase is always tried first.
      </p>
      <form.Subscribe selector={(state) => !state.isDefaultValue}>
        {(dirty) => (
          <div
            className={cn(
              "flex flex-wrap items-center justify-end gap-2",
              dirty &&
                "sticky bottom-4 z-10 rounded-xl border bg-background/95 p-3 shadow-lg backdrop-blur-sm",
            )}
          >
            {dirty && (
              <>
                <p className="mr-auto text-sm text-muted-foreground">
                  Unsaved changes to the naming rules
                </p>
                <Button type="button" variant="ghost" onClick={() => form.reset()}>
                  Discard
                </Button>
              </>
            )}
            <form.AppForm>
              <form.SubmitButton requireChanges>Save naming rules</form.SubmitButton>
            </form.AppForm>
          </div>
        )}
      </form.Subscribe>
    </Form>
  );
}

/**
 * One row of chips per designator group. A word in two groups is marked:
 * a name that uses it matches either kind of body, which is sometimes meant
 * ("Ville" is a city and a town) and sometimes a slip.
 */
function DesignatorGroups({
  value,
  onChange,
  onBlur,
}: {
  value: string[][];
  onChange: (value: string[][]) => void;
  onBlur: () => void;
}) {
  const shared = sharedDesignators(value);
  const groupName = (index: number) => value[index]?.[0] ?? `row ${index + 1}`;
  const otherGroups = (word: string, index: number) =>
    (shared.get(word.trim().toLocaleLowerCase())?.rows ?? []).filter((i) => i !== index);

  return (
    <FieldSet className="gap-2">
      <FieldLegend variant="label" className="mb-0">
        Designators
      </FieldLegend>
      <FieldDescription>
        One row per kind of body, with its word in each language. Names that differ only by
        designators in the same row are the same place.
      </FieldDescription>
      {value.length > 0 && (
        <ol className="mt-1 flex flex-col gap-2">
          {value.map((group, index) => (
            // Rows have no identity but their position; a row's draft is
            // committed on blur, before any remove button can be pressed.
            <li key={index} className="flex items-center gap-2">
              <span className="w-5 shrink-0 text-right text-xs text-muted-foreground tabular-nums">
                {index + 1}
              </span>
              <ChipInput
                aria-label={`Designator group ${index + 1}`}
                value={group}
                onChange={(words) => onChange(value.map((g, i) => (i === index ? words : g)))}
                onBlur={onBlur}
                placeholder="City, Ville"
                chipClassName={(word) =>
                  otherGroups(word, index).length > 0
                    ? "bg-warning/15 text-warning ring-1 ring-warning/30 ring-inset"
                    : undefined
                }
                chipTitle={(word) => {
                  const others = otherGroups(word, index);
                  return others.length > 0
                    ? `Also in ${others.map((i) => `“${groupName(i)}”`).join(", ")}`
                    : undefined;
                }}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`Remove designator group ${index + 1}`}
                onClick={() => onChange(value.filter((_, i) => i !== index))}
              >
                <Trash2Icon />
              </Button>
            </li>
          ))}
        </ol>
      )}
      <div>
        <Button type="button" variant="outline" size="sm" onClick={() => onChange([...value, []])}>
          <PlusIcon /> Add group
        </Button>
      </div>
      {shared.size > 0 && (
        <p className="text-xs text-muted-foreground">
          <span className="font-medium text-warning">In more than one group:</span>{" "}
          {[...shared.values()]
            .map(({ word, rows }) => `${word} (${rows.map(groupName).join(", ")})`)
            .join("; ")}
          . A name using one matches either kind.
        </p>
      )}
    </FieldSet>
  );
}

/**
 * A name typed in, read by the rules as they stand in the form: the place
 * name the rules find inside it and the designators it uses. Asked of the
 * server, so it is the same code the agent's checks run.
 */
function NamingPreviewPanel({ values }: { values: NamingRulesFormInput }) {
  const [name, setName] = useState("");
  // Debounce the form's values, not the parsed rules: those are a new object
  // every render, and would restart the timer forever.
  const debouncedValues = useDebouncedValue(values, 300);
  const debouncedName = useDebouncedValue(name.trim(), 300);
  const parsed = namingRulesSchema.safeParse(debouncedValues);
  const rules: NamingRules = parsed.success
    ? parsed.data
    : { designators: [], connectors: [], leading: [], and_words: [] };
  const preview = useQuery(namingPreviewQuery(browserApi, rules, debouncedName));
  const groupName = (index: number) => rules.designators[index]?.[0] ?? `Group ${index + 1}`;

  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-muted/40 p-3">
      <div className="flex flex-col gap-1.5">
        <label htmlFor="naming-preview" className="text-sm font-medium">
          Try a name
        </label>
        <Input
          id="naming-preview"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="The Corporation of the Township of Elmwood"
          autoComplete="off"
          className="bg-background"
        />
      </div>
      {debouncedName === "" || preview.data === undefined ? (
        <p className="text-xs text-muted-foreground">
          {preview.isFetching ? (
            <Loader2Icon className="inline size-3 animate-spin" aria-label="Reading the name" />
          ) : (
            "See how the rules below read a body's name, as you edit them and before you save."
          )}
        </p>
      ) : preview.isError ? (
        <p className="text-xs text-destructive">{errorMessage(preview.error)}</p>
      ) : (
        <dl
          className={cn(
            "grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm transition-opacity",
            preview.isFetching && "opacity-60",
          )}
          aria-live="polite"
        >
          <dt className="text-muted-foreground">Place name</dt>
          <dd className="font-medium">{preview.data.core || "–"}</dd>
          <dt className="text-muted-foreground">Designators</dt>
          <dd className="flex flex-wrap gap-1">
            {preview.data.designator_groups.length === 0 ? (
              <span className="text-muted-foreground">None found</span>
            ) : (
              preview.data.designator_groups.map((index) => (
                <span
                  key={index}
                  className="rounded-md bg-background px-1.5 py-0.5 text-xs font-medium ring-1 ring-border"
                >
                  {groupName(index)}
                </span>
              ))
            )}
          </dd>
          <dt className="text-muted-foreground">Compared as</dt>
          <dd className="font-mono text-xs leading-5 break-words text-muted-foreground">
            {preview.data.forms.join(" · ")}
          </dd>
        </dl>
      )}
    </div>
  );
}
