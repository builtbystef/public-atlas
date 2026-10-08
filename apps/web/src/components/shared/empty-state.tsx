import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * What a list shows when there is nothing in it: a line of muted text, or
 * with `boxed` a dashed panel that holds the section's place on the page.
 */
export function EmptyState({ boxed = false, children }: { boxed?: boolean; children: ReactNode }) {
  return (
    <p
      className={cn(
        "text-sm text-muted-foreground",
        boxed && "rounded-lg border border-dashed px-4 py-8 text-center",
      )}
    >
      {children}
    </p>
  );
}
