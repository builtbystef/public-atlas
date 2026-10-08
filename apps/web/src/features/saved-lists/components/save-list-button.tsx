"use client";

import type { CountryOutput, InstitutionTypeInput } from "@public-atlas/api-client";
import { BookmarkPlusIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { InstitutionFilterValues } from "@/features/graph/schemas";
import type { Database } from "@/lib/api/database";
import { paths } from "@/lib/routes";

import { SavedListDialog } from "./saved-list-dialog";

/** Saves the filters in force as a new list, after asking for its name. */
export function SaveListButton({
  database,
  filters,
  countries,
  institutionTypes,
}: {
  database: Database;
  filters: InstitutionFilterValues;
  countries: CountryOutput[];
  institutionTypes: InstitutionTypeInput[];
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <BookmarkPlusIcon /> Save as list
      </Button>
      {open && (
        <SavedListDialog
          database={database}
          list={null}
          filters={filters}
          countries={countries}
          institutionTypes={institutionTypes}
          onClose={() => setOpen(false)}
          onSaved={(list) =>
            toast.success(`Saved “${list.name}”`, {
              action: { label: "Open", onClick: () => router.push(paths.list(list.id)) },
            })
          }
        />
      )}
    </>
  );
}
