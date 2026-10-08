import type {
  AssignmentResult,
  AssignmentStatus,
  EntityStatus,
  ReviewStatus,
  RunStatus,
} from "@public-atlas/api-client";
import type { ComponentProps } from "react";

import { Badge } from "@/components/ui/badge";
import {
  assignmentResultLabels,
  assignmentStatusLabels,
  entityStatusLabels,
  reviewStatusLabels,
  runStatusLabels,
} from "@/lib/labels";
import { cn } from "@/lib/utils";

type Variant = NonNullable<ComponentProps<typeof Badge>["variant"]>;

/**
 * One badge per status enum, each with a fixed colour per value so a status
 * reads the same on every page. The colours follow the palette's semantics:
 * success for what is settled or went well, warning (the ochre accent) for
 * what waits on someone, info for what is in motion, plum for what was
 * merged, destructive for what went wrong, and neutral for the rest.
 */
export function EntityStatusBadge({ status }: { status: EntityStatus }) {
  const variant: Record<EntityStatus, Variant> = {
    verified: "success",
    candidate: "secondary",
    needs_review: "warning",
    rejected: "destructive",
  };
  return <Badge variant={variant[status]}>{entityStatusLabels[status]}</Badge>;
}

export function AssignmentStatusBadge({ status }: { status: AssignmentStatus }) {
  const variant: Record<AssignmentStatus, Variant> = {
    held: "outline",
    queued: "warning",
    running: "info",
    finished: "success",
    cancelled: "destructive",
  };
  return (
    <Badge variant={variant[status]}>
      {status === "running" && <LiveDot />}
      {assignmentStatusLabels[status]}
    </Badge>
  );
}

export function AssignmentResultBadge({ result }: { result: AssignmentResult | null }) {
  if (result === null) return null;
  const variant: Record<AssignmentResult, Variant> = {
    complete: "success",
    complete_with_gaps: "warning",
    out_of_budget: "destructive",
    needs_review: "warning",
    no_homepage: "outline",
    failed: "destructive",
  };
  return <Badge variant={variant[result]}>{assignmentResultLabels[result]}</Badge>;
}

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const variant: Record<RunStatus, Variant> = {
    active: "success",
    paused: "warning",
    stopped: "secondary",
  };
  return (
    <Badge variant={variant[status]}>
      {status === "active" && <LiveDot />}
      {runStatusLabels[status]}
    </Badge>
  );
}

export function ReviewStatusBadge({ status }: { status: ReviewStatus }) {
  const variant: Record<ReviewStatus, Variant> = {
    open: "info",
    approved: "success",
    rejected: "destructive",
    merged: "plum",
  };
  return <Badge variant={variant[status]}>{reviewStatusLabels[status]}</Badge>;
}

/** A pulsing dot for a state that is happening right now. */
function LiveDot({ className }: { className?: string }) {
  return (
    <span className={cn("relative flex size-1.5", className)} aria-hidden="true">
      <span className="absolute inline-flex size-full animate-ping rounded-full bg-current opacity-60" />
      <span className="relative inline-flex size-1.5 rounded-full bg-current" />
    </span>
  );
}
