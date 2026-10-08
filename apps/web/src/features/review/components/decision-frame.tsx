"use client";

import type { AnyFormApi } from "@tanstack/react-form";
import { CircleCheckIcon, CircleXIcon, MergeIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Form, FormError } from "@/components/shared/form";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

/** What a decision does to its entity, which sets the dialog's colour and icon. */
export type DecisionTone = "approve" | "merge" | "reject";

const TONES: Record<DecisionTone, { icon: ReactNode; badge: string; confirm: string }> = {
  approve: {
    icon: <CircleCheckIcon />,
    badge: "bg-success/10 text-success",
    confirm: "bg-success text-success-foreground hover:bg-success/90",
  },
  merge: {
    icon: <MergeIcon />,
    badge: "bg-primary/10 text-primary",
    confirm: "",
  },
  reject: {
    icon: <CircleXIcon />,
    badge: "bg-destructive/10 text-destructive",
    confirm: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
  },
};

/**
 * The frame every review decision shares: an icon in the decision's colour,
 * what is decided on and what that means, the dialog's own fields, and a
 * confirm button in the same colour. `submit` renders the button, so it is
 * bound to the caller's form; `confirmClass` is the class to give it.
 */
export function DecisionFrame({
  open,
  onOpenChange,
  tone,
  title,
  subject,
  description,
  form,
  serverError,
  submit,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tone: DecisionTone;
  title: string;
  /** What is decided on, under the title, such as the entity's name. */
  subject?: ReactNode;
  description: ReactNode;
  form: AnyFormApi;
  serverError: string | null;
  submit: (confirmClass: string) => ReactNode;
  children: ReactNode;
}) {
  const style = TONES[tone];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] gap-5 overflow-y-auto p-5 sm:max-w-lg">
        <div className="flex items-start gap-3 pr-6">
          <span
            className={cn(
              "flex size-9 shrink-0 items-center justify-center rounded-full [&>svg]:size-5",
              style.badge,
            )}
          >
            {style.icon}
          </span>
          <div className="flex min-w-0 flex-col gap-1">
            <DialogTitle>{title}</DialogTitle>
            {subject && (
              <p className="line-clamp-2 font-medium break-words text-foreground">{subject}</p>
            )}
            <DialogDescription className="leading-relaxed">{description}</DialogDescription>
          </div>
        </div>
        <Form form={form} className="gap-5">
          <FormError message={serverError} />
          {children}
          <DialogFooter className="-mx-5 -mb-5 px-5 py-3.5">
            <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
            {submit(cn("min-w-24", style.confirm))}
          </DialogFooter>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
