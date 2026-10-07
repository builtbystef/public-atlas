"use client";

import type { EvalRunOutput } from "@public-atlas/api-client";
import { useSuspenseQuery } from "@tanstack/react-query";

import { DataTable } from "@/components/shared/data-table";
import { useListState } from "@/hooks/use-list-state";
import { useUrlFilters } from "@/hooks/use-url-filters";
import { browserApi } from "@/lib/api/client";
import { paged } from "@/lib/lists";
import { cn } from "@/lib/utils";

import { evalRunListQuery } from "../queries";
import { parseEvalSearch, type EvalSearch } from "../schemas";
import { evalRunColumns } from "./eval-run-columns";

export function EvalRunsTable({
  initialFilters,
  timeZone,
}: {
  initialFilters: EvalSearch;
  timeZone: string;
}) {
  const list = useListState({
    filterKey: "",
    initial: initialFilters,
    defaultSort: { sort: "started_at", order: "desc" },
  });
  const { deferred, isStale } = useUrlFilters({ page: list.search.page }, parseEvalSearch);
  const { data: runs } = useSuspenseQuery(evalRunListQuery(browserApi, paged(deferred)));
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        {runs.total} {runs.total === 1 ? "eval run" : "eval runs"}, newest first
      </p>
      <DataTable<EvalRunOutput>
        columns={evalRunColumns({ timeZone })}
        data={runs.items}
        total={runs.total}
        page={list.page}
        onPageChange={list.setPage}
        emptyMessage="No eval runs yet. Run `public-atlas eval run`."
        className={cn(isStale && "opacity-60 transition-opacity")}
      />
    </div>
  );
}
