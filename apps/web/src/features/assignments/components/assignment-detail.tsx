"use client";

import { useMutation, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { UnlockIcon } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";
import { toast } from "sonner";

import { Detail } from "@/components/shared/detail-list";
import { PageHeader } from "@/components/shared/layout/page-header";
import { TableSkeleton } from "@/components/shared/skeletons";
import { AssignmentResultBadge, AssignmentStatusBadge } from "@/components/shared/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { releaseAssignments } from "@/features/runs/mutations";
import { runKeys } from "@/features/runs/queries";
import { browserApi } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/formatting/dates";
import { formatCost, formatCount } from "@/lib/formatting/money";
import { assignmentTypeLabels, humanize } from "@/lib/labels";
import { paths } from "@/lib/routes";

import { assignmentKeys, assignmentQuery } from "../queries";
import { EventTimeline } from "./event-timeline";
import { FindingsList } from "./findings-list";
import { SubjectLink } from "./subject-link";

const REFRESH_MS = 5_000;

export function AssignmentDetail({ id, timeZone }: { id: string; timeZone: string }) {
  const queryClient = useQueryClient();
  const { data: assignment } = useSuspenseQuery({
    ...assignmentQuery(browserApi, id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? REFRESH_MS : false;
    },
  });
  const live = assignment.status === "queued" || assignment.status === "running";

  const release = useMutation({
    mutationFn: () =>
      releaseAssignments(assignment.run_id, { limit: 1, assignment_ids: [assignment.id] }),
    onSuccess: async () => {
      toast.success("Assignment released");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: assignmentKeys.all }),
        queryClient.invalidateQueries({ queryKey: runKeys.all }),
      ]);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <>
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-3">
            {assignmentTypeLabels[assignment.type]}
            <AssignmentStatusBadge status={assignment.status} />
            <AssignmentResultBadge result={assignment.result} />
          </span>
        }
        description={
          <span className="flex flex-wrap items-center gap-x-1">
            <span>for</span>
            <SubjectLink subject={assignment.subject} subjectId={assignment.subject_id} showKind />
          </span>
        }
      >
        {assignment.status === "held" && (
          <Button variant="outline" disabled={release.isPending} onClick={() => release.mutate()}>
            <UnlockIcon /> Release
          </Button>
        )}
      </PageHeader>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="flex flex-col gap-3 text-sm">
              <Detail label="Run">
                <Link
                  href={paths.run(assignment.run_id)}
                  className="font-mono text-xs hover:underline"
                >
                  {assignment.run_id}
                </Link>
              </Detail>
              <Detail label="Parent">
                {assignment.parent_assignment_id && (
                  <Link
                    href={paths.assignment(assignment.parent_assignment_id)}
                    className="font-mono text-xs hover:underline"
                  >
                    {assignment.parent_assignment_id}
                  </Link>
                )}
              </Detail>
              <Detail label="Created">{formatDateTime(assignment.created_at, timeZone)}</Detail>
              <Detail label="Started">{formatDateTime(assignment.started_at, timeZone)}</Detail>
              <Detail label="Finished">{formatDateTime(assignment.finished_at, timeZone)}</Detail>
              <Detail label="Sessions">{String(assignment.sessions)}</Detail>
            </dl>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Spend</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <p className="text-2xl font-semibold tabular-nums">{formatCost(assignment.cost)}</p>
            <BudgetBar
              label="Requests"
              used={assignment.requests_used}
              budget={assignment.budget_requests}
            />
            <BudgetBar
              label="Tokens"
              used={assignment.tokens_used}
              budget={assignment.budget_tokens}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Outcome</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="flex flex-col gap-3 text-sm">
              <Detail label="Summary">
                {assignment.summary && (
                  <span className="whitespace-pre-wrap">{assignment.summary}</span>
                )}
              </Detail>
              <Detail label="Not found">
                {assignment.types_not_found.map(humanize).join(", ")}
              </Detail>
              <Detail label="Handoff">
                {assignment.handoff_note && (
                  <span className="whitespace-pre-wrap text-muted-foreground">
                    {assignment.handoff_note}
                  </span>
                )}
              </Detail>
              <Detail label="Last error">
                {assignment.last_error && (
                  <span className="break-words text-destructive">{assignment.last_error}</span>
                )}
              </Detail>
            </dl>
          </CardContent>
        </Card>
      </div>

      <section className="mt-8 flex flex-col gap-4">
        <h3 className="text-lg font-semibold">Findings</h3>
        <Suspense fallback={<TableSkeleton rows={3} />}>
          <FindingsList assignmentId={assignment.id} live={live} />
        </Suspense>
      </section>

      <section className="mt-8 flex flex-col gap-4">
        <h3 className="text-lg font-semibold">Events</h3>
        <Suspense fallback={<Skeleton className="h-48" />}>
          <EventTimeline assignmentId={assignment.id} live={live} timeZone={timeZone} />
        </Suspense>
      </section>
    </>
  );
}

function BudgetBar({ label, used, budget }: { label: string; used: number; budget: number }) {
  const ratio = budget > 0 ? Math.min(used / budget, 1) : 0;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="tabular-nums">
          {formatCount(used)} / {formatCount(budget)}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={ratio >= 1 ? "h-full bg-destructive" : "h-full bg-primary"}
          style={{ width: `${ratio * 100}%` }}
        />
      </div>
    </div>
  );
}
