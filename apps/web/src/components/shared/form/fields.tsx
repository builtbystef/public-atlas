"use client";

import type { QueryKey } from "@tanstack/react-query";
import type { ComponentProps } from "react";

import { OptionSelect } from "@/components/shared/option-select";
import { ChipInput } from "@/components/shared/chip-input";
import {
  EntityCombobox,
  type EntityComboboxProps,
  type EntityOption,
} from "@/components/shared/entity-combobox";
import { MultiCombobox, type MultiComboboxOption } from "@/components/shared/multi-combobox";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

import { useFieldContext } from "./contexts";

/**
 * Field components bound to the form through `createFormHook`, so a form
 * renders `<form.AppField name="email">{(f) => <f.TextField label="Email" />}</form.AppField>`
 * and the wiring of value, change, blur, and errors lives here once.
 */

interface CommonProps {
  label: string;
  description?: string | undefined;
  /** Marks the label; validation itself is the schema's job. */
  required?: boolean;
}

/** Most fields are optional, so the few that are not carry a mark. */
function RequiredMark() {
  return (
    <span aria-hidden="true" className="text-destructive">
      *
    </span>
  );
}

function useFieldState() {
  const field = useFieldContext<string>();
  const invalid = field.state.meta.isTouched && !field.state.meta.isValid;
  return { field, invalid };
}

export function TextField({
  label,
  description,
  required = false,
  ...inputProps
}: CommonProps &
  Omit<ComponentProps<typeof Input>, "value" | "onChange" | "onBlur" | "id" | "name">) {
  const { field, invalid } = useFieldState();
  return (
    <Field data-invalid={invalid}>
      <FieldLabel htmlFor={field.name}>
        {label}
        {required && <RequiredMark />}
      </FieldLabel>
      <Input
        id={field.name}
        name={field.name}
        value={field.state.value}
        onBlur={field.handleBlur}
        onChange={(event) => field.handleChange(event.target.value)}
        aria-invalid={invalid}
        aria-required={required}
        {...inputProps}
      />
      {description && <FieldDescription>{description}</FieldDescription>}
      {invalid && <FieldError errors={field.state.meta.errors} />}
    </Field>
  );
}

export function TextareaField({
  label,
  description,
  required = false,
  ...textareaProps
}: CommonProps &
  Omit<ComponentProps<typeof Textarea>, "value" | "onChange" | "onBlur" | "id" | "name">) {
  const { field, invalid } = useFieldState();
  return (
    <Field data-invalid={invalid}>
      <FieldLabel htmlFor={field.name}>
        {label}
        {required && <RequiredMark />}
      </FieldLabel>
      <Textarea
        id={field.name}
        name={field.name}
        value={field.state.value}
        onBlur={field.handleBlur}
        onChange={(event) => field.handleChange(event.target.value)}
        aria-invalid={invalid}
        aria-required={required}
        {...textareaProps}
      />
      {description && <FieldDescription>{description}</FieldDescription>}
      {invalid && <FieldError errors={field.state.meta.errors} />}
    </Field>
  );
}

/** A list of words entered as chips; the value is the list. */
export function ChipsField({
  label,
  description,
  required = false,
  placeholder,
}: CommonProps & { placeholder?: string }) {
  const field = useFieldContext<string[]>();
  const invalid = field.state.meta.isTouched && !field.state.meta.isValid;
  return (
    <Field data-invalid={invalid}>
      <FieldLabel htmlFor={field.name}>
        {label}
        {required && <RequiredMark />}
      </FieldLabel>
      <ChipInput
        id={field.name}
        value={field.state.value}
        onChange={field.handleChange}
        onBlur={field.handleBlur}
        placeholder={placeholder}
        invalid={invalid}
      />
      {description && <FieldDescription>{description}</FieldDescription>}
      {invalid && <FieldError errors={field.state.meta.errors} />}
    </Field>
  );
}

export interface SelectOption {
  value: string;
  label: string;
}

/** Several options picked from a searchable list, shown as chips; the value is the list. */
export function MultiSelectField({
  label,
  description,
  required = false,
  options,
  placeholder,
}: CommonProps & {
  options: readonly MultiComboboxOption[];
  placeholder?: string | undefined;
}) {
  const field = useFieldContext<string[]>();
  const invalid = field.state.meta.isTouched && !field.state.meta.isValid;
  return (
    <Field data-invalid={invalid}>
      <FieldLabel htmlFor={field.name}>
        {label}
        {required && <RequiredMark />}
      </FieldLabel>
      <MultiCombobox
        id={field.name}
        options={options}
        value={field.state.value}
        onValueChange={field.handleChange}
        onBlur={field.handleBlur}
        placeholder={placeholder}
        invalid={invalid}
      />
      {description && <FieldDescription>{description}</FieldDescription>}
      {invalid && <FieldError errors={field.state.meta.errors} />}
    </Field>
  );
}

export function SelectField({
  label,
  description,
  required = false,
  options,
  placeholder,
  disabled,
}: CommonProps & {
  options: readonly SelectOption[];
  /** Adds an empty option with this label, which the schema turns into null. */
  placeholder?: string | undefined;
  disabled?: boolean | undefined;
}) {
  const { field, invalid } = useFieldState();
  return (
    <Field data-invalid={invalid}>
      <FieldLabel htmlFor={field.name}>
        {label}
        {required && <RequiredMark />}
      </FieldLabel>
      <OptionSelect
        id={field.name}
        name={field.name}
        value={field.state.value}
        onBlur={field.handleBlur}
        onValueChange={field.handleChange}
        aria-invalid={invalid}
        aria-required={required}
        disabled={disabled}
        className="w-full"
        options={[
          ...(placeholder !== undefined ? [{ value: "", label: placeholder }] : []),
          ...options,
        ]}
      />
      {description && <FieldDescription>{description}</FieldDescription>}
      {invalid && <FieldError errors={field.state.meta.errors} />}
    </Field>
  );
}

/** A contact or company chosen by name; the value is its id, "" for none. */
export function ComboboxField<
  P extends { items: readonly EntityOption[]; total: number },
  R extends EntityOption,
  PK extends QueryKey,
  RK extends QueryKey,
>({
  label,
  description,
  required = false,
  ...pickerProps
}: CommonProps &
  Omit<
    EntityComboboxProps<P, R, PK, RK>,
    "id" | "name" | "value" | "onValueChange" | "onBlur" | "invalid"
  >) {
  const { field, invalid } = useFieldState();
  return (
    <Field data-invalid={invalid}>
      <FieldLabel htmlFor={field.name}>
        {label}
        {required && <RequiredMark />}
      </FieldLabel>
      <EntityCombobox
        id={field.name}
        name={field.name}
        value={field.state.value}
        onValueChange={field.handleChange}
        onBlur={field.handleBlur}
        invalid={invalid}
        {...pickerProps}
      />
      {description && <FieldDescription>{description}</FieldDescription>}
      {invalid && <FieldError errors={field.state.meta.errors} />}
    </Field>
  );
}

export function DateTimeField({ label, description, required = false }: CommonProps) {
  const { field, invalid } = useFieldState();
  return (
    <Field data-invalid={invalid}>
      <FieldLabel htmlFor={field.name}>
        {label}
        {required && <RequiredMark />}
      </FieldLabel>
      <Input
        id={field.name}
        name={field.name}
        type="datetime-local"
        value={field.state.value}
        onBlur={field.handleBlur}
        onChange={(event) => field.handleChange(event.target.value)}
        aria-invalid={invalid}
        aria-required={required}
      />
      {description && <FieldDescription>{description}</FieldDescription>}
      {invalid && <FieldError errors={field.state.meta.errors} />}
    </Field>
  );
}
