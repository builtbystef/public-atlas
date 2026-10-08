"use client";

import { revalidateLogic, useStore } from "@tanstack/react-form";
import { useState, type ReactNode } from "react";

import { useAppForm } from "@/components/shared/form";
import { errorMessage } from "@/lib/api/errors";

import { decisionSchema, type DecisionFormInput } from "../schemas";
import { DecisionFrame } from "./decision-frame";

/**
 * Approve or reject, with a note for the record. An approval of an
 * institution may also give it its type, which a body saved as `other` or
 * raised as a new type needs.
 */
export function DecisionDialog({
  open,
  onOpenChange,
  title,
  subject,
  description,
  confirmLabel,
  details,
  destructive = false,
  typeField,
  preview,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** What is decided on, such as the entity's name. */
  subject?: ReactNode;
  description: ReactNode;
  /** Under the description, such as the entities a decision on several items changes. */
  details?: ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  /** Shows the institution type field, prefilled with this; omit to hide it. */
  typeField?: { initial: string; description: string } | undefined;
  /** What the decision would do, given the type typed so far ("" when none). */
  preview?: (values: { institution_type: string }) => ReactNode;
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
  const institutionType = useStore(form.store, (state) => state.values.institution_type);
  return (
    <DecisionFrame
      open={open}
      onOpenChange={onOpenChange}
      tone={destructive ? "reject" : "approve"}
      title={title}
      subject={subject}
      description={description}
      form={form}
      serverError={serverError}
      submit={(className) => (
        <form.AppForm>
          <form.SubmitButton className={className}>{confirmLabel}</form.SubmitButton>
        </form.AppForm>
      )}
    >
      {details}
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
      {preview?.({ institution_type: institutionType.trim() })}
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
