import type { ReactNode } from "react";

/** A card's content when there is nothing to list. */
export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}
