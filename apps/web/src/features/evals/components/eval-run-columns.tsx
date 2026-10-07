"use client";

import type { EvalRunOutput } from "@public-atlas/api-client";
import Link from "next/link";

import { createDataTableColumnHelper } from "@/components/shared/data-table";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/formatting/dates";
import { formatCost } from "@/lib/formatting/money";
import { assignmentTypeLabels, assignmentTypes } from "@/lib/labels";
import { paths } from "@/lib/routes";

import { ScoreCell } from "./score-cell";

const column = createDataTableColumnHelper<EvalRunOutput>();

export function evalRunColumns({ timeZone }: { timeZone: string }) {
  return column.columns([
    column.accessor("started_at", {
      header: "Started",
      enableSorting: false,
      cell: ({ row }) => (
        <span className="flex flex-col gap-0.5">
          <Link
            href={paths.evalRun(row.original.id)}
            className="font-medium whitespace-nowrap hover:underline"
          >
            {formatDateTime(row.original.started_at, timeZone)}
          </Link>
          {!row.original.finished_at && (
            <Badge variant="outline" className="w-fit">
              Running
            </Badge>
          )}
        </span>
      ),
    }),
    column.accessor("model", { header: "Model", enableSorting: false }),
    column.accessor("dataset_version", {
      header: "Dataset",
      enableSorting: false,
      cell: ({ row }) => <span className="font-mono text-xs">{row.original.dataset_version}</span>,
    }),
    ...assignmentTypes.map((type) =>
      column.display({
        id: `recall-${type}`,
        header: () => (
          <span className="block text-right leading-tight">
            {assignmentTypeLabels[type].replace("Find ", "")}
            <br />
            <span className="text-xs font-normal text-muted-foreground">recall · precision</span>
          </span>
        ),
        cell: ({ row }) => {
          const summary = row.original.summary[type];
          return (
            <span className="block text-right whitespace-nowrap">
              <ScoreCell value={summary?.mean_recall} /> ·{" "}
              <ScoreCell value={summary?.mean_precision} />
            </span>
          );
        },
      }),
    ),
    column.accessor("cost", {
      header: () => <span className="block text-right">Cost</span>,
      enableSorting: false,
      cell: ({ row }) => (
        <span className="block text-right tabular-nums">{formatCost(row.original.cost)}</span>
      ),
    }),
  ]);
}
