"use client";

import type { PlaceOutput } from "@public-atlas/api-client";
import Link from "next/link";

import { createDataTableColumnHelper, SortableHeader } from "@/components/shared/data-table";
import { EntityStatusBadge } from "@/components/shared/status-badge";
import { humanize } from "@/lib/labels";
import { paths } from "@/lib/routes";

import { Population } from "./population";

const column = createDataTableColumnHelper<PlaceOutput>();

export function placeColumns({ showCountry }: { showCountry: boolean }) {
  return column.columns([
    column.accessor("name", {
      header: ({ column }) => <SortableHeader column={column}>Place</SortableHeader>,
      cell: ({ row }) => (
        <Link href={paths.place(row.original.id)} className="font-medium hover:underline">
          {row.original.name}
        </Link>
      ),
    }),
    column.accessor("administrative_level", {
      header: ({ column }) => <SortableHeader column={column}>Level</SortableHeader>,
      cell: ({ row }) => humanize(row.original.administrative_level),
    }),
    column.accessor("population", {
      header: ({ column }) => <SortableHeader column={column}>Population</SortableHeader>,
      cell: ({ row }) => <Population value={row.original.population} />,
    }),
    ...(showCountry
      ? [
          column.accessor("country_code", {
            header: "Country",
            enableSorting: false,
            cell: ({ row }) => row.original.country_code,
          }),
        ]
      : []),
    column.accessor("status", {
      header: "Status",
      enableSorting: false,
      cell: ({ row }) => <EntityStatusBadge status={row.original.status} />,
    }),
    column.display({
      id: "institutions",
      header: "",
      cell: ({ row }) => (
        <Link
          href={`${paths.place(row.original.id)}#institutions`}
          className="text-sm whitespace-nowrap text-muted-foreground hover:text-foreground hover:underline"
        >
          Institutions →
        </Link>
      ),
    }),
  ]);
}
