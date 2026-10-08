import { formatCount } from "@/lib/formatting/money";

/** A place's population as digits that line up; a dash when there is no figure. */
export function Population({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) {
    return <span className="text-muted-foreground">–</span>;
  }
  return <span className="tabular-nums">{formatCount(value)}</span>;
}
