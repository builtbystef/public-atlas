"use client";

import type { AssignmentOutput } from "@public-atlas/api-client";
import Link from "next/link";

import { createDataTableColumnHelper } from "@/components/shared/data-table";
import { AssignmentResultBadge, AssignmentStatusBadge } from "@/components/shared/status-badge";
import { formatDateTime } from "@/lib/formatting/dates";
import { formatCount } from "@/lib/formatting/money";
import { assignmentTypeLabels } from "@/lib/labels";
import { paths } from "@/lib/routes";

import { SubjectLink } from "./subject-link";

const column = createDataTableColumnHelper<AssignmentOutput>();

export function assignmentColumns({
  timeZone,
  showRun,
}: {
  timeZone: string;
  /** Off when every row is of the same run. */
  showRun: boolean;
}) {
  const runColumn = column.accessor("run_id", {
    header: "Run",
    enableSorting: false,
    cell: ({ row }) => (
      <Link
        href={paths.run(row.original.run_id)}
        className="font-mono text-xs text-muted-foreground hover:underline"
      >
        {row.original.run_id.slice(0, 8)}
      </Link>
    ),
  });
  return column.columns([
    column.accessor("type", {
      header: "Assignment",
      enableSorting: false,
      cell: ({ row }) => (
        <Link href={paths.assignment(row.original.id)} className="font-medium hover:underline">
          {assignmentTypeLabels[row.original.type]}
        </Link>
      ),
    }),
    column.accessor("subject_id", {
      header: "Subject",
      enableSorting: false,
      cell: ({ row }) => (
        <SubjectLink subject={row.original.subject} subjectId={row.original.subject_id} showKind />
      ),
    }),
    ...(showRun ? [runColumn] : []),
    column.accessor("status", {
      header: "Status",
      enableSorting: false,
      cell: ({ row }) => <AssignmentStatusBadge status={row.original.status} />,
    }),
    column.accessor("result", {
      header: "Result",
      enableSorting: false,
      cell: ({ row }) => <AssignmentResultBadge result={row.original.result} />,
    }),
    column.accessor("sessions", {
      header: () => <span className="block text-right">Sessions</span>,
      enableSorting: false,
      cell: ({ row }) => (
        <span className="block text-right tabular-nums">{row.original.sessions}</span>
      ),
    }),
    column.accessor("requests_used", {
      header: () => <span className="block text-right">Requests</span>,
      enableSorting: false,
      cell: ({ row }) => (
        <span className="block text-right tabular-nums whitespace-nowrap">
          {row.original.requests_used} / {row.original.budget_requests}
        </span>
      ),
    }),
    column.accessor("tokens_used", {
      header: () => <span className="block text-right">Tokens</span>,
      enableSorting: false,
      cell: ({ row }) => (
        <span className="block text-right tabular-nums whitespace-nowrap">
          {formatCount(row.original.tokens_used)}
        </span>
      ),
    }),
    column.accessor("created_at", {
      header: "Created",
      enableSorting: false,
      cell: ({ row }) => (
        <span className="whitespace-nowrap">
          {formatDateTime(row.original.created_at, timeZone)}
        </span>
      ),
    }),
    column.accessor("finished_at", {
      header: "Finished",
      enableSorting: false,
      cell: ({ row }) => (
        <span className="whitespace-nowrap">
          {formatDateTime(row.original.finished_at, timeZone)}
        </span>
      ),
    }),
  ]);
}
