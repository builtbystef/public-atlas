"use client";

import type { ReviewRow } from "@public-atlas/api-client";
import { ChevronRightIcon, LayersIcon } from "lucide-react";
import Link from "next/link";

import { createDataTableColumnHelper, SortableHeader } from "@/components/shared/data-table";
import { ReviewStatusBadge } from "@/components/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/formatting/dates";
import { entityKindLabels, labelOf, reviewRuleLabels } from "@/lib/labels";
import { paths } from "@/lib/routes";
import { cn } from "@/lib/utils";

import type { DecisionTarget, useReviewActions } from "../hooks/use-review-actions";
import { entityCount, isGroup, memberSummary, questionText } from "../question";

const column = createDataTableColumnHelper<ReviewRow>();

export function reviewColumns({
  timeZone,
  actions,
  expanded,
  onToggle,
}: {
  timeZone: string;
  actions: ReturnType<typeof useReviewActions>;
  /** The ids of the rows whose items show. */
  expanded: ReadonlySet<string>;
  onToggle: (id: string) => void;
}) {
  return column.columns([
    column.display({
      id: "expand",
      header: () => <span className="sr-only">Items</span>,
      cell: ({ row }) =>
        isGroup(row.original) && (
          <Button
            size="icon-xs"
            variant="ghost"
            onClick={() => onToggle(row.original.id)}
            aria-expanded={expanded.has(row.original.id)}
            aria-label={expanded.has(row.original.id) ? "Hide the items" : "Show the items"}
          >
            <ChevronRightIcon
              className={cn("transition-transform", expanded.has(row.original.id) && "rotate-90")}
            />
          </Button>
        ),
    }),
    column.display({
      id: "subject",
      header: "Subject",
      cell: ({ row }) => {
        const target = row.original;
        const [first] = target.members;
        if (!first) return null;
        if (isGroup(target)) {
          return (
            <span className="flex max-w-xs min-w-48 flex-col gap-0.5 whitespace-normal">
              <button
                type="button"
                onClick={() => onToggle(target.id)}
                className="text-left font-medium hover:underline"
              >
                {questionText(target.rule, target.question) ??
                  labelOf(reviewRuleLabels, target.rule)}
              </button>
              <span className="line-clamp-1 text-xs text-muted-foreground">
                {memberSummary(target)}
              </span>
            </span>
          );
        }
        return (
          <span className="flex max-w-xs min-w-48 flex-col gap-0.5 whitespace-normal">
            <Link
              href={paths.reviewItem(first.id)}
              className="line-clamp-2 font-medium break-all hover:underline"
            >
              {first.label}
            </Link>
            <span className="text-xs text-muted-foreground">
              {entityKindLabels[first.entity_kind]}
              {first.country_code && ` · ${first.country_code}`}
            </span>
          </span>
        );
      },
    }),
    column.display({
      id: "reason",
      header: "Reason",
      cell: ({ row }) => {
        const target = row.original;
        const reasons = isGroup(target) ? [] : (target.members[0]?.reasons ?? []);
        return (
          <span className="flex max-w-xs min-w-40 flex-col gap-0.5 whitespace-normal">
            <span className="text-sm">{labelOf(reviewRuleLabels, target.rule)}</span>
            {reasons.map((reason) => (
              <span key={reason} className="line-clamp-2 text-xs text-muted-foreground">
                {reason}
              </span>
            ))}
          </span>
        );
      },
    }),
    column.accessor("count", {
      header: ({ column }) => <SortableHeader column={column}>Affects</SortableHeader>,
      cell: ({ row }) => {
        const target = row.original;
        const what = entityCount(target.count, target.members[0]?.entity_kind ?? "institution");
        return isGroup(target) ? (
          <Badge variant="info" className="whitespace-nowrap">
            <LayersIcon />
            {what}
          </Badge>
        ) : (
          <span className="text-sm whitespace-nowrap text-muted-foreground">{what}</span>
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
    column.accessor("raised_at", {
      header: ({ column }) => <SortableHeader column={column}>Raised</SortableHeader>,
      cell: ({ row }) => {
        const assignment = isGroup(row.original)
          ? null
          : row.original.members[0]?.raised_by_assignment_id;
        return (
          <span className="flex flex-col gap-0.5 whitespace-nowrap">
            <span className="text-sm">{formatDateTime(row.original.raised_at, timeZone)}</span>
            {assignment && (
              <Link
                href={paths.assignment(assignment)}
                className="font-mono text-xs text-muted-foreground hover:underline"
              >
                by {assignment.slice(0, 8)}
              </Link>
            )}
          </span>
        );
      },
    }),
    column.display({
      id: "actions",
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => {
        const target = row.original;
        if (target.status !== "open") return null;
        if (isGroup(target)) {
          return (
            <div className="flex justify-end gap-1.5">
              <Button size="sm" variant="outline" onClick={() => actions.approveAll(target)}>
                Approve all {target.count}
              </Button>
              <Button size="sm" variant="destructive" onClick={() => actions.rejectAll(target)}>
                Reject all
              </Button>
            </div>
          );
        }
        const [first] = target.members;
        if (!first) return null;
        return <ItemActions item={{ ...first, kind: target.kind }} actions={actions} />;
      },
    }),
  ]);
}

/** Approve, merge and reject for one item, on its row or among a row's items. */
export function ItemActions({
  item,
  actions,
  size = "sm",
}: {
  item: DecisionTarget;
  actions: ReturnType<typeof useReviewActions>;
  size?: "sm" | "xs";
}) {
  return (
    <div className="flex justify-end gap-1.5">
      <Button size={size} variant="outline" onClick={() => actions.approve(item)}>
        Approve
      </Button>
      {(item.entity_kind === "institution" || item.entity_kind === "place") && (
        <Button size={size} variant="outline" onClick={() => actions.merge(item)}>
          Merge
        </Button>
      )}
      <Button size={size} variant="destructive" onClick={() => actions.reject(item)}>
        Reject
      </Button>
    </div>
  );
}
