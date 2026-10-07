import type { Progress } from "@public-atlas/api-client";

import {
  assignmentResultLabels,
  assignmentResults,
  assignmentStatusLabels,
  assignmentStatuses,
} from "@/lib/labels";
import { cn } from "@/lib/utils";

const STATUS_COLOR = {
  held: "bg-muted-foreground/30",
  queued: "bg-chart-1",
  running: "bg-chart-3",
  finished: "bg-primary",
  cancelled: "bg-destructive/60",
} as const;

export function totalAssignments(progress: Progress): number {
  return Object.values(progress.by_status).reduce((sum, count) => sum + count, 0);
}

/** One bar across the run's assignments, a segment per status, with the counts under it. */
export function RunProgressBar({
  progress,
  className,
}: {
  progress: Progress;
  className?: string;
}) {
  const total = totalAssignments(progress);
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted">
        {total > 0 &&
          assignmentStatuses.map((status) => {
            const count = progress.by_status[status] ?? 0;
            if (count === 0) return null;
            return (
              <div
                key={status}
                className={STATUS_COLOR[status]}
                style={{ width: `${(count / total) * 100}%` }}
                title={`${assignmentStatusLabels[status]}: ${count}`}
              />
            );
          })}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
        {total === 0 ? (
          <span>No assignments</span>
        ) : (
          assignmentStatuses.map((status) => {
            const count = progress.by_status[status] ?? 0;
            if (count === 0) return null;
            return (
              <span key={status} className="inline-flex items-center gap-1 tabular-nums">
                <span className={cn("size-2 rounded-full", STATUS_COLOR[status])} />
                {count} {assignmentStatusLabels[status].toLowerCase()}
              </span>
            );
          })
        )}
      </div>
    </div>
  );
}

/** The finished assignments by how they ended. */
export function RunResults({ progress }: { progress: Progress }) {
  const rows = assignmentResults
    .map((result) => [result, progress.by_result[result] ?? 0] as const)
    .filter(([, count]) => count > 0);
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">Nothing has finished yet.</p>;
  }
  return (
    <dl className="grid grid-cols-[1fr_auto] gap-x-6 gap-y-1 text-sm">
      {rows.map(([result, count]) => (
        <div key={result} className="contents">
          <dt className="text-muted-foreground">{assignmentResultLabels[result]}</dt>
          <dd className="text-right tabular-nums">{count}</dd>
        </div>
      ))}
    </dl>
  );
}
