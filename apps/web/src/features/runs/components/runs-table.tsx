"use client";

import type { RunDetail } from "@public-atlas/api-client";
import { useSuspenseQuery } from "@tanstack/react-query";

import { DataTable } from "@/components/shared/data-table";
import { useListState } from "@/hooks/use-list-state";
import { useUrlFilters } from "@/hooks/use-url-filters";
import { browserApi } from "@/lib/api/client";
import { paged } from "@/lib/lists";
import { cn } from "@/lib/utils";

import { runListQuery } from "../queries";
import { parseRunSearch, type RunSearch } from "../schemas";
import { runColumns } from "./run-columns";

const REFRESH_MS = 10_000;

export function RunsTable({
  initialFilters,
  timeZone,
}: {
  initialFilters: RunSearch;
  timeZone: string;
}) {
  const list = useListState({
    filterKey: "",
    initial: initialFilters,
    defaultSort: { sort: "created_at", order: "desc" },
  });
  const { deferred, isStale } = useUrlFilters({ page: list.search.page }, parseRunSearch);
  const { data: runs } = useSuspenseQuery({
    ...runListQuery(browserApi, paged(deferred)),
    refetchInterval: REFRESH_MS,
  });

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        {runs.total} {runs.total === 1 ? "run" : "runs"}
      </p>
      <DataTable<RunDetail>
        columns={runColumns({ timeZone })}
        data={runs.items}
        total={runs.total}
        page={list.page}
        onPageChange={list.setPage}
        emptyMessage="No runs yet. Start one to put the agent to work."
        className={cn(isStale && "opacity-60 transition-opacity")}
      />
    </div>
  );
}
