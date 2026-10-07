"use client";

import { useQueryClient } from "@tanstack/react-query";
import { DatabaseIcon } from "lucide-react";
import { useRouter } from "next/navigation";

import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { useSidebar } from "@/components/ui/sidebar";
import { databaseCookie, databaseLabels, databases, type Database } from "@/lib/api/database";

/**
 * Chooses which database the console reads: the live graph or the eval
 * harness's. The choice is a cookie both API clients send as a header, so
 * switching clears what the browser cached and re-renders every page from
 * the server.
 */
export function DatabaseSwitch({ database }: { database: Database }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { state } = useSidebar();

  const choose = (next: Database) => {
    if (next === database) return;
    document.cookie = databaseCookie(next);
    queryClient.clear();
    router.refresh();
  };

  if (state === "collapsed") {
    return (
      <div
        className="flex size-8 items-center justify-center text-muted-foreground"
        title={databaseLabels[database]}
      >
        <DatabaseIcon className="size-4" />
      </div>
    );
  }

  return (
    <label className="flex items-center gap-2 px-1 text-xs text-muted-foreground">
      <DatabaseIcon className="size-4 shrink-0" />
      <NativeSelect
        value={database}
        onChange={(event) => choose(event.target.value as Database)}
        aria-label="Database"
        className="h-8 w-full text-xs"
      >
        {databases.map((value) => (
          <NativeSelectOption key={value} value={value}>
            {databaseLabels[value]}
          </NativeSelectOption>
        ))}
      </NativeSelect>
    </label>
  );
}
