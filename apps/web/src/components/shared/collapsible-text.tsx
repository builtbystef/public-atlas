"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const DEFAULT_LIMIT = 600;

/** Long text (a prompt, a page's text) shown cut at `limit` characters until opened. */
export function CollapsibleText({
  text,
  limit = DEFAULT_LIMIT,
  className,
}: {
  text: string;
  limit?: number;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const long = text.length > limit;
  return (
    <div className="flex flex-col items-start gap-1">
      <p className={cn("text-sm break-words whitespace-pre-wrap", className)}>
        {open || !long ? text : `${text.slice(0, limit)}…`}
      </p>
      {long && (
        <Button variant="link" size="xs" className="px-0" onClick={() => setOpen(!open)}>
          {open ? "Show less" : `Show all (${text.length.toLocaleString("en-US")} characters)`}
        </Button>
      )}
    </div>
  );
}
