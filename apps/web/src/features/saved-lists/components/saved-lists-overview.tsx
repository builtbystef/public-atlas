"use client";

import type { CountryOutput, InstitutionTypeInput } from "@public-atlas/api-client";
import { useQuery } from "@tanstack/react-query";
import { ChevronRightIcon, DownloadIcon, PlusIcon, UploadIcon } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/shared/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { institutionCountQuery } from "@/features/graph/queries";
import { browserApi } from "@/lib/api/client";
import type { Database } from "@/lib/api/database";
import { formatDate } from "@/lib/formatting/dates";
import { formatCount } from "@/lib/formatting/money";
import { paths } from "@/lib/routes";

import type { SavedList } from "../schemas";
import { savedListActions, useSavedLists } from "../store";
import { FilterChips } from "./filter-chips";
import { SavedListDialog } from "./saved-list-dialog";

/** The front page: every list saved in this browser for this database, newest first. */
export function SavedListsOverview({
  database,
  countries,
  institutionTypes,
  timeZone,
}: {
  database: Database;
  countries: CountryOutput[];
  institutionTypes: InstitutionTypeInput[];
  timeZone: string;
}) {
  const lists = useSavedLists(database);
  const [creating, setCreating] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const actions = savedListActions(database);

  const exportLists = () => {
    const blob = new Blob([actions.exportFile()], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `saved-lists-${database}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const importLists = async (file: File) => {
    try {
      const imported = actions.importFile(await file.text());
      if (imported === null) {
        toast.error("That file is not an export of saved lists.");
      } else {
        toast.success(
          imported === 0
            ? "Nothing new in that file"
            : `Imported ${imported} ${imported === 1 ? "list" : "lists"}`,
        );
      }
    } catch {
      toast.error("This browser would not store the lists. Its storage may be full or turned off.");
    }
  };

  return (
    <>
      <PageHeader>
        <input
          ref={fileInput}
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void importLists(file);
          }}
        />
        <Button variant="ghost" onClick={() => fileInput.current?.click()}>
          <UploadIcon /> Import
        </Button>
        <Button variant="ghost" onClick={exportLists} disabled={!lists?.length}>
          <DownloadIcon /> Export
        </Button>
        <Button onClick={() => setCreating(true)}>
          <PlusIcon /> New list
        </Button>
      </PageHeader>

      {lists === null ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-36" />
          ))}
        </div>
      ) : lists.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-4 py-12 text-center">
          <p className="max-w-md text-sm text-muted-foreground">
            No saved lists yet. Filter the institutions table and press “Save as list”, or start one
            here from a place, a type, a population range and more.
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              nativeButton={false}
              render={<Link href={paths.institutions} />}
            >
              Browse institutions
            </Button>
            <Button onClick={() => setCreating(true)}>
              <PlusIcon /> New list
            </Button>
          </div>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {lists.map((list) => (
            <SavedListCard key={list.id} list={list} countries={countries} timeZone={timeZone} />
          ))}
        </div>
      )}

      {creating && (
        <SavedListDialog
          database={database}
          list={null}
          countries={countries}
          institutionTypes={institutionTypes}
          onClose={() => setCreating(false)}
          onSaved={(list) => toast.success(`Saved “${list.name}”`)}
        />
      )}
    </>
  );
}

function SavedListCard({
  list,
  countries,
  timeZone,
}: {
  list: SavedList;
  countries: CountryOutput[];
  timeZone: string;
}) {
  const count = useQuery(institutionCountQuery(browserApi, list.filters));
  return (
    <Link
      href={paths.list(list.id)}
      className="group/list block rounded-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      <Card className="h-full transition-[box-shadow] group-hover/list:shadow-md group-hover/list:ring-primary/30">
        <CardHeader className="grid-cols-[1fr_auto]">
          <div className="flex min-w-0 flex-col gap-1">
            <CardTitle className="truncate">{list.name}</CardTitle>
            {list.description && (
              <CardDescription className="line-clamp-2">{list.description}</CardDescription>
            )}
          </div>
          <div className="row-span-2 flex flex-col items-end">
            <span className="text-2xl font-semibold tracking-tight tabular-nums">
              {count.data === undefined ? (
                count.isError ? (
                  "–"
                ) : (
                  <Skeleton className="h-7 w-10" />
                )
              ) : (
                formatCount(count.data)
              )}
            </span>
            <span className="text-xs text-muted-foreground">
              {count.data === 1 ? "institution" : "institutions"}
            </span>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <FilterChips filters={list.filters} countries={countries} />
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Updated {formatDate(list.updatedAt, timeZone)}</span>
            <ChevronRightIcon className="size-4 transition-transform group-hover/list:translate-x-0.5" />
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
