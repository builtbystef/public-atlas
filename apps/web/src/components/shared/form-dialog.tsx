"use client";

import type { AnyFormApi } from "@tanstack/react-form";
import type { ReactNode } from "react";

import { Form, FormError } from "@/components/shared/form";
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
import { cn } from "@/lib/utils";

/** A dialog around a `useAppForm` form: title, fields, cancel and submit. */
export function FormDialog({
  open,
  onOpenChange,
  title,
  description,
  form,
  serverError,
  submit,
  className,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  form: AnyFormApi;
  serverError: string | null;
  /** The submit button, rendered by the caller so it is bound to its form. */
  submit: ReactNode;
  /** For the dialog box: a wider one than `sm:max-w-lg`. */
  className?: string;
  children: ReactNode;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn("max-h-[90svh] overflow-y-auto sm:max-w-lg", className)}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <Form form={form} className="gap-4">
          <FormError message={serverError} />
          {children}
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
            {submit}
          </DialogFooter>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
