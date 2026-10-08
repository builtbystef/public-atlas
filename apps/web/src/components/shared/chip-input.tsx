"use client";

import { XIcon } from "lucide-react";
import { useRef, useState, type KeyboardEvent } from "react";

import { cn } from "@/lib/utils";

/**
 * A list of words or short phrases entered as chips. Enter or a comma ends
 * one, Backspace in the empty input takes the last one back to edit, and
 * pasting "a, b, c" adds three. A chip keeps its inner spaces ("of the") and
 * its punctuation ("d'"), which a comma-separated text field hid. A repeat,
 * compared case-insensitively, is not added.
 */
export function ChipInput({
  id,
  value,
  onChange,
  onBlur,
  placeholder,
  invalid = false,
  "aria-label": ariaLabel,
  "aria-describedby": describedBy,
  chipClassName,
  chipTitle,
}: {
  id?: string | undefined;
  value: readonly string[];
  onChange: (value: string[]) => void;
  onBlur?: (() => void) | undefined;
  placeholder?: string | undefined;
  invalid?: boolean | undefined;
  "aria-label"?: string | undefined;
  "aria-describedby"?: string | undefined;
  /** Extra classes for a chip, to mark some out. */
  chipClassName?: (chip: string) => string | undefined;
  /** A chip's tooltip, saying why it is marked. */
  chipTitle?: (chip: string) => string | undefined;
}) {
  const [draft, setDraft] = useState("");
  const input = useRef<HTMLInputElement>(null);

  /** `value` with each new word added once; returns the new list. */
  const withWords = (current: readonly string[], raw: readonly string[]) => {
    const next = [...current];
    for (const word of raw.map((w) => w.trim()).filter(Boolean)) {
      const key = word.toLocaleLowerCase();
      if (!next.some((chip) => chip.toLocaleLowerCase() === key)) next.push(word);
    }
    return next;
  };

  const commit = (raw: readonly string[]) => {
    const next = withWords(value, raw);
    if (next.length !== value.length) onChange(next);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") {
      // Ctrl/Cmd+Enter still bubbles to the form, which submits it.
      if (!(event.key === "Enter" && (event.metaKey || event.ctrlKey))) event.preventDefault();
      commit([draft]);
      setDraft("");
    } else if (event.key === "Backspace" && draft === "" && value.length > 0) {
      event.preventDefault();
      setDraft(value.at(-1) ?? "");
      onChange(value.slice(0, -1));
    }
  };

  const onType = (text: string) => {
    // A comma that arrives without a keypress: a paste, or an input method.
    if (!text.includes(",")) {
      setDraft(text);
      return;
    }
    const parts = text.split(",");
    const rest = parts.pop() ?? "";
    commit(parts);
    setDraft(rest);
  };

  const remove = (index: number) => {
    onChange(value.filter((_, i) => i !== index));
    input.current?.focus();
  };

  return (
    <div
      data-slot="chip-input"
      className={cn(
        "flex min-h-8 w-full cursor-text flex-wrap items-center gap-1 rounded-lg border border-input bg-transparent px-1 py-1 text-sm transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50 dark:bg-input/30",
        invalid &&
          "border-destructive ring-3 ring-destructive/20 dark:border-destructive/50 dark:ring-destructive/40",
      )}
      onClick={(event) => {
        if (event.target === event.currentTarget) input.current?.focus();
      }}
    >
      {value.map((chip, index) => (
        <span
          key={`${chip}-${index}`}
          title={chipTitle?.(chip)}
          className={cn(
            "inline-flex h-6 max-w-full items-center gap-0.5 rounded-md bg-muted pr-0.5 pl-2 text-xs font-medium whitespace-pre text-foreground",
            chipClassName?.(chip),
          )}
        >
          <span className="truncate">{chip}</span>
          <button
            type="button"
            aria-label={`Remove “${chip}”`}
            onClick={() => remove(index)}
            className="flex size-5 shrink-0 items-center justify-center rounded-sm opacity-60 outline-none hover:bg-foreground/10 hover:opacity-100 focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-ring/50"
          >
            <XIcon className="size-3" aria-hidden="true" />
          </button>
        </span>
      ))}
      <input
        ref={input}
        id={id}
        value={draft}
        onChange={(event) => onType(event.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => {
          commit([draft]);
          setDraft("");
          onBlur?.();
        }}
        placeholder={value.length === 0 ? placeholder : undefined}
        aria-label={ariaLabel}
        aria-describedby={describedBy}
        aria-invalid={invalid}
        autoComplete="off"
        className="h-6 min-w-24 flex-1 bg-transparent px-1.5 outline-none placeholder:text-muted-foreground"
      />
    </div>
  );
}
