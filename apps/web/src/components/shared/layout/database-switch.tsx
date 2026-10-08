"use client";

import { useQueryClient } from "@tanstack/react-query";
import { DatabaseIcon, FlaskConicalIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { RadioCards } from "@/components/shared/radio-cards";
import { Button } from "@/components/ui/button";
import {
  databaseCookie,
  databaseDescriptions,
  databaseLabels,
  databases,
  type Database,
} from "@/lib/api/database";

/**
 * Chooses which database the console reads: the live graph or the eval
 * harness's. The choice is a cookie both API clients send as a header, so
 * switching clears what the browser cached and re-renders every page from
 * the server.
 */
function useChooseDatabase() {
  const router = useRouter();
  const queryClient = useQueryClient();
  return (next: Database) => {
    document.cookie = databaseCookie(next);
    queryClient.clear();
    router.refresh();
  };
}

/** The choice on the settings page: one card per database, with what it holds. */
export function DatabaseChoice({ database }: { database: Database }) {
  const choose = useChooseDatabase();
  const [selected, setSelected] = useState(database);

  return (
    <RadioCards
      name="database"
      legend="Database"
      value={selected}
      onChange={(value) => {
        setSelected(value);
        choose(value);
      }}
      options={databases.map((value) => ({
        value,
        label: databaseLabels[value],
        description: databaseDescriptions[value],
        icon: value === "eval" ? <FlaskConicalIcon /> : <DatabaseIcon />,
      }))}
    />
  );
}

/**
 * Shown above every page while the console reads the eval database, since
 * the choice itself lives on the settings page and is easy to forget.
 */
export function EvalDatabaseBanner() {
  const choose = useChooseDatabase();
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-warning/25 bg-warning/10 px-4 py-2 text-sm md:px-8">
      <FlaskConicalIcon className="size-4 shrink-0 text-warning" />
      <p className="min-w-0 flex-1">
        <span className="font-medium">Eval database.</span>{" "}
        <span className="text-muted-foreground">
          Every page shows what the last eval run built, not the live graph.
        </span>
      </p>
      <Button variant="outline" size="sm" onClick={() => choose("main")}>
        Back to live
      </Button>
    </div>
  );
}
