import { XIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * The controls above a table. With a search, the search, the count and the
 * actions share the first row and the filters get a row of their own, so a
 * long set of filters never wraps around the count. Without one, the filters
 * and the count share a single row. `onClear` adds a button that resets the
 * filters, shown while any is set.
 */
export function TableToolbar({
  search,
  filters,
  count,
  actions,
  onClear,
}: {
  search?: ReactNode;
  filters?: ReactNode;
  count: ReactNode;
  actions?: ReactNode;
  /** Undefined while no filter is set. */
  onClear?: (() => void) | undefined;
}) {
  const end = (
    <div className="ml-auto flex shrink-0 items-center gap-3">
      <span className="text-sm text-muted-foreground tabular-nums">{count}</span>
      {actions}
    </div>
  );
  const filterRow = (filters || onClear) && (
    <div className="flex flex-wrap items-center gap-2">
      {/* With a search, the selects stretch to the table's width; otherwise they keep theirs. */}
      {filters && (
        <div
          className={cn(
            "flex flex-wrap items-center gap-2",
            search && "flex-1 *:min-w-36 *:not-data-[slot=input-group]:flex-auto",
          )}
        >
          {filters}
        </div>
      )}
      {onClear && (
        <Button variant="ghost" onClick={onClear} className="text-muted-foreground">
          <XIcon /> Clear
        </Button>
      )}
      {!search && end}
    </div>
  );
  if (!search) return filterRow || <div className="flex">{end}</div>;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="max-w-sm min-w-48 flex-1">{search}</div>
        {end}
      </div>
      {filterRow}
    </div>
  );
}
