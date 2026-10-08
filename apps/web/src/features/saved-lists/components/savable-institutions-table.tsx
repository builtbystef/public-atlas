"use client";

import type { ComponentProps } from "react";

import { InstitutionsTable } from "@/features/graph/components/institutions-table";
import type { Database } from "@/lib/api/database";

import { SaveListButton } from "./save-list-button";

/** The institutions table with "Save as list" in its toolbar, for the pages that render it. */
export function SavableInstitutionsTable({
  database,
  ...props
}: Omit<ComponentProps<typeof InstitutionsTable>, "actions"> & { database: Database }) {
  return (
    <InstitutionsTable
      {...props}
      actions={(filters) => (
        <SaveListButton
          database={database}
          filters={filters}
          countries={props.countries}
          institutionTypes={props.institutionTypes}
        />
      )}
    />
  );
}
