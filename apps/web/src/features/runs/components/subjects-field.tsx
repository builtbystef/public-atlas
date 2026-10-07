"use client";

import { XIcon } from "lucide-react";
import { useState } from "react";

import { EntityCombobox, type EntityOption } from "@/components/shared/entity-combobox";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { subjectOptionQuery, subjectPickerQuery } from "@/features/graph/queries";
import { browserApi } from "@/lib/api/client";

/**
 * The places and institutions a run is limited to. Each pick from the search
 * adds a chip; the value is their ids.
 */
export function SubjectsField({
  countryCode,
  value,
  onChange,
}: {
  countryCode: string;
  value: readonly string[];
  onChange: (ids: string[]) => void;
}) {
  const [chosen, setChosen] = useState<EntityOption[]>([]);
  const add = (id: string, option?: EntityOption) => {
    if (id === "" || value.includes(id)) return;
    setChosen((list) => [...list, option ?? { id, name: id }]);
    onChange([...value, id]);
  };
  const remove = (id: string) => {
    setChosen((list) => list.filter((option) => option.id !== id));
    onChange(value.filter((other) => other !== id));
  };
  return (
    <Field>
      <FieldLabel htmlFor="subjects">Subjects</FieldLabel>
      <SubjectPicker key={value.length} countryCode={countryCode} onPick={add} />
      <FieldDescription>
        Leave empty for every place and institution the levels and types allow.
      </FieldDescription>
      {chosen.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {chosen.map((option) => (
            <li
              key={option.id}
              className="inline-flex items-center gap-1 rounded-md border bg-muted/40 py-0.5 pr-0.5 pl-2 text-sm"
            >
              <span>{option.name}</span>
              {option.detail && (
                <span className="text-xs text-muted-foreground">{option.detail}</span>
              )}
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                aria-label={`Remove ${option.name}`}
                onClick={() => remove(option.id)}
              >
                <XIcon />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Field>
  );
}

/** Remounted after each pick (by key), so the input clears for the next one. */
function SubjectPicker({
  countryCode,
  onPick,
}: {
  countryCode: string;
  onPick: (id: string, option?: EntityOption) => void;
}) {
  const [value, setValue] = useState("");
  return (
    <EntityCombobox
      id="subjects"
      name="subjects"
      value={value}
      onValueChange={(id) => {
        setValue(id);
        if (id) onPick(id);
      }}
      placeholder={countryCode ? "Search places and institutions" : "Choose a country first"}
      disabled={!countryCode}
      search={(q) => subjectPickerQuery(browserApi, q, countryCode || undefined)}
      resolve={(id) => subjectOptionQuery(browserApi, id)}
    />
  );
}
