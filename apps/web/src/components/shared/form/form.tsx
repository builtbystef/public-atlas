"use client";

import { useStore, type AnyFormApi } from "@tanstack/react-form";
import { cn } from "cn";
import {
  useEffect,
  useId,
  useRef,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import { FieldGroup } from "@/components/ui/field";

/**
 * The <form> element for a `useAppForm` form. It submits through the form
 * API, moves focus to the first invalid control when a submit is rejected,
 * and submits on Ctrl/Cmd+Enter so a textarea does not trap the keyboard.
 * With `warnOnLeave`, the browser asks before unloading unsaved changes.
 */
export function Form({
  form,
  warnOnLeave = false,
  className,
  children,
  ...props
}: Omit<React.ComponentProps<"form">, "onSubmit"> & {
  form: AnyFormApi;
  warnOnLeave?: boolean;
  children: ReactNode;
}) {
  const ref = useRef<HTMLFormElement>(null);
  const unsaved = useStore(form.store, (state) => !state.isDefaultValue && !state.isSubmitting);

  useEffect(() => {
    if (!warnOnLeave || !unsaved) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [warnOnLeave, unsaved]);

  const submit = async () => {
    await form.handleSubmit();
    if (form.state.isValid) return;
    // Errors render on the next paint; wait for it before looking them up.
    requestAnimationFrame(() => {
      ref.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
    });
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void submit();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLFormElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      void submit();
    }
  };

  return (
    <form
      ref={ref}
      noValidate
      className={cn("flex flex-col gap-6", className)}
      onSubmit={onSubmit}
      onKeyDown={onKeyDown}
      {...props}
    >
      {children}
    </form>
  );
}

/** The row of buttons that ends a form: cancel on the left of the primary action. */
export function FormActions({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="form-actions"
      className={cn("flex flex-wrap items-center justify-end gap-2", className)}
      {...props}
    />
  );
}

/** The sections of a page form, one after another with a rule between them. */
export function FormSections({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="form-sections"
      className={cn("flex flex-col divide-y *:py-8 *:first:pt-0 *:last:pb-0", className)}
      {...props}
    />
  );
}

/** A titled group of fields inside <FormSections>. */
export function FormSection({
  title,
  description,
  children,
}: {
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h3 id={id} className="text-base leading-none font-medium">
          {title}
        </h3>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      <FieldGroup>{children}</FieldGroup>
    </section>
  );
}
