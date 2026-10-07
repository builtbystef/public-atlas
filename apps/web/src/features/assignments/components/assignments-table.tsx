"use client";

import type {
  AssignmentOutput,
  AssignmentResult,
  AssignmentStatus,
  AssignmentType,
} from "@public-atlas/api-client";
import { useSuspenseQuery } from "@tanstack/react-query";
import { useState } from "react";

import { DataTable } from "@/components/shared/data-table";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { useListState } from "@/hooks/use-list-state";
import { useUrlFilters } from "@/hooks/use-url-filters";
import { browserApi } from "@/lib/api/client";
import {
  assignmentResultLabels,
  assignmentResults,
  assignmentStatusLabels,
  assignmentStatuses,
  assignmentTypeLabels,
  assignmentTypes,
} from "@/lib/labels";
import { cn } from "@/lib/utils";

import { assignmentListQuery } from "../queries";
import {
  assignmentFilters,
  parseAssignmentSearch,
  type AssignmentSearch,
  type FixedFilters,
} from "../schemas";
import { assignmentColumns } from "./assignment-columns";

const REFRESH_MS = 10_000;

export function AssignmentsTable({
  initialFilters,
  fixed = {},
  timeZone,
}: {
  initialFilters: AssignmentSearch;
  fixed?: FixedFilters;
  timeZone: string;
}) {
  const [status, setStatus] = useState<AssignmentStatus | "">(initialFilters.status ?? "");
  const [result, setResult] = useState<AssignmentResult | "">(initialFilters.result ?? "");
  const [type, setType] = useState<AssignmentType | "">(initialFilters.type ?? "");
  const list = useListState({
    filterKey: `${status}\0${result}\0${type}`,
    initial: initialFilters,
    defaultSort: { sort: "created_at", order: "desc" },
  });
  const { deferred, isStale } = useUrlFilters(
    {
      run_id: fixed.run_id === undefined ? initialFilters.run_id : undefined,
      subject_id: fixed.subject_id === undefined ? initialFilters.subject_id : undefined,
      status: status || undefined,
      result: result || undefined,
      type: type || undefined,
      page: list.search.page,
    },
    parseAssignmentSearch,
  );
  const { data: assignments } = useSuspenseQuery({
    ...assignmentListQuery(browserApi, assignmentFilters(deferred, fixed)),
    refetchInterval: REFRESH_MS,
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <NativeSelect
          value={type}
          onChange={(event) => setType(event.target.value as AssignmentType | "")}
          aria-label="Filter by type"
        >
          <NativeSelectOption value="">Any type</NativeSelectOption>
          {assignmentTypes.map((value) => (
            <NativeSelectOption key={value} value={value}>
              {assignmentTypeLabels[value]}
            </NativeSelectOption>
          ))}
        </NativeSelect>
        <NativeSelect
          value={status}
          onChange={(event) => setStatus(event.target.value as AssignmentStatus | "")}
          aria-label="Filter by status"
        >
          <NativeSelectOption value="">Any status</NativeSelectOption>
          {assignmentStatuses.map((value) => (
            <NativeSelectOption key={value} value={value}>
              {assignmentStatusLabels[value]}
            </NativeSelectOption>
          ))}
        </NativeSelect>
        <NativeSelect
          value={result}
          onChange={(event) => setResult(event.target.value as AssignmentResult | "")}
          aria-label="Filter by result"
        >
          <NativeSelectOption value="">Any result</NativeSelectOption>
          {assignmentResults.map((value) => (
            <NativeSelectOption key={value} value={value}>
              {assignmentResultLabels[value]}
            </NativeSelectOption>
          ))}
        </NativeSelect>
        <span className="ml-auto text-sm text-muted-foreground">
          {assignments.total} {assignments.total === 1 ? "assignment" : "assignments"}
        </span>
      </div>
      <DataTable<AssignmentOutput>
        columns={assignmentColumns({ timeZone, showRun: fixed.run_id === undefined })}
        data={assignments.items}
        total={assignments.total}
        page={list.page}
        onPageChange={list.setPage}
        emptyMessage={
          status || result || type
            ? "No assignments match these filters."
            : "No assignments yet. A run spawns them."
        }
        className={cn(isStale && "opacity-60 transition-opacity")}
      />
    </div>
  );
}
