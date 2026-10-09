"use client";

import type {
  AssignmentOutput,
  AssignmentResult,
  AssignmentStatus,
  AssignmentType,
} from "@public-atlas/api-client";
import { useSuspenseQuery } from "@tanstack/react-query";
import { useState } from "react";

import { OptionSelect } from "@/components/shared/option-select";
import { DataTable } from "@/components/shared/data-table";
import { TableToolbar } from "@/components/shared/table-toolbar";
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
      <TableToolbar
        filters={
          <>
            <OptionSelect<AssignmentType | "">
              value={type}
              onValueChange={setType}
              aria-label="Filter by type"
              options={[
                { value: "", label: "Any type" },
                ...assignmentTypes.map((value) => ({ value, label: assignmentTypeLabels[value] })),
              ]}
            />
            <OptionSelect<AssignmentStatus | "">
              value={status}
              onValueChange={setStatus}
              aria-label="Filter by status"
              options={[
                { value: "", label: "Any status" },
                ...assignmentStatuses.map((value) => ({
                  value,
                  label: assignmentStatusLabels[value],
                })),
              ]}
            />
            <OptionSelect<AssignmentResult | "">
              value={result}
              onValueChange={setResult}
              aria-label="Filter by result"
              options={[
                { value: "", label: "Any result" },
                ...assignmentResults.map((value) => ({
                  value,
                  label: assignmentResultLabels[value],
                })),
              ]}
            />
          </>
        }
        count={`${assignments.total} ${assignments.total === 1 ? "assignment" : "assignments"}`}
        onClear={
          status || result || type
            ? () => {
                setStatus("");
                setResult("");
                setType("");
              }
            : undefined
        }
      />
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
