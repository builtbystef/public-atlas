import "server-only";

import { hasFlag } from "country-flag-icons";
import * as flags from "country-flag-icons/react/3x2";
import { GlobeIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type FlagComponent = (typeof flags)["CA"];

/**
 * A country's flag, 3:2, or a globe for a code with no flag. Server-only:
 * the module holds every flag (about 330 KB), so a client component takes
 * the rendered flag as a prop rather than importing this. Decorative, since
 * the country's name is always beside it.
 */
export function CountryFlag({ code, className }: { code: string; className?: string }) {
  const Flag = hasFlag(code)
    ? (flags as unknown as Record<string, FlagComponent | undefined>)[code]
    : undefined;
  const frame = cn(
    "h-6 w-9 shrink-0 overflow-hidden rounded-[3px] ring-1 ring-foreground/10",
    className,
  );
  if (Flag === undefined) {
    return (
      <span aria-hidden="true" className={cn(frame, "flex items-center justify-center bg-muted")}>
        <GlobeIcon className="size-3.5 text-muted-foreground" />
      </span>
    );
  }
  return <Flag aria-hidden="true" className={cn(frame, "block")} />;
}
