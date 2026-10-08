"use client";

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
import { errorMessage } from "@/lib/api/errors";
import { assignmentTypeLabels, assignmentTypes } from "@/lib/labels";

import { releaseSchema, type ReleaseFormInput } from "../schemas";

const typeOptions = assignmentTypes.map((value) => ({ value, label: assignmentTypeLabels[value] }));

/** Queues the next held assignments of a step-mode run: how many, and of which type. */
export function ReleaseDialog({
  open,
  onOpenChange,
  held,
  onRelease,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** How many the run holds, for the description. */
  held: number;
  onRelease: (values: { limit: number; assignment_type: string }) => Promise<unknown>;
}) {
  const [serverError, setServerError] = useState<string | null>(null);
  const form = useAppForm({
    defaultValues: {
      limit: "1",
      assignment_type: "",
    } satisfies ReleaseFormInput as ReleaseFormInput,
    validationLogic: revalidateLogic(),
    validators: { onDynamic: releaseSchema },
    onSubmit: async ({ value }) => {
      setServerError(null);
      try {
        await onRelease(releaseSchema.parse(value));
        onOpenChange(false);
      } catch (error) {
        setServerError(errorMessage(error));
      }
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Release held assignments</DialogTitle>
          <DialogDescription>
            {held === 1 ? "One assignment is held." : `${held} assignments are held.`}
          </DialogDescription>
        </DialogHeader>
        <Form form={form} className="gap-4">
          <FormError message={serverError} />
          <form.AppField name="limit">
            {(field) => <field.TextField label="How many" type="number" min={1} max={500} />}
          </form.AppField>
          <form.AppField name="assignment_type">
            {(field) => (
              <field.SelectField label="Of type" options={typeOptions} placeholder="Any type" />
            )}
          </form.AppField>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
            <form.AppForm>
              <form.SubmitButton>Release</form.SubmitButton>
            </form.AppForm>
          </DialogFooter>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
