"use client";

import type { EvalEntry, EvalScoreOutput } from "@public-atlas/api-client";
import { ChevronDownIcon, ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import type { ReactNode } from "react";

import { EmptyState } from "@/components/shared/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { assignmentTypeLabels, humanize } from "@/lib/labels";

import { byBucket, change, entriesByKind, groupStats, newLines, splitUrls } from "../scores";
import type { OpenScore } from "./eval-scores-table";
import { ScoreCell, ScoreChange } from "./score-cell";

/**
 * One subject's score on one assignment type, beside the table: the recall
 * and precision with the counts behind them, recall by group, then every
 * entry by kind and bucket, marking those the compared run did not have.
 * The arrows step to the subject above or below in the table's order.
 */
export function EvalScoreSheet({
  open,
  score,
  baseline,
  floor,
  previous,
  next,
  onOpen,
  onClose,
}: {
  open: OpenScore | null;
  score: EvalScoreOutput | undefined;
  baseline: EvalScoreOutput | undefined;
  floor: number | undefined;
  previous: OpenScore | null;
  next: OpenScore | null;
  onOpen: (open: OpenScore) => void;
  onClose: () => void;
}) {
  return (
    <Sheet
      open={open !== null && score !== undefined}
      onOpenChange={(value) => !value && onClose()}
    >
      <SheetContent className="w-full overflow-y-auto data-[side=right]:sm:max-w-xl">
        {open && score && (
          <>
            <SheetHeader className="pr-12">
              <SheetTitle>{open.subject}</SheetTitle>
              <SheetDescription>{assignmentTypeLabels[open.type]}</SheetDescription>
              <div className="mt-2 flex gap-1">
                <Button
                  variant="outline"
                  size="xs"
                  disabled={!previous}
                  onClick={() => previous && onOpen(previous)}
                >
                  <ChevronLeftIcon /> Previous subject
                </Button>
                <Button
                  variant="outline"
                  size="xs"
                  disabled={!next}
                  onClick={() => next && onOpen(next)}
                >
                  Next subject <ChevronRightIcon />
                </Button>
              </div>
            </SheetHeader>
            <ScoreBody score={score} baseline={baseline} floor={floor} />
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function ScoreBody({
  score,
  baseline,
  floor,
}: {
  score: EvalScoreOutput;
  baseline: EvalScoreOutput | undefined;
  floor: number | undefined;
}) {
  const kinds = entriesByKind(score);
  const before = baseline ? entriesByKind(baseline) : undefined;
  const hits = score.hits?.length ?? null;
  const groups = groupStats(score);
  return (
    <div className="flex flex-col gap-6 px-4 pb-6">
      <dl className="grid grid-cols-2 gap-3">
        <Figure
          label="Recall"
          value={<ScoreCell value={score.recall} floor={floor} missing="Nothing to find" />}
          change={change(score.recall, baseline?.recall)}
          detail={hits !== null ? `${hits} of ${hits + score.misses.length} found` : undefined}
        />
        <Figure
          label="Precision"
          value={<ScoreCell value={score.precision} missing="Nothing saved" />}
          change={change(score.precision, baseline?.precision)}
          detail={
            hits !== null
              ? `${hits} of ${hits + score.false_positives.length} saved right`
              : undefined
          }
        />
      </dl>

      {groups && groups.length > 1 && (
        <section className="flex flex-col gap-2">
          <h4 className="font-medium">Recall by group</h4>
          <ul className="flex flex-col gap-1">
            {groups.map((stat) => (
              <li key={stat.group} className="flex items-center gap-3">
                <span className="min-w-0 flex-1 truncate">{humanize(stat.group)}</span>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {stat.hits}/{stat.hits + stat.misses}
                </span>
                <span className="w-10 text-right">
                  <ScoreCell value={stat.hits / (stat.hits + stat.misses)} floor={floor} />
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <EntrySection
        title="Missed"
        entries={kinds.missed}
        fresh={newLines(kinds.missed, before?.missed)}
      />
      <EntrySection
        title="Saved wrong"
        entries={kinds.wrong}
        fresh={newLines(kinds.wrong, before?.wrong)}
      />
      <EntrySection
        title="False positives"
        entries={kinds.falsePositives}
        fresh={newLines(kinds.falsePositives, before?.falsePositives)}
      />
      <Collapsible className="flex flex-col gap-2">
        <CollapsibleTrigger className="group flex w-fit items-center gap-1.5 font-medium hover:underline">
          <ChevronDownIcon className="size-4 transition-transform group-data-[panel-open]:rotate-180" />
          Found <span className="font-normal text-muted-foreground">({hits ?? "not kept"})</span>
        </CollapsibleTrigger>
        <CollapsibleContent>
          {score.hits === null ? (
            <EmptyState>This run was recorded before hits were kept.</EmptyState>
          ) : (
            <Buckets entries={kinds.found} fresh={null} />
          )}
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}

function Figure({
  label,
  value,
  change: moved,
  detail,
}: {
  label: string;
  value: ReactNode;
  change: number | null;
  detail: string | undefined;
}) {
  return (
    <div className="flex flex-col gap-0.5 rounded-lg border p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="flex items-center gap-2 text-xl font-semibold">
        {value}
        <ScoreChange value={moved} showZero />
      </dd>
      {detail && <dd className="text-xs text-muted-foreground">{detail}</dd>}
    </div>
  );
}

function EntrySection({
  title,
  entries,
  fresh,
}: {
  title: string;
  entries: EvalEntry[];
  fresh: Set<string> | null;
}) {
  return (
    <section className="flex flex-col gap-2">
      <h4 className="flex items-center gap-2 font-medium">
        {title} <span className="font-normal text-muted-foreground">({entries.length})</span>
        {fresh !== null && fresh.size > 0 && <Badge variant="warning">{fresh.size} new</Badge>}
      </h4>
      {entries.length === 0 ? (
        <EmptyState>None.</EmptyState>
      ) : (
        <Buckets entries={entries} fresh={fresh} />
      )}
    </section>
  );
}

/** Entries under their buckets, largest bucket first. */
function Buckets({ entries, fresh }: { entries: EvalEntry[]; fresh: Set<string> | null }) {
  return (
    <div className="flex flex-col gap-3">
      {byBucket(entries).map(([bucket, list]) => (
        <div key={bucket} className="flex flex-col gap-1">
          <p className="text-xs font-medium text-muted-foreground">
            {humanize(bucket)} · {list.length}
          </p>
          <ul className="flex flex-col gap-1.5">
            {list.map((entry, index) => (
              <li key={index} className="flex flex-wrap items-baseline gap-x-1.5 break-words">
                <span className="min-w-0">
                  {splitUrls(entry.line).map((part, i) =>
                    part.href ? (
                      <a
                        key={i}
                        href={part.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="break-all text-primary hover:underline"
                      >
                        {part.text}
                      </a>
                    ) : (
                      <span key={i}>{part.text}</span>
                    ),
                  )}
                </span>
                {entry.group && (
                  <Badge variant="outline" className="font-normal">
                    {humanize(entry.group)}
                  </Badge>
                )}
                {fresh?.has(entry.line) && <Badge variant="warning">New</Badge>}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
