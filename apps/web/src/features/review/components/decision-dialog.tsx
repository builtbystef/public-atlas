"use client";

import { revalidateLogic } from "@tanstack/react-form";
import { useState, type ReactNode } from "react";

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

import { decisionSchema, type DecisionFormInput } from "../schemas";

/**
 * Approve or reject, with a note for the record. An approval of an
 * institution may also give it its type, which a body saved as `other` or
 * raised as a new type needs.
 */
export function DecisionDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  destructive = false,
  typeField,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  /** Shows the institution type field, prefilled with this; omit to hide it. */
  typeField?: { initial: string; description: string } | undefined;
  onConfirm: (values: { note: string | null; institution_type: string | null }) => Promise<unknown>;
}) {
  const [serverError, setServerError] = useState<string | null>(null);
  const form = useAppForm({
    defaultValues: {
      note: "",
      institution_type: typeField?.initial ?? "",
    } satisfies DecisionFormInput,
    validationLogic: revalidateLogic(),
    validators: { onDynamic: decisionSchema },
    onSubmit: async ({ value }) => {
      setServerError(null);
      try {
        await onConfirm(decisionSchema.parse(value));
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
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <Form form={form} className="gap-4">
          <FormError message={serverError} />
          {typeField && (
            <form.AppField name="institution_type">
              {(field) => (
                <field.TextField
                  label="Institution type"
                  description={typeField.description}
                  placeholder="school_board"
                  autoComplete="off"
                />
              )}
            </form.AppField>
          )}
          <form.AppField name="note">
            {(field) => (
              <field.TextareaField label="Note" rows={3} placeholder="Why, for the next reader." />
            )}
          </form.AppField>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
            <form.AppForm>
              <form.SubmitButton
                className={
                  destructive ? "bg-destructive text-white hover:bg-destructive/90" : undefined
                }
              >
                {confirmLabel}
              </form.SubmitButton>
            </form.AppForm>
          </DialogFooter>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
