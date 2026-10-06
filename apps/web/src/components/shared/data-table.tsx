"use client";

import {
  createColumnHelper,
  rowPaginationFeature,
  rowSortingFeature,
  tableFeatures,
  useTable,
  type Column,
  type ColumnDef,
  type RowData,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDownIcon, ArrowUpIcon, ArrowUpDownIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PAGE_SIZE } from "@/lib/lists";
import { cn } from "@/lib/utils";

/**
 * TanStack Table v9 registers only the features a table uses, and the types
 * follow: `createColumnHelper<DataTableFeatures, Row>()` knows about sorting
 * because it is declared here. Sorting and paging are the API's job: the
 * table holds one page and the state that asked for it, and a header click or
 * a pager click asks the owner for another page.
 */
export const dataTableFeatures = tableFeatures({
  rowSortingFeature,
  rowPaginationFeature,
});

export type DataTableFeatures = typeof dataTableFeatures;

export function createDataTableColumnHelper<TData extends RowData>() {
  return createColumnHelper<DataTableFeatures, TData>();
}

// The helper's `columns()` returns `ColumnDef<..., any>[]`; this matches it.
// oxlint-disable-next-line typescript/no-explicit-any
export type DataTableColumn<TData extends RowData> = ColumnDef<DataTableFeatures, TData, any>;

interface DataTableProps<TData extends { id: string }> {
  columns: DataTableColumn<TData>[];
  /** The rows of the current page. */
  data: TData[];
  /** Rows across every page: the API's `total`. */
  total: number;
  /** 1-based. */
  page: number;
  pageSize?: number;
  onPageChange: (page: number) => void;
  /** Leave out for a table whose order is fixed. */
  sorting?: SortingState;
  onSortingChange?: (sorting: SortingState) => void;
  emptyMessage?: ReactNode;
  className?: string;
}

const NO_SORTING: SortingState = [];

export function DataTable<TData extends { id: string }>({
  columns,
  data,
  total,
  page,
  pageSize = PAGE_SIZE,
  onPageChange,
  sorting = NO_SORTING,
  onSortingChange,
  emptyMessage = "Nothing here yet.",
  className,
}: DataTableProps<TData>) {
  const pagination = { pageIndex: page - 1, pageSize };
  const table = useTable({
    features: dataTableFeatures,
    columns,
    data,
    getRowId: (row) => row.id,
    manualSorting: true,
    manualPagination: true,
    rowCount: total,
    state: { sorting, pagination },
    onSortingChange: (updater) => {
      onSortingChange?.(typeof updater === "function" ? updater(sorting) : updater);
    },
    onPaginationChange: (updater) => {
      const next = typeof updater === "function" ? updater(pagination) : updater;
      onPageChange(next.pageIndex + 1);
    },
  });
  const rows = table.getRowModel().rows;
  const pageCount = table.getPageCount();
  const first = rows.length === 0 ? 0 : pagination.pageIndex * pageSize + 1;
  const last = pagination.pageIndex * pageSize + rows.length;

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <div className="overflow-x-auto rounded-lg border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder ? null : <table.FlexRender header={header} />}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="h-24 text-center text-muted-foreground"
                >
                  {total > 0 ? "Nothing on this page." : emptyMessage}
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getAllCells().map((cell) => (
                    <TableCell key={cell.id}>
                      <table.FlexRender cell={cell} />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
      {/* Also when the page is past the end (a delete emptied it), so there is a way back. */}
      {(pageCount > 1 || page > 1) && (
        <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2 text-sm text-muted-foreground">
          <span className="tabular-nums">
            {rows.length === 0 ? `0 of ${total}` : `${first}–${last} of ${total}`}
          </span>
          <span>
            Page {page} of {Math.max(pageCount, 1)}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

/** A column header that toggles sorting; use from a column's `header` option. */
export function SortableHeader<TData extends RowData, TValue>({
  column,
  children,
}: {
  column: Column<DataTableFeatures, TData, TValue>;
  children: ReactNode;
}) {
  const sorted = column.getIsSorted();
  const Icon = sorted === "asc" ? ArrowUpIcon : sorted === "desc" ? ArrowDownIcon : ArrowUpDownIcon;
  return (
    <Button
      variant="ghost"
      size="sm"
      className="-ml-2.5 data-[sorted=true]:text-foreground"
      data-sorted={sorted !== false}
      onClick={() => column.toggleSorting(sorted === "asc")}
    >
      {children}
      <Icon className="text-muted-foreground" />
    </Button>
  );
}
