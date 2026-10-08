"use client";

import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { cn } from "@/lib/utils";

/**
 * A population range as two inputs, each a whole number or empty for no
 * bound. The values are the inputs' text; parsing is the list schema's job.
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
    <div className={cn("flex items-center gap-1.5", className)}>
      <InputGroup className="w-36">
        <InputGroupAddon className="text-xs">Pop. ≥</InputGroupAddon>
        <InputGroupInput
          id={`${idPrefix}-min`}
          type="number"
          inputMode="numeric"
          min={0}
          step={1}
          value={min}
          onChange={(event) => onMinChange(event.target.value)}
          placeholder="Any"
          aria-label="Smallest population"
        />
      </InputGroup>
      <InputGroup className="w-36">
        <InputGroupAddon className="text-xs">Pop. ≤</InputGroupAddon>
        <InputGroupInput
          id={`${idPrefix}-max`}
          type="number"
          inputMode="numeric"
          min={0}
          step={1}
          value={max}
          onChange={(event) => onMaxChange(event.target.value)}
          placeholder="Any"
          aria-label="Largest population"
        />
      </InputGroup>
    </div>
  );
}

/** A bound's text as the URL and the API take it: undefined unless a whole number. */
export function populationBound(text: string): number | undefined {
  const trimmed = text.trim();
  if (!/^\d+$/.test(trimmed)) return undefined;
  return Number(trimmed);
}
