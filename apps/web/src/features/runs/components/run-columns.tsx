"use client";

import type { RunDetail } from "@public-atlas/api-client";
import Link from "next/link";

import { createDataTableColumnHelper } from "@/components/shared/data-table";
import { RunStatusBadge } from "@/components/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/formatting/dates";
import { formatCost } from "@/lib/formatting/money";
import { runModeShortLabels } from "@/lib/labels";
import { paths } from "@/lib/routes";

import { RunProgressBar } from "./run-progress";

const column = createDataTableColumnHelper<RunDetail>();

export function runColumns({ timeZone }: { timeZone: string }) {
  return column.columns([
    column.accessor("name", {
      header: "Run",
      enableSorting: false,
      cell: ({ row }) => (
        <span className="flex flex-wrap items-center gap-2">
          <Link href={paths.run(row.original.id)} className="font-medium hover:underline">
            {row.original.name}
          </Link>
          {row.original.is_eval && <Badge variant="outline">Eval</Badge>}
          {row.original.record_video && <Badge variant="outline">Video</Badge>}
        </span>
      ),
    }),
    column.accessor("country_code", { header: "Country", enableSorting: false }),
    column.accessor("mode", {
      header: "Mode",
      enableSorting: false,
      cell: ({ row }) => runModeShortLabels[row.original.mode],
    }),
    column.accessor("status", {
      header: "Status",
      enableSorting: false,
      cell: ({ row }) => <RunStatusBadge status={row.original.status} />,
    }),
    column.display({
      id: "progress",
      header: "Progress",
      cell: ({ row }) => <RunProgressBar progress={row.original.progress} className="min-w-56" />,
    }),
    column.display({
      id: "cost",
      header: () => <span className="block text-right">Cost</span>,
      cell: ({ row }) => (
        <span className="block text-right tabular-nums">
          {formatCost(row.original.progress.cost)}
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
  ]);
}
