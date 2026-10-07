"use client";

import type { InstitutionOutput } from "@public-atlas/api-client";
import Link from "next/link";

import { createDataTableColumnHelper, SortableHeader } from "@/components/shared/data-table";
import { ExternalLink } from "@/components/shared/external-link";
import { EntityStatusBadge } from "@/components/shared/status-badge";
import { formatDateTime } from "@/lib/formatting/dates";
import { enteredByLabels, humanize } from "@/lib/labels";
import { paths } from "@/lib/routes";

const column = createDataTableColumnHelper<InstitutionOutput>();

export function institutionColumns({ timeZone }: { timeZone: string }) {
  return column.columns([
    column.accessor("name", {
      header: ({ column }) => <SortableHeader column={column}>Institution</SortableHeader>,
      cell: ({ row }) => (
        <Link href={paths.institution(row.original.id)} className="font-medium hover:underline">
          {row.original.name}
        </Link>
      ),
    }),
    column.accessor("institution_type", {
      header: ({ column }) => <SortableHeader column={column}>Type</SortableHeader>,
      cell: ({ row }) => (
        <span className="flex flex-col">
          {humanize(row.original.institution_type)}
          {row.original.suggested_type && (
            <span className="text-xs text-muted-foreground">
              suggested: {row.original.suggested_type}
            </span>
          )}
        </span>
      ),
    }),
    column.accessor((row) => row.place.name, {
      id: "place",
      header: ({ column }) => <SortableHeader column={column}>Place</SortableHeader>,
      cell: ({ row }) => (
        <span className="flex flex-col">
          <Link href={paths.institutionsIn(row.original.place.id)} className="hover:underline">
            {row.original.place.name}
          </Link>
          <span className="text-xs text-muted-foreground">
            {humanize(row.original.place.administrative_level)}
          </span>
        </span>
      ),
    }),
    column.accessor("status", {
      header: ({ column }) => <SortableHeader column={column}>Status</SortableHeader>,
      cell: ({ row }) => <EntityStatusBadge status={row.original.status} />,
    }),
    column.accessor("homepage_url", {
      header: "Homepage",
      enableSorting: false,
      cell: ({ row }) =>
        row.original.homepage_url ? (
          <ExternalLink href={row.original.homepage_url} className="max-w-64 text-xs" />
        ) : (
          <span className="text-muted-foreground">–</span>
        ),
    }),
    column.accessor("entered_by", {
      header: "Entered by",
      enableSorting: false,
      cell: ({ row }) => enteredByLabels[row.original.entered_by],
    }),
    column.accessor("created_at", {
      header: ({ column }) => <SortableHeader column={column}>Created</SortableHeader>,
      cell: ({ row }) => (
        <span className="whitespace-nowrap">
          {formatDateTime(row.original.created_at, timeZone)}
        </span>
      ),
    }),
  ]);
}
