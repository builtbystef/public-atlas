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

type Variant = NonNullable<ComponentProps<typeof Badge>["variant"]>;

/**
 * One badge per status enum, each with a fixed colour per value so a status
 * reads the same on every page: filled for the state that counts (verified,
 * running, active), outlined for the one that waits on someone, destructive
 * for the one that went wrong.
 */
export function EntityStatusBadge({ status }: { status: EntityStatus }) {
  const variant: Record<EntityStatus, Variant> = {
    verified: "default",
    candidate: "secondary",
    needs_review: "outline",
    rejected: "destructive",
  };
  return <Badge variant={variant[status]}>{entityStatusLabels[status]}</Badge>;
}

export function AssignmentStatusBadge({ status }: { status: AssignmentStatus }) {
  const variant: Record<AssignmentStatus, Variant> = {
    held: "outline",
    queued: "secondary",
    running: "default",
    finished: "secondary",
    cancelled: "destructive",
  };
  return <Badge variant={variant[status]}>{assignmentStatusLabels[status]}</Badge>;
}

export function AssignmentResultBadge({ result }: { result: AssignmentResult | null }) {
  if (result === null) return null;
  const variant: Record<AssignmentResult, Variant> = {
    complete: "default",
    complete_with_gaps: "outline",
    out_of_budget: "destructive",
    needs_review: "outline",
    no_homepage: "outline",
    failed: "destructive",
  };
  return <Badge variant={variant[result]}>{assignmentResultLabels[result]}</Badge>;
}

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const variant: Record<RunStatus, Variant> = {
    active: "default",
    paused: "outline",
    stopped: "secondary",
  };
  return <Badge variant={variant[status]}>{runStatusLabels[status]}</Badge>;
}

export function ReviewStatusBadge({ status }: { status: ReviewStatus }) {
  const variant: Record<ReviewStatus, Variant> = {
    open: "default",
    approved: "secondary",
    rejected: "destructive",
    merged: "secondary",
  };
  return <Badge variant={variant[status]}>{reviewStatusLabels[status]}</Badge>;
}
