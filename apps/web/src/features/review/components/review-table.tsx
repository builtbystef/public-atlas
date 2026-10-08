"use client";

import type { ReviewItemRow } from "@public-atlas/api-client";
import { useSuspenseQuery } from "@tanstack/react-query";
import { useState } from "react";

import { DataTable } from "@/components/shared/data-table";
import { TableToolbar } from "@/components/shared/table-toolbar";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { useListState } from "@/hooks/use-list-state";
import { useUrlFilters } from "@/hooks/use-url-filters";
import { browserApi } from "@/lib/api/client";
import {
  reviewRuleLabels,
  reviewRules,
  reviewStatusLabels,
  reviewStatuses,
  type ReviewRule,
} from "@/lib/labels";
import { cn } from "@/lib/utils";

import type { useReviewActions } from "../hooks/use-review-actions";
import { reviewListQuery } from "../queries";
import { parseReviewSearch, reviewFilters, type ReviewSearch } from "../schemas";
import { reviewColumns } from "./review-columns";

const REFRESH_MS = 15_000;

export function ReviewTable({
  initialFilters,
  timeZone,
  actions,
}: {
  initialFilters: ReviewSearch;
  timeZone: string;
  actions: ReturnType<typeof useReviewActions>;
}) {
  const [status, setStatus] = useState<ReviewSearch["status"]>(initialFilters.status ?? "open");
  const [rule, setRule] = useState<ReviewRule | "">(initialFilters.rule ?? "");
  const list = useListState({
    filterKey: `${status}\0${rule}`,
    initial: initialFilters,
    defaultSort: { sort: "created_at", order: "desc" },
  });
  const { deferred, isStale } = useUrlFilters(
    {
      status: status === "open" ? undefined : status,
      rule: rule || undefined,
      page: list.search.page,
    },
    parseReviewSearch,
  );
  const { data: items } = useSuspenseQuery({
    ...reviewListQuery(browserApi, reviewFilters(deferred)),
    refetchInterval: REFRESH_MS,
  });

  return (
    <div className="flex flex-col gap-4">
      <TableToolbar
        filters={
          <>
            <NativeSelect
              value={status}
              onChange={(event) => setStatus(event.target.value as ReviewSearch["status"])}
              aria-label="Filter by status"
            >
              {reviewStatuses.map((value) => (
                <NativeSelectOption key={value} value={value}>
                  {reviewStatusLabels[value]}
                </NativeSelectOption>
              ))}
              <NativeSelectOption value="all">Any status</NativeSelectOption>
            </NativeSelect>
            <NativeSelect
              value={rule}
              onChange={(event) => setRule(event.target.value as ReviewRule | "")}
              aria-label="Filter by rule"
            >
              <NativeSelectOption value="">Any rule</NativeSelectOption>
              {reviewRules.map((value) => (
                <NativeSelectOption key={value} value={value}>
                  {reviewRuleLabels[value]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </>
        }
        count={`${items.total} ${items.total === 1 ? "item" : "items"}`}
        onClear={
          status !== "open" || rule
            ? () => {
                setStatus("open");
                setRule("");
              }
            : undefined
        }
      />
      <DataTable<ReviewItemRow>
        columns={reviewColumns({ timeZone, actions })}
        data={items.items}
        total={items.total}
        page={list.page}
        onPageChange={list.setPage}
        emptyMessage={
          status === "open" && !rule ? "The queue is empty." : "No items match these filters."
        }
        className={cn(isStale && "opacity-60 transition-opacity")}
      />
    </div>
  );
}
