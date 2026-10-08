import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface RadioCardOption<V extends string> {
  value: V;
  label: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
}

/**
 * A small set of exclusive choices, each a card with its name and what it
 * means, for settings where a plain select would hide the explanation.
 */
export function RadioCards<V extends string>({
  name,
  legend,
  value,
  options,
  onChange,
  className,
}: {
  name: string;
  legend: string;
  value: V;
  options: RadioCardOption<V>[];
  onChange: (value: V) => void;
  className?: string;
}) {
  return (
    <fieldset className={cn("flex flex-col gap-3", className)}>
      <legend className="sr-only">{legend}</legend>
      {options.map((option) => (
        <label
          key={option.value}
          className="flex cursor-pointer items-start gap-3 rounded-lg border bg-card p-4 shadow-xs transition-colors hover:border-primary/40 has-checked:border-primary has-checked:bg-primary/5 has-focus-visible:ring-3 has-focus-visible:ring-ring/50"
        >
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
            className="mt-0.5 size-4 shrink-0 accent-primary"
          />
          {option.icon && (
            <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center text-muted-foreground [&_svg]:size-4">
              {option.icon}
            </span>
          )}
          <span className="flex flex-col gap-1">
            <span className="text-sm font-medium">{option.label}</span>
            {option.description && (
              <span className="text-sm text-muted-foreground">{option.description}</span>
            )}
          </span>
        </label>
      ))}
    </fieldset>
  );
}
