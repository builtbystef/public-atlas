"use client";

import type { ReviewItemRow } from "@public-atlas/api-client";
import Link from "next/link";

import { createDataTableColumnHelper } from "@/components/shared/data-table";
import { ReviewStatusBadge } from "@/components/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/formatting/dates";
import { entityKindLabels, labelOf, reviewRuleLabels } from "@/lib/labels";
import { paths } from "@/lib/routes";

import type { useReviewActions } from "../hooks/use-review-actions";
import { reasonsOf } from "./question-facts";

const column = createDataTableColumnHelper<ReviewItemRow>();

export function reviewColumns({
  timeZone,
  actions,
}: {
  timeZone: string;
  actions: ReturnType<typeof useReviewActions>;
}) {
  return column.columns([
    column.accessor("label", {
      header: "Entity",
      enableSorting: false,
      cell: ({ row }) => (
        <span className="flex flex-col gap-0.5">
          <Link
            href={paths.reviewItem(row.original.id)}
            className="line-clamp-2 max-w-sm font-medium break-all hover:underline"
          >
            {row.original.label}
          </Link>
          <span className="text-xs text-muted-foreground">
            {entityKindLabels[row.original.entity_kind]}
          </span>
        </span>
      ),
    }),
    column.accessor("rule", {
      header: "Rule",
      enableSorting: false,
      cell: ({ row }) => (
        <span className="flex flex-col gap-1">
          {labelOf(reviewRuleLabels, row.original.rule)}
          {row.original.kind && (
            <Badge variant="outline" className="w-fit font-mono text-[10px]">
              {row.original.kind}
            </Badge>
          )}
        </span>
      ),
    }),
    column.display({
      id: "reasons",
      header: "Reasons",
      cell: ({ row }) => {
        const reasons = reasonsOf(row.original.question);
        return (
          <ul className="flex max-w-md flex-col gap-0.5 text-sm text-muted-foreground">
            {reasons.map((reason) => (
              <li key={reason} className="line-clamp-2">
                {reason}
              </li>
            ))}
          </ul>
        );
      },
    }),
    column.accessor("status", {
      header: "Status",
      enableSorting: false,
      cell: ({ row }) => (
        <span className="flex flex-col gap-1">
          <ReviewStatusBadge status={row.original.status} />
          {row.original.decided_at && (
            <span className="text-xs whitespace-nowrap text-muted-foreground">
              {formatDateTime(row.original.decided_at, timeZone)}
            </span>
          )}
        </span>
      ),
    }),
    column.accessor("raised_by_assignment_id", {
      header: "Raised by",
      enableSorting: false,
      cell: ({ row }) =>
        row.original.raised_by_assignment_id ? (
          <Link
            href={paths.assignment(row.original.raised_by_assignment_id)}
            className="font-mono text-xs hover:underline"
          >
            {row.original.raised_by_assignment_id.slice(0, 8)}
          </Link>
        ) : (
          <span className="text-muted-foreground">–</span>
        ),
    }),
    column.display({
      id: "actions",
      cell: ({ row }) => {
        const item = row.original;
        if (item.status !== "open") return null;
        return (
          <div className="flex justify-end gap-1">
            <Button size="sm" variant="outline" onClick={() => actions.approve(item)}>
              Approve
            </Button>
            {(item.entity_kind === "institution" || item.entity_kind === "place") && (
              <Button size="sm" variant="outline" onClick={() => actions.merge(item)}>
                Merge
              </Button>
            )}
            <Button size="sm" variant="destructive" onClick={() => actions.reject(item)}>
              Reject
            </Button>
          </div>
        );
      },
    }),
  ]);
}
