import { ArrowDownIcon, ArrowUpIcon, CircleAlertIcon } from "lucide-react";

import { formatPercent } from "@/lib/formatting/money";
import { cn } from "@/lib/utils";

/**
 * A recall or precision as a percentage. Given a floor (the gate on a
 * recall's type) it is green at or above it and red, with a mark, below;
 * without one it is plain. A dash, saying why, when not judged.
 */
export function ScoreCell({
  value,
  floor,
  missing = "Not judged",
  className,
}: {
  value: number | null | undefined;
  floor?: number | undefined;
  /** Why there is no value: the dash's tooltip. */
  missing?: string;
  className?: string;
}) {
  if (value === null || value === undefined) {
    return (
      <span className={cn("text-muted-foreground", className)} title={missing}>
        –<span className="sr-only">{missing}</span>
      </span>
    );
  }
  const below = floor !== undefined && value < floor;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 tabular-nums",
        floor !== undefined && (below ? "text-destructive" : "text-success"),
        className,
      )}
      title={floor !== undefined ? `Target ${formatPercent(floor)}` : undefined}
    >
      {below && <CircleAlertIcon className="size-[0.8em] shrink-0" aria-hidden="true" />}
      {formatPercent(value)}
      {below && <span className="sr-only">, below the {formatPercent(floor)} target</span>}
    </span>
  );
}

/**
 * How far a score moved since the run compared against, in percentage
 * points: green up, red down. Nothing when either side is missing, and
 * nothing for no change unless `showZero`.
 */
export function ScoreChange({
  value,
  showZero = false,
  className,
}: {
  value: number | null;
  showZero?: boolean;
  className?: string;
}) {
  if (value === null) return null;
  const points = Math.round(value * 100);
  if (points === 0) {
    return showZero ? (
      <span className={cn("text-xs text-muted-foreground tabular-nums", className)}>±0</span>
    ) : null;
  }
  const Arrow = points > 0 ? ArrowUpIcon : ArrowDownIcon;
  return (
    <span
      className={cn(
        "inline-flex items-center text-xs tabular-nums",
        points > 0 ? "text-success" : "text-destructive",
        className,
      )}
      title="Since the run compared against"
    >
      <Arrow className="size-3" aria-hidden="true" />
      {Math.abs(points)}
      <span className="sr-only">
        {points > 0 ? " points up" : " points down"} since the run compared against
      </span>
    </span>
  );
}
