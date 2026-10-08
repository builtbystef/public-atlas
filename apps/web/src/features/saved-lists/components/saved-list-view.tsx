"use client";

import type { CountryOutput, InstitutionTypeInput } from "@public-atlas/api-client";
import { ArrowUpRightIcon, PencilIcon, Trash2Icon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { PageHeader } from "@/components/shared/layout/page-header";
import { DetailSkeleton, TableSkeleton } from "@/components/shared/skeletons";
import { Button } from "@/components/ui/button";
import { InstitutionsTable } from "@/features/graph/components/institutions-table";
import type { InstitutionSearch } from "@/features/graph/schemas";
import type { Database } from "@/lib/api/database";
import { toSearchString } from "@/lib/lists";
import { paths } from "@/lib/routes";

import { savedListActions, useSavedList } from "../store";
import { FilterChips } from "./filter-chips";
import { SavedListDialog } from "./saved-list-dialog";

/**
 * One saved list: its name and filters, and the institutions that match them
 * now. The list's filters are fixed; the table's other controls narrow it
 * further without changing the list.
 */
export function SavedListView({
  database,
  id,
  initialFilters,
  countries,
  institutionTypes,
  timeZone,
}: {
  database: Database;
  id: string;
  /** The URL's page, sort and any narrowing beyond the list's own filters. */
  initialFilters: InstitutionSearch;
  countries: CountryOutput[];
  institutionTypes: InstitutionTypeInput[];
  timeZone: string;
}) {
  const router = useRouter();
  const list = useSavedList(database, id);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // Deleted here: on its way back to the lists, not a list that was never found.
  const [deleted, setDeleted] = useState(false);

  if (list === undefined || deleted) return <DetailSkeleton />;
  if (list === null) {
    return (
      <div className="flex max-w-lg flex-col items-start gap-3">
        <h2 className="text-2xl font-semibold tracking-tight">List not found</h2>
        <p className="text-muted-foreground">
          Saved lists live in the browser that saved them, one set per database. This one is not
          among this browser’s lists for the database the console is reading.
        </p>
        <Button variant="outline" nativeButton={false} render={<Link href={paths.lists} />}>
          Back to the saved lists
        </Button>
      </div>
    );
  }

  return (
    <>
      <PageHeader title={list.name} description={list.description}>
        <Button
          variant="ghost"
          nativeButton={false}
          render={<Link href={paths.institutionsWhere(toSearchString(list.filters))} />}
        >
          Open in Institutions <ArrowUpRightIcon />
        </Button>
        <Button variant="outline" onClick={() => setEditing(true)}>
          <PencilIcon /> Edit
        </Button>
        <Button variant="outline" onClick={() => setDeleting(true)}>
          <Trash2Icon /> Delete
        </Button>
      </PageHeader>
      <FilterChips filters={list.filters} countries={countries} className="-mt-3 mb-6" />

      <Suspense fallback={<TableSkeleton />}>
        <InstitutionsTable
          // An edit changes what is fixed, so the table starts over.
          key={list.updatedAt}
          initialFilters={initialFilters}
          fixed={list.filters}
          countries={countries}
          institutionTypes={institutionTypes}
          timeZone={timeZone}
        />
      </Suspense>

      {editing && (
        <SavedListDialog
          database={database}
          list={list}
          countries={countries}
          institutionTypes={institutionTypes}
          onClose={() => setEditing(false)}
          onSaved={() => toast.success("List saved")}
        />
      )}
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete “${list.name}”?`}
        description="The list goes from this browser. The institutions it showed stay in the graph."
        confirmLabel="Delete"
        onConfirm={() => {
          setDeleted(true);
          savedListActions(database).remove(list.id);
          toast.success("List deleted");
          router.push(paths.lists);
        }}
      />
    </>
  );
}
