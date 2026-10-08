"use client";

import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { cn } from "@/lib/utils";

// Number inputs without the browser's spinners, which crowd a narrow box.
const boundClassName =
  "w-0 min-w-0 px-1.5 text-center tabular-nums [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none";

/**
 * A population range as one control with two bounds, each a whole number or
 * empty for no bound. The values are the inputs' text; parsing is the list
 * schema's job.
 */
export function PopulationRange({
  min,
  max,
  onMinChange,
  onMaxChange,
  idPrefix = "population",
  className,
}: {
  min: string;
  max: string;
  onMinChange: (value: string) => void;
  onMaxChange: (value: string) => void;
  idPrefix?: string;
  className?: string;
}) {
  return (
    <InputGroup className={cn("w-60", className)}>
      <InputGroupAddon>Population</InputGroupAddon>
      <InputGroupInput
        id={`${idPrefix}-min`}
        type="number"
        inputMode="numeric"
        min={0}
        step={1}
        value={min}
        onChange={(event) => onMinChange(event.target.value)}
        placeholder="Min"
        aria-label="Smallest population"
        className={boundClassName}
      />
      <span aria-hidden="true" className="text-sm text-muted-foreground">
        –
      </span>
      <InputGroupInput
        id={`${idPrefix}-max`}
        type="number"
        inputMode="numeric"
        min={0}
        step={1}
        value={max}
        onChange={(event) => onMaxChange(event.target.value)}
        placeholder="Max"
        aria-label="Largest population"
        className={boundClassName}
      />
    </InputGroup>
  );
}

/** A bound's text as the URL and the API take it: undefined unless a whole number. */
export function populationBound(text: string): number | undefined {
  const trimmed = text.trim();
  if (!/^\d+$/.test(trimmed)) return undefined;
  return Number(trimmed);
}
