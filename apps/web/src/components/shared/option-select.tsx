"use client";

import type { ComponentProps, ReactNode } from "react";

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export interface SelectChoice<V extends string = string> {
  value: V;
  label: ReactNode;
  disabled?: boolean | undefined;
}

/**
 * A select over a flat list of choices, the trigger showing the chosen one's
 * label. A choice valued "" is the unset state, an "Any status" say: the
 * trigger shows its label muted, as a placeholder.
 */
export function OptionSelect<V extends string>({
  value,
  onValueChange,
  options,
  prefix,
  name,
  disabled,
  ...trigger
}: {
  value: V;
  onValueChange: (value: V) => void;
  options: readonly SelectChoice<V>[];
  /** A muted word before the value, naming what it is: "Colour", say. */
  prefix?: ReactNode;
  name?: string | undefined;
  disabled?: boolean | undefined;
} & Omit<ComponentProps<typeof SelectTrigger>, "value" | "children" | "disabled">) {
  return (
    <Select
      value={value}
      onValueChange={(next) => onValueChange(next as V)}
      items={options}
      name={name}
      disabled={disabled}
    >
      <SelectTrigger {...trigger}>
        {prefix !== undefined && <span className="text-muted-foreground">{prefix}</span>}
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {/* The group gives the list its inner padding, as in the shadcn examples. */}
        <SelectGroup>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value} disabled={option.disabled}>
              {option.label}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}
