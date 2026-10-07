import { formatPercent } from "@/lib/formatting/money";
import { cn } from "@/lib/utils";

/** A recall or precision as a percentage, tinted by how good it is; a dash when not scored. */
export function ScoreCell({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) {
    return <span className="text-muted-foreground">–</span>;
  }
  return (
    <span
      className={cn(
        "tabular-nums",
        value >= 0.9 ? "text-foreground" : value >= 0.7 ? "text-amber-600" : "text-destructive",
      )}
    >
      {formatPercent(value)}
    </span>
  );
}
