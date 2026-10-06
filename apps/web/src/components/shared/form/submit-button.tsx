"use client";

import { Loader2Icon } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";

import { useFormContext } from "./contexts";

export function SubmitButton({
  children,
  className,
  disabled = false,
  requireChanges = false,
}: {
  children: ReactNode;
  className?: string;
  /** Beyond "while submitting": when the form can no longer succeed. */
  disabled?: boolean;
  /** For edit forms: there is nothing to save until a value differs from the record. */
  requireChanges?: boolean;
}) {
  const form = useFormContext();
  return (
    <form.Subscribe
      selector={(state) => ({ isSubmitting: state.isSubmitting, unchanged: state.isDefaultValue })}
    >
      {({ isSubmitting, unchanged }) => (
        <Button
          type="submit"
          disabled={disabled || isSubmitting || (requireChanges && unchanged)}
          className={className}
        >
          {isSubmitting && <Loader2Icon className="animate-spin" />}
          {children}
        </Button>
      )}
    </form.Subscribe>
  );
}
