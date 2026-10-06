"use client";

import {
  keepPreviousData,
  useQuery,
  type QueryKey,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { useState } from "react";

import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "@/components/ui/combobox";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

/** What a picker needs of a contact or company. */
export interface EntityOption {
  id: string;
  name: string;
  /** Shown after the name in the list, muted: the kind of thing it is, say. */
  detail?: string;
}

interface EntityPage {
  items: readonly EntityOption[];
  total: number;
}

/**
 * Generic over the queries' exact types (a contact page, a company record)
 * so the `queryOptions()` a form passes in fit without widening.
 */
export interface EntityComboboxProps<
  P extends EntityPage,
  R extends EntityOption,
  PK extends QueryKey,
  RK extends QueryKey,
> {
  id: string;
  name: string;
  /** The chosen id, or "" for none. */
  value: string;
  onValueChange: (id: string) => void;
  onBlur?: () => void;
  invalid?: boolean;
  disabled?: boolean;
  placeholder: string;
  /**
   * The option behind `value`, when the caller already has it (an edit form
   * holds the whole record). Otherwise `resolve` fetches it, so the input
   * can show a name rather than an id.
   */
  selected?: EntityOption | null | undefined;
  /** The matches for what was typed. Called with "" for the opening list. */
  search: (q: string) => UseQueryOptions<P, Error, P, PK>;
  resolve: (id: string) => UseQueryOptions<R, Error, R, RK>;
}

const DEBOUNCE_MS = 250;

/**
 * A searchable picker over an API list. The API does the matching, so the
 * list is right however many rows the workspace has: each keystroke (after a
 * pause) fetches the first matches, and the popup says when there were more.
 */
export function EntityCombobox<
  P extends EntityPage,
  R extends EntityOption,
  PK extends QueryKey,
  RK extends QueryKey,
>({
  id,
  name,
  value,
  onValueChange,
  onBlur,
  invalid,
  disabled,
  placeholder,
  selected,
  search,
  resolve,
}: EntityComboboxProps<P, R, PK, RK>) {
  const [input, setInput] = useState("");
  const q = useDebouncedValue(input.trim(), DEBOUNCE_MS);
  const matches = useQuery({ ...search(q), placeholderData: keepPreviousData });
  const items: readonly EntityOption[] = matches.data?.items ?? [];

  // The chosen option: from the caller, the matches, or a fetch of its own.
  const known =
    (selected?.id === value ? selected : undefined) ?? items.find((item) => item.id === value);
  const resolved = useQuery({ ...resolve(value), enabled: value !== "" && known === undefined });
  const current: EntityOption | null =
    value === "" ? null : (known ?? resolved.data ?? { id: value, name: "" });

  const hidden = matches.data ? matches.data.total - items.length : 0;

  return (
    <Combobox<EntityOption>
      id={id}
      name={name}
      items={items}
      value={current}
      onValueChange={(item) => onValueChange(item?.id ?? "")}
      onInputValueChange={setInput}
      // The API already matched; showing everything it returned is the point.
      filter={null}
      itemToStringLabel={(item) => item.name}
      itemToStringValue={(item) => item.id}
      isItemEqualToValue={(item, other) => item.id === other.id}
      disabled={disabled}
    >
      <ComboboxInput
        placeholder={placeholder}
        onBlur={onBlur}
        aria-invalid={invalid}
        disabled={disabled}
        showClear
        className="w-full"
      />
      <ComboboxContent>
        <ComboboxEmpty>{matches.isPending ? "Loading…" : "No matches."}</ComboboxEmpty>
        <ComboboxList>
          {(item: EntityOption) => (
            <ComboboxItem key={item.id} value={item}>
              <span className="truncate">{item.name}</span>
              {item.detail && (
                <span className="ml-auto truncate text-xs text-muted-foreground">
                  {item.detail}
                </span>
              )}
            </ComboboxItem>
          )}
        </ComboboxList>
        {hidden > 0 && (
          <p className="border-t px-2 py-1.5 text-xs text-muted-foreground">
            {hidden} more. Keep typing to narrow it down.
          </p>
        )}
      </ComboboxContent>
    </Combobox>
  );
}
