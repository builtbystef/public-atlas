"use client";

import type { RunDetail as RunDetailOutput } from "@public-atlas/api-client";
import { useSuspenseQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { Detail } from "@/components/shared/detail-list";
import { PageHeader } from "@/components/shared/layout/page-header";
import { RunStatusBadge } from "@/components/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AssignmentsTable } from "@/features/assignments/components/assignments-table";
import type { AssignmentSearch } from "@/features/assignments/schemas";
import { browserApi } from "@/lib/api/client";
import { formatDateTime } from "@/lib/formatting/dates";
import { formatCost } from "@/lib/formatting/money";
import { assignmentTypeLabels, humanize, runModeLabels } from "@/lib/labels";

import { useRunActions } from "../hooks/use-run-actions";
import { runQuery } from "../queries";
import { RunActions } from "./run-actions";
import { RunProgressBar, RunResults, totalAssignments } from "./run-progress";

const REFRESH_MS = 5_000;

export function RunDetail({
  id,
  assignmentFilters,
  timeZone,
}: {
  id: string;
  assignmentFilters: AssignmentSearch;
  timeZone: string;
}) {
  const { data: run } = useSuspenseQuery({
    ...runQuery(browserApi, id),
    refetchInterval: (query) => (query.state.data?.status === "active" ? REFRESH_MS : false),
  });
  const actions = useRunActions();

  return (
    <>
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-3">
            {run.name}
            <RunStatusBadge status={run.status} />
            {run.is_eval && <Badge variant="plum">Eval</Badge>}
          </span>
        }
        description={`Created ${formatDateTime(run.created_at, timeZone)}`}
      >
        <RunActions run={run} actions={actions} />
      </PageHeader>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="flex flex-col gap-3 text-sm">
              <Detail label="Country">{run.country_code}</Detail>
              <Detail label="Mode">{runModeLabels[run.mode]}</Detail>
              <Detail label="Video">{run.record_video ? "Recorded" : "Off"}</Detail>
              <Detail label="Filter">
                <RunFilterSummary filter={run.filter} />
              </Detail>
            </dl>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Progress</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <p className="text-2xl font-semibold tabular-nums">
              {totalAssignments(run.progress)}{" "}
              <span className="text-base font-normal text-muted-foreground">assignments</span>
            </p>
            <RunProgressBar progress={run.progress} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Results and cost</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <p className="text-2xl font-semibold tabular-nums">
              {formatCost(run.progress.cost)}{" "}
              <span className="text-base font-normal text-muted-foreground">
                from the usage table
              </span>
            </p>
            <RunResults progress={run.progress} />
          </CardContent>
        </Card>
      </div>

      <section className="mt-8 flex flex-col gap-4">
        <h3 className="text-lg font-semibold">Assignments</h3>
        <AssignmentsTable
          initialFilters={assignmentFilters}
          fixed={{ run_id: run.id }}
          timeZone={timeZone}
        />
      </section>
      {actions.dialog}
    </>
  );
}

/** The filter as the API stored it: each axis with its values, or "any". */
function RunFilterSummary({ filter }: { filter: RunDetailOutput["filter"] }) {
  const list = (key: string): string[] => {
    const value = filter[key];
    return Array.isArray(value) ? value.map(String) : [];
  };
  const rows: [string, ReactNode][] = [
    [
      "Assignment types",
      list("assignment_types")
        .map((t) => (t in assignmentTypeLabels ? assignmentTypeLabels[t as never] : t))
        .join(", "),
    ],
    ["Levels", list("administrative_levels").map(humanize).join(", ")],
    ["Institution types", list("institution_types").map(humanize).join(", ")],
    ["Subjects", list("subject_ids").length > 0 ? `${list("subject_ids").length} chosen` : ""],
  ];
  return (
    <dl className="flex flex-col gap-1">
      {rows.map(([label, value]) => (
        <div key={label} className="flex gap-2">
          <dt className="shrink-0 text-muted-foreground">{label}:</dt>
          <dd>{value || <span className="text-muted-foreground">any</span>}</dd>
        </div>
      ))}
    </dl>
  );
}
