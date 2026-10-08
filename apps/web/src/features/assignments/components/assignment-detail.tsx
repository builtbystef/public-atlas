"use client";

import type { AssignmentOutput } from "@public-atlas/api-client";
import { useMutation, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { AlertCircleIcon, UnlockIcon } from "lucide-react";
import Link from "next/link";
import { Suspense, type ReactNode } from "react";
import { toast } from "sonner";

import { CollapsibleText } from "@/components/shared/collapsible-text";
import { Detail } from "@/components/shared/detail-list";
import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/layout/page-header";
import { TableSkeleton } from "@/components/shared/skeletons";
import { AssignmentResultBadge, AssignmentStatusBadge } from "@/components/shared/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { releaseAssignments } from "@/features/runs/mutations";
import { runKeys } from "@/features/runs/queries";
import { browserApi } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { formatDateTime, formatDuration } from "@/lib/formatting/dates";
import { formatCompact, formatCost, formatCount, formatPercent } from "@/lib/formatting/money";
import { assignmentTypeLabels, humanize } from "@/lib/labels";
import { paths } from "@/lib/routes";
import { cn } from "@/lib/utils";

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

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Stat label="Cost" value={formatCost(assignment.cost) || "–"}>
          {assignment.sessions === 1 ? "1 session" : `${assignment.sessions} sessions`}
        </Stat>
        <BudgetStat
          label="Requests"
          used={assignment.requests_used}
          budget={assignment.budget_requests}
        />
        <BudgetStat
          label="Tokens"
          used={assignment.tokens_used}
          budget={assignment.budget_tokens}
        />
        <DurationStat assignment={assignment} timeZone={timeZone} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Card>
          <CardHeader>
            <CardTitle>Outcome</CardTitle>
            <CardDescription>What the agent reported when it stopped.</CardDescription>
          </CardHeader>
          <CardContent>
            <Outcome assignment={assignment} />
          </CardContent>
        </Card>
        <Card className="self-start">
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="flex flex-col gap-3 text-sm">
              <Detail label="Run">
                <IdLink href={paths.run(assignment.run_id)} id={assignment.run_id} />
              </Detail>
              <Detail label="Parent">
                {assignment.parent_assignment_id && (
                  <IdLink
                    href={paths.assignment(assignment.parent_assignment_id)}
                    id={assignment.parent_assignment_id}
                  />
                )}
              </Detail>
              <Detail label="Created">{formatDateTime(assignment.created_at, timeZone)}</Detail>
              <Detail label="Started">{formatDateTime(assignment.started_at, timeZone)}</Detail>
              <Detail label="Finished">{formatDateTime(assignment.finished_at, timeZone)}</Detail>
              <Detail label="Assignment">
                <code className="font-mono text-xs break-all text-muted-foreground">
                  {assignment.id}
                </code>
              </Detail>
            </dl>
          </CardContent>
        </Card>
      </div>

      <Section
        title="Findings"
        description="What the assignment saved, with the quote behind each save and the page it was read on."
      >
        <Suspense fallback={<TableSkeleton rows={3} />}>
          <FindingsList assignmentId={assignment.id} live={live} />
        </Suspense>
      </Section>

      <Section
        title="Events"
        description="Everything the agent saw, said and did, session by session."
      >
        <Suspense fallback={<Skeleton className="h-48" />}>
          <EventTimeline assignmentId={assignment.id} live={live} timeZone={timeZone} />
        </Suspense>
      </Section>
    </>
  );
}

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="mt-10 flex flex-col gap-4">
      <div className="flex flex-col gap-0.5">
        <h3 className="text-lg font-semibold">{title}</h3>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      {children}
    </section>
  );
}

/** A record's id as a link, shortened to its first block with the whole id on hover. */
function IdLink({
  href,
  id,
}: {
  href: ReturnType<typeof paths.run> | ReturnType<typeof paths.assignment>;
  id: string;
}) {
  return (
    <Link href={href} title={id} className="font-mono text-xs hover:underline">
      {id.slice(0, 8)}…
    </Link>
  );
}

/** One figure in the strip under the header: a label, a number and a line under it. */
function Stat({
  label,
  value,
  children,
}: {
  label: string;
  value: ReactNode;
  children?: ReactNode;
}) {
  return (
    <Card size="sm" className="gap-2">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <div className="text-2xl font-semibold tracking-tight tabular-nums">{value}</div>
      </CardHeader>
      {children && <CardContent className="text-xs text-muted-foreground">{children}</CardContent>}
    </Card>
  );
}

function BudgetStat({ label, used, budget }: { label: string; used: number; budget: number }) {
  const ratio = budget > 0 ? Math.min(used / budget, 1) : 0;
  return (
    <Stat
      label={label}
      value={
        <span title={`${formatCount(used)} of ${formatCount(budget)}`}>
          {formatCompact(used)}
          <span className="text-base font-normal text-muted-foreground">
            {" "}
            / {formatCompact(budget)}
          </span>
        </span>
      }
    >
      <div className="flex flex-col gap-1.5">
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className={cn(
              "h-full rounded-full transition-[width]",
              ratio >= 1 ? "bg-destructive" : ratio >= 0.8 ? "bg-warning" : "bg-primary",
            )}
            style={{ width: `${ratio * 100}%` }}
          />
        </div>
        <span className="tabular-nums">{formatPercent(ratio)} of the budget</span>
      </div>
    </Stat>
  );
}

function DurationStat({
  assignment,
  timeZone,
}: {
  assignment: AssignmentOutput;
  timeZone: string;
}) {
  const duration = formatDuration(assignment.started_at, assignment.finished_at);
  const note = assignment.finished_at
    ? `Finished ${formatDateTime(assignment.finished_at, timeZone)}`
    : assignment.started_at
      ? `Started ${formatDateTime(assignment.started_at, timeZone)}`
      : assignment.status === "held"
        ? "Waiting to be released"
        : "Not started yet";
  return (
    <Stat label="Duration" value={duration || (assignment.started_at ? "Running" : "–")}>
      {note}
    </Stat>
  );
}

/** The summary, the gaps, the handoff note and the error, each only when there is one. */
function Outcome({ assignment }: { assignment: AssignmentOutput }) {
  const empty =
    !assignment.summary &&
    !assignment.handoff_note &&
    !assignment.last_error &&
    assignment.types_not_found.length === 0;
  if (empty) {
    return (
      <EmptyState>
        {assignment.status === "finished" || assignment.status === "cancelled"
          ? "The agent left no summary."
          : "The agent writes its summary when the assignment finishes."}
      </EmptyState>
    );
  }
  return (
    <div className="flex flex-col gap-5">
      {assignment.last_error && (
        <Alert variant="destructive">
          <AlertCircleIcon />
          <AlertTitle>Last error</AlertTitle>
          <AlertDescription className="break-words">{assignment.last_error}</AlertDescription>
        </Alert>
      )}
      {assignment.summary && (
        <OutcomeBlock title="Summary">
          <CollapsibleText text={assignment.summary} limit={600} className="leading-relaxed" />
        </OutcomeBlock>
      )}
      {assignment.types_not_found.length > 0 && (
        <OutcomeBlock title="Not found">
          <ul className="flex flex-wrap gap-1.5">
            {assignment.types_not_found.map((type) => (
              <li key={type}>
                <Badge variant="warning">{humanize(type)}</Badge>
              </li>
            ))}
          </ul>
        </OutcomeBlock>
      )}
      {assignment.handoff_note && (
        <OutcomeBlock title="Handoff note">
          <div className="rounded-lg bg-muted/60 p-3">
            <CollapsibleText
              text={assignment.handoff_note}
              limit={400}
              className="leading-relaxed text-muted-foreground"
            />
          </div>
        </OutcomeBlock>
      )}
    </div>
  );
}

function OutcomeBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{title}</h4>
      {children}
    </div>
  );
}
