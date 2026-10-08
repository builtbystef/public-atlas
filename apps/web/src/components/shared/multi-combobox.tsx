"use client";

import {
  Combobox,
  ComboboxChip,
  ComboboxChips,
  ComboboxChipsInput,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxItem,
  ComboboxList,
  ComboboxValue,
  useComboboxAnchor,
} from "@/components/ui/combobox";

export interface MultiComboboxOption {
  value: string;
  label: string;
  /** Shown under the label in the list, to tell options apart. */
  description?: string | undefined;
}

/**
 * Several options picked from a searchable list, each shown as a chip: the
 * shadcn combobox in its multiple-selection form. The value is the options'
 * `value`s, in the order they were picked.
 */
export function MultiCombobox({
  id,
  options,
  value,
  onValueChange,
  onBlur,
  placeholder,
  invalid = false,
  "aria-describedby": describedBy,
}: {
  id?: string | undefined;
  options: readonly MultiComboboxOption[];
  value: readonly string[];
  onValueChange: (value: string[]) => void;
  onBlur?: (() => void) | undefined;
  placeholder?: string | undefined;
  invalid?: boolean | undefined;
  "aria-describedby"?: string | undefined;
}) {
  const anchor = useComboboxAnchor();
  const byValue = new Map(options.map((option) => [option.value, option]));
  const labelOf = (key: string) => byValue.get(key)?.label ?? key;
  return (
    <Combobox<string, true>
      multiple
      autoHighlight
      items={options.map((option) => option.value)}
      value={[...value]}
      onValueChange={onValueChange}
      itemToStringLabel={labelOf}
    >
      <ComboboxChips ref={anchor} className="min-h-9 py-1">
        <ComboboxValue>
          {value.map((key) => (
            <ComboboxChip key={key}>{labelOf(key)}</ComboboxChip>
          ))}
        </ComboboxValue>
        <ComboboxChipsInput
          id={id}
          onBlur={onBlur}
          placeholder={value.length === 0 ? placeholder : "Add more…"}
          aria-invalid={invalid}
          aria-describedby={describedBy}
          className="h-6 px-1"
        />
      </ComboboxChips>
      <ComboboxContent anchor={anchor}>
        <ComboboxEmpty>Nothing matches.</ComboboxEmpty>
        <ComboboxList>
          {(key: string) => {
            const option = byValue.get(key);
            return (
              <ComboboxItem key={key} value={key} className="items-start py-1.5">
                <span className="flex min-w-0 flex-col">
                  <span>{labelOf(key)}</span>
                  {option?.description && (
                    <span className="line-clamp-2 text-xs text-muted-foreground">
                      {option.description}
                    </span>
                  )}
                </span>
              </ComboboxItem>
            );
          }}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}
