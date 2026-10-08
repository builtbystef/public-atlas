import type { AssignmentRefOutput, ReviewItemDetail } from "@public-atlas/api-client";
import Link from "next/link";
import type { ReactNode } from "react";

import { AssignmentStatusBadge, ReviewStatusBadge } from "@/components/shared/status-badge";
import { formatDateTime } from "@/lib/formatting/dates";
import { assignmentTypeLabels } from "@/lib/labels";
import { paths } from "@/lib/routes";
import { cn } from "@/lib/utils";

/** "Find homepage for Oakville Library", linked to the assignment. */
function AssignmentName({ assignment }: { assignment: AssignmentRefOutput }) {
  return (
    <Link href={paths.assignment(assignment.id)} className="font-medium hover:underline">
      {assignmentTypeLabels[assignment.type]} for {assignment.subject.label}
    </Link>
  );
}

function Step({
  done = true,
  title,
  at,
  children,
}: {
  done?: boolean;
  title: ReactNode;
  at?: string | null | undefined;
  children?: ReactNode;
}) {
  return (
    <li className="group relative flex flex-col gap-1 pb-5 pl-6 last:pb-0">
      {/* The line to the next step, and the step's dot on it. */}
      <span className="absolute top-2 bottom-0 left-[5px] w-px bg-border group-last:hidden" />
      <span
        className={cn(
          "absolute top-1.5 left-0 size-[11px] rounded-full border-2",
          done ? "border-primary bg-primary" : "border-muted-foreground/50 bg-background",
        )}
      />
      <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">{title}</span>
      {at && <span className="text-xs text-muted-foreground">{at}</span>}
      {children}
    </li>
  );
}

/**
 * What happened to the item, in order: who raised it, the decision and its
 * note, and the assignments started on the entity or its institution since.
 */
export function ReviewHistory({ item, timeZone }: { item: ReviewItemDetail; timeZone: string }) {
  const raiser = item.raised_by;
  return (
    <ol className="flex flex-col">
      <Step
        title={
          raiser ? (
            <>
              Raised by <AssignmentName assignment={raiser} />
              <AssignmentStatusBadge status={raiser.status} />
            </>
          ) : (
            "Raised"
          )
        }
        at={formatDateTime(item.raised_at, timeZone)}
      />
      {item.status === "open" ? (
        <Step
          done={false}
          title={<span className="text-muted-foreground">Waiting for a decision</span>}
        />
      ) : (
        <Step
          title={
            <>
              Decided <ReviewStatusBadge status={item.status} />
            </>
          }
          at={formatDateTime(item.decided_at, timeZone)}
        >
          {item.note && (
            <p className="mt-1 rounded-md bg-muted px-3 py-2 text-sm whitespace-pre-wrap">
              {item.note}
            </p>
          )}
        </Step>
      )}
      {item.started_since.map((assignment) => (
        <Step
          key={assignment.id}
          title={
            <>
              Started <AssignmentName assignment={assignment} />
              <AssignmentStatusBadge status={assignment.status} />
            </>
          }
          at={formatDateTime(assignment.created_at, timeZone)}
        />
      ))}
    </ol>
  );
}
