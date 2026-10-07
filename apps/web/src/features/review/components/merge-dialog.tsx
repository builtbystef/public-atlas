"use client";

import type { EntityKind } from "@public-atlas/api-client";
import { revalidateLogic } from "@tanstack/react-form";
import { useState } from "react";

import { Form, FormError, useAppForm } from "@/components/shared/form";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  institutionOptionQuery,
  institutionPickerQuery,
  placeOptionQuery,
  placePickerQuery,
} from "@/features/graph/queries";
import { browserApi } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";

import { mergeSchema, type MergeFormInput } from "../schemas";

/** Picks the entity this one is a duplicate of; the item's entity is folded into it. */
export function MergeDialog({
  open,
  onOpenChange,
  label,
  entityKind,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  label: string;
  entityKind: EntityKind;
  onConfirm: (values: { into_id: string; note: string | null }) => Promise<unknown>;
}) {
  const [serverError, setServerError] = useState<string | null>(null);
  const form = useAppForm({
    defaultValues: { into_id: "", note: "" } satisfies MergeFormInput,
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
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Merge “{label}”</DialogTitle>
          <DialogDescription>
            Its names, evidence, homepages, sources and open assignments move to the one you choose,
            and it is marked as merged. This cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <Form form={form} className="gap-4">
          <FormError message={serverError} />
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
          <form.AppField name="note">
            {(field) => <field.TextareaField label="Note" rows={3} />}
          </form.AppField>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
            <form.AppForm>
              <form.SubmitButton>Merge</form.SubmitButton>
            </form.AppForm>
          </DialogFooter>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
