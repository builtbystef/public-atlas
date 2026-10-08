"use client";

import type { EvalRunDetail as EvalRunDetailOutput } from "@public-atlas/api-client";
import { keepPreviousData, useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { ChevronDownIcon, InfoIcon, LoaderIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { JsonView } from "@/components/shared/json-view";
import { PageHeader } from "@/components/shared/layout/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { useUrlFilters } from "@/hooks/use-url-filters";
import { browserApi } from "@/lib/api/client";
import { formatDateTime, formatDuration } from "@/lib/formatting/dates";
import { formatCost } from "@/lib/formatting/money";
import { paths } from "@/lib/routes";
import { cn } from "@/lib/utils";

import { COMPARE_ROWS, evalRunListQuery, evalRunQuery } from "../queries";
import {
  NO_COMPARISON,
  parseEvalRunSearch,
  type EvalRunSearch,
  type SubjectSort,
} from "../schemas";
import { floorsByType, isBelowTarget, sortRows, subjectRows } from "../scores";
import { EvalScoreSheet } from "./eval-score-sheet";
import { EvalScoresTable, type OpenScore } from "./eval-scores-table";
import { EvalSummary, GatesVerdict } from "./eval-summary";

const REFRESH_MS = 15_000;

/**
 * One eval run (spec section 10): whether it met the pilot's targets, the
 * mean per assignment type, then each subject's recall and precision, all
 * set against an earlier run (the one before, unless another is chosen).
 * A score opens beside the table with the entries behind it. What is
 * compared, the order, the filter and the open score live in the URL, so a
 * view can be shared.
 */
export function EvalRunDetail({
  id,
  initialSearch,
  timeZone,
}: {
  id: string;
  initialSearch: EvalRunSearch;
  timeZone: string;
}) {
  const { data: run } = useSuspenseQuery({
    ...evalRunQuery(browserApi, id),
    refetchInterval: (query) => (query.state.data?.finished_at ? false : REFRESH_MS),
  });
  const [compare, setCompare] = useState(initialSearch.compare);
  const [sort, setSort] = useState<SubjectSort>(initialSearch.sort ?? "lowest");
  const [belowOnly, setBelowOnly] = useState(initialSearch.below === "1");
  const [open, setOpen] = useState<OpenScore | null>(
    initialSearch.subject && initialSearch.type
      ? { subject: initialSearch.subject, type: initialSearch.type }
      : null,
  );
  const baselineId = compare === NO_COMPARISON ? null : (compare ?? run.previous_id ?? null);
  const baselineQuery = useQuery({
    ...evalRunQuery(browserApi, baselineId ?? ""),
    enabled: baselineId !== null,
    placeholderData: keepPreviousData,
  });
  const baseline = baselineId !== null ? baselineQuery.data : undefined;
  const { data: candidates } = useQuery(evalRunListQuery(browserApi, COMPARE_ROWS));

  const floors = floorsByType(run.gates);
  const all = subjectRows(run.scores, baseline?.scores);
  const rows = sortRows(
    belowOnly ? all.filter((row) => isBelowTarget(row, floors)) : all,
    sort === "change" && !baseline ? "lowest" : sort,
  );
  const openRow = open ? all.find((row) => row.subject === open.subject) : undefined;
  // A link to a score this run does not have opens nothing, and leaves the URL.
  const shown = open && openRow?.scores[open.type] ? open : null;
  useUrlFilters(
    {
      compare,
      sort: sort === "lowest" ? undefined : sort,
      below: belowOnly ? "1" : undefined,
      subject: shown?.subject,
      type: shown?.type,
    },
    parseEvalRunSearch,
  );
  // The subject above or below the open one in the table, scored on the same type.
  const neighbour = (direction: 1 | -1): OpenScore | null => {
    if (!shown) return null;
    const scored = rows.filter((row) => row.scores[shown.type]);
    const index = scored.findIndex((row) => row.subject === shown.subject);
    const row = index < 0 ? undefined : scored[index + direction];
    return row ? { subject: row.subject, type: shown.type } : null;
  };
  const subjects = Array.isArray(run.settings["subjects"]) ? run.settings["subjects"].length : 0;

  return (
    <>
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-3">
            Eval run of {formatDateTime(run.started_at, timeZone)}
            {run.finished_at ? (
              <GatesVerdict gates={run.gates} />
            ) : (
              <Badge variant="outline">
                <LoaderIcon className="animate-spin" /> Running
              </Badge>
            )}
          </span>
        }
        description={
          <>
            {run.model} · dataset <span className="font-mono text-xs">{run.dataset_version}</span>
            {subjects > 0 && ` · ${subjects} ${subjects === 1 ? "subject" : "subjects"}`}
            {run.finished_at && ` · took ${formatDuration(run.started_at, run.finished_at)}`} ·{" "}
            {formatCost(run.cost)} ·{" "}
            <Link href={paths.run(run.run_id)} className="underline-offset-3 hover:underline">
              its run
            </Link>
          </>
        }
      >
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          Compare with
          <NativeSelect
            value={baselineId ?? NO_COMPARISON}
            onChange={(event) => setCompare(event.target.value)}
          >
            <NativeSelectOption value={NO_COMPARISON}>Nothing</NativeSelectOption>
            {compareOptions(run, candidates?.items ?? [], baseline).map((option) => (
              <NativeSelectOption key={option.id} value={option.id}>
                {formatDateTime(option.started_at, timeZone)}
                {option.id === run.previous_id && " (previous)"}
                {option.dataset_version !== run.dataset_version && " · other dataset"}
                {!option.finished_at && " · running"}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </label>
      </PageHeader>

      <div className="flex flex-col gap-4">
        {!run.finished_at && (
          <Alert>
            <LoaderIcon className="animate-spin" />
            <AlertTitle>This run is still going</AlertTitle>
            <AlertDescription>
              The subjects are worked in the eval database, and their scores are recorded together
              when every one is done. This page refreshes until then.
            </AlertDescription>
          </Alert>
        )}
        {baseline && baseline.dataset_version !== run.dataset_version && (
          <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <InfoIcon className="size-4 shrink-0" />
            The run compared with scored dataset{" "}
            <span className="font-mono text-xs">{baseline.dataset_version}</span>: the labels
            changed since, so some of the change is the dataset&apos;s.
          </p>
        )}
        {baselineId !== null && baselineQuery.isError && (
          <p className="text-sm text-destructive">The run to compare with could not be read.</p>
        )}
        <div className={cn(baselineQuery.isPlaceholderData && "opacity-60 transition-opacity")}>
          <EvalSummary run={run} baseline={baseline} />
        </div>
      </div>

      <section className="mt-8 flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <h3 className="text-lg font-semibold">Scores by subject</h3>
          <p className="text-sm text-muted-foreground">
            Open a score to see what was found, missed and saved wrongly.
            {baseline && " Arrows show the change in recall since the run compared with."}
          </p>
        </div>
        <EvalScoresTable
          rows={rows}
          total={all.length}
          floors={floors}
          comparing={baseline !== undefined}
          sort={sort}
          onSortChange={setSort}
          belowOnly={belowOnly}
          onBelowOnlyChange={setBelowOnly}
          open={shown}
          onOpen={setOpen}
          running={!run.finished_at}
        />
      </section>

      <Collapsible className="mt-8 flex flex-col gap-3">
        <CollapsibleTrigger className="group flex w-fit items-center gap-1.5 text-sm font-medium hover:underline">
          <ChevronDownIcon className="size-4 transition-transform group-data-[panel-open]:rotate-180" />
          Settings the run was started with
        </CollapsibleTrigger>
        <CollapsibleContent>
          <JsonView value={run.settings} />
        </CollapsibleContent>
      </Collapsible>

      <EvalScoreSheet
        open={shown}
        score={shown ? openRow?.scores[shown.type] : undefined}
        baseline={shown ? openRow?.baseline[shown.type] : undefined}
        floor={shown ? floors[shown.type] : undefined}
        previous={neighbour(-1)}
        next={neighbour(1)}
        onOpen={setOpen}
        onClose={() => setOpen(null)}
      />
    </>
  );
}

/**
 * The runs this one can be compared with: the others listed, newest first,
 * and the one compared with now even when it is too old to be listed.
 */
function compareOptions(
  run: EvalRunDetailOutput,
  listed: { id: string; started_at: string; dataset_version: string; finished_at: string | null }[],
  baseline: EvalRunDetailOutput | undefined,
) {
  const options = listed.filter((other) => other.id !== run.id);
  if (baseline && !options.some((other) => other.id === baseline.id)) options.push(baseline);
  return options;
}
