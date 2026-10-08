"use client";

import type { EntityKind } from "@public-atlas/api-client";
import { useQuery } from "@tanstack/react-query";
import { revalidateLogic, useStore } from "@tanstack/react-form";
import { useState, type ReactNode } from "react";
import { z } from "zod";

import { useAppForm } from "@/components/shared/form";
import {
  institutionOptionQuery,
  institutionPickerQuery,
  placeOptionQuery,
  placePickerQuery,
} from "@/features/graph/queries";
import { browserApi } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { entityKindLabels } from "@/lib/labels";

import { mergeSchema, type MergeFormInput } from "../schemas";
import { DecisionFrame } from "./decision-frame";

/** Picks the entity this one is a duplicate of; the item's entity is folded into it. */
export function MergeDialog({
  open,
  onOpenChange,
  label,
  entityKind,
  initialIntoId,
  preview,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  label: string;
  entityKind: EntityKind;
  /** The entity chosen to begin with; the reviewer can still pick another. */
  initialIntoId?: string | undefined;
  /** What the merge would do, once an entity to merge into is chosen. */
  preview?: (into: { id: string; name: string }) => ReactNode;
  onConfirm: (values: { into_id: string; note: string | null }) => Promise<unknown>;
}) {
  const [serverError, setServerError] = useState<string | null>(null);
  const form = useAppForm({
    defaultValues: { into_id: initialIntoId ?? "", note: "" } satisfies MergeFormInput,
    validationLogic: revalidateLogic(),
    validators: { onDynamic: mergeSchema },
    onSubmit: async ({ value }) => {
      setServerError(null);
      try {
        await onConfirm(mergeSchema.parse(value));
        onOpenChange(false);
      } catch (error) {
        setServerError(errorMessage(error));
      }
    },
  });
  const places = entityKind === "place";
  const intoId = useStore(form.store, (state) => state.values.into_id);
  const chosen = z.uuid().safeParse(intoId).success;
  // The chosen entity's name, which the picker has loaded already.
  const place = useQuery({ ...placeOptionQuery(browserApi, intoId), enabled: chosen && places });
  const institution = useQuery({
    ...institutionOptionQuery(browserApi, intoId),
    enabled: chosen && !places,
  });
  const target = places ? place : institution;
  return (
    <DecisionFrame
      open={open}
      onOpenChange={onOpenChange}
      tone="merge"
      title={`Merge this ${entityKindLabels[entityKind].toLowerCase()}`}
      subject={label}
      description="Its names, evidence, homepages, sources and open assignments move to the one you choose, and it is marked as merged. This cannot be undone."
      form={form}
      serverError={serverError}
      submit={(className) => (
        <form.AppForm>
          <form.SubmitButton className={className}>Merge</form.SubmitButton>
        </form.AppForm>
      )}
    >
      {places ? (
        <form.AppField name="into_id">
          {(field) => (
            <field.ComboboxField
              label="Merge into"
              required
              placeholder="Search places"
              search={(q) => placePickerQuery(browserApi, q)}
              resolve={(id) => placeOptionQuery(browserApi, id)}
            />
          )}
        </form.AppField>
      ) : (
        <form.AppField name="into_id">
          {(field) => (
            <field.ComboboxField
              label="Merge into"
              required
              placeholder="Search institutions"
              search={(q) => institutionPickerQuery(browserApi, q)}
              resolve={(id) => institutionOptionQuery(browserApi, id)}
            />
          )}
        </form.AppField>
      )}
      {chosen && preview?.({ id: intoId, name: target.data?.name ?? "the one chosen" })}
      <form.AppField name="note">
        {(field) => (
          <field.TextareaField
            label="Note (optional)"
            rows={2}
            placeholder="Why, for the next reader."
          />
        )}
      </form.AppField>
    </DecisionFrame>
  );
}
