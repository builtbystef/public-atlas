"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { cn } from "@/lib/utils";

export interface CheckboxOption {
  value: string;
  label: string;
  description?: string | undefined;
}

/**
 * A set of checkboxes whose value is the list of checked options, in the
 * options' order. Used for the array fields of a form (a run's filter, a
 * level's expected types) through `<form.Field>`.
 */
export function CheckboxGroup({
  name,
  label,
  description,
  options,
  value,
  onChange,
  errors,
  emptyMessage = "Nothing to choose from.",
  columns = 2,
}: {
  name: string;
  label: string;
  description?: string;
  options: readonly CheckboxOption[];
  value: readonly string[];
  onChange: (value: string[]) => void;
  errors?: readonly unknown[];
  emptyMessage?: string;
  columns?: 1 | 2 | 3;
}) {
  const toggle = (option: string, checked: boolean) => {
    const next = options
      .map((o) => o.value)
      .filter((v) => (v === option ? checked : value.includes(v)));
    onChange(next);
  };
  const invalid = errors !== undefined && errors.length > 0;
  return (
    <Field data-invalid={invalid}>
      <FieldLabel>{label}</FieldLabel>
      {description && <FieldDescription>{description}</FieldDescription>}
      {options.length === 0 ? (
        <p className="text-sm text-muted-foreground">{emptyMessage}</p>
      ) : (
        <div
          className={cn(
            "grid gap-x-6 gap-y-2",
            columns === 2 && "sm:grid-cols-2",
            columns === 3 && "sm:grid-cols-3",
          )}
        >
          {options.map((option) => {
            const id = `${name}-${option.value}`;
            return (
              <label key={option.value} htmlFor={id} className="flex items-start gap-2 text-sm">
                <Checkbox
                  id={id}
                  name={name}
                  value={option.value}
                  checked={value.includes(option.value)}
                  onCheckedChange={(checked) => toggle(option.value, checked === true)}
                  className="mt-0.5"
                />
                <span className="flex flex-col">
                  <span>{option.label}</span>
                  {option.description && (
                    <span className="text-xs text-muted-foreground">{option.description}</span>
                  )}
                </span>
              </label>
            );
          })}
        </div>
      )}
      {invalid && <FieldError errors={errors as { message?: string }[]} />}
    </Field>
  );
}
