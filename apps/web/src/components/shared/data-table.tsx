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
import { createContext, Fragment, useContext, useRef, type ReactNode } from "react";

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
  /** Classes for a row, to set some rows apart. */
  rowClassName?: (row: TData) => string | undefined;
  /** Shown under a row across every column, such as what an expanded row holds; null for none. */
  renderSubRow?: (row: TData) => ReactNode;
}

const NO_SORTING: SortingState = [];

/**
 * The sort state the owner holds, for the headers. Read from here rather than
 * from `column.getIsSorted()`: TanStack copies controlled state into its own
 * store in a layout effect, so a header that reads the store during render is
 * one render behind, and nothing re-renders it afterwards.
 */
const SortingContext = createContext<{
  sorting: SortingState;
  setSorting: ((sorting: SortingState) => void) | undefined;
}>({ sorting: NO_SORTING, setSorting: undefined });

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
  rowClassName,
  renderSubRow,
}: DataTableProps<TData>) {
  const root = useRef<HTMLDivElement>(null);
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

  // The pager sits under the table, so after a page change the new page's
  // top would be off screen; bring it back into view when it is.
  const goTo = (next: number) => {
    onPageChange(next);
    const top = root.current?.getBoundingClientRect().top ?? 0;
    if (top < 0) root.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  };

  return (
    <SortingContext.Provider value={{ sorting, setSorting: onSortingChange }}>
      <div ref={root} className={cn("flex scroll-mt-20 flex-col gap-3", className)}>
        <div className="overflow-x-auto rounded-lg border bg-card shadow-xs">
          <Table>
            <TableHeader className="bg-muted/50">
              {table.getHeaderGroups().map((headerGroup) => (
                <TableRow key={headerGroup.id} className="hover:bg-transparent">
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
                <TableRow className="hover:bg-transparent">
                  <TableCell
                    colSpan={columns.length}
                    className="h-32 text-center whitespace-normal text-muted-foreground"
                  >
                    {total > 0 ? "Nothing on this page." : emptyMessage}
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((row) => {
                  const sub = renderSubRow?.(row.original);
                  return (
                    <Fragment key={row.id}>
                      <TableRow className={rowClassName?.(row.original)}>
                        {row.getAllCells().map((cell) => (
                          <TableCell key={cell.id}>
                            <table.FlexRender cell={cell} />
                          </TableCell>
                        ))}
                      </TableRow>
                      {sub != null && (
                        <TableRow className="hover:bg-transparent">
                          <TableCell colSpan={columns.length} className="p-0 whitespace-normal">
                            {sub}
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  );
                })
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
            <span className="tabular-nums">
              Page {page} of {Math.max(pageCount, 1)}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => goTo(page - 1)}
                disabled={!table.getCanPreviousPage()}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => goTo(page + 1)}
                disabled={!table.getCanNextPage()}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>
    </SortingContext.Provider>
  );
}

/**
 * A column header that toggles sorting; use from a column's `header` option.
 * Unsorted goes ascending, ascending goes descending, descending goes back to
 * ascending: the list is always sorted by something.
 */
export function SortableHeader<TData extends RowData, TValue>({
  column,
  children,
}: {
  column: Column<DataTableFeatures, TData, TValue>;
  children: ReactNode;
}) {
  const { sorting, setSorting } = useContext(SortingContext);
  const current = sorting.find((entry) => entry.id === column.id);
  const sorted = current ? (current.desc ? "desc" : "asc") : false;
  const Icon = sorted === "asc" ? ArrowUpIcon : sorted === "desc" ? ArrowDownIcon : ArrowUpDownIcon;
  return (
    <Button
      variant="ghost"
      size="sm"
      className="-ml-2.5 h-7 text-xs font-medium text-muted-foreground data-[sorted=true]:text-foreground"
      data-sorted={sorted !== false}
      onClick={() => setSorting?.([{ id: column.id, desc: sorted === "asc" }])}
    >
      {children}
      <Icon
        className={cn("size-3.5", sorted === false ? "text-muted-foreground/60" : "text-primary")}
      />
    </Button>
  );
}
