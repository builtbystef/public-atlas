"use client";

import type { AssignmentType } from "@public-atlas/api-client";

import { OptionSelect } from "@/components/shared/option-select";
import { EmptyState } from "@/components/shared/empty-state";
import { TableToolbar } from "@/components/shared/table-toolbar";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { assignmentTypeLabels, assignmentTypes } from "@/lib/labels";
import { cn } from "@/lib/utils";

import type { SubjectSort } from "../schemas";
import { change, scoreCounts, type SubjectRow } from "../scores";
import { ScoreCell, ScoreChange } from "./score-cell";

const sortLabels: Record<SubjectSort, string> = {
  lowest: "Lowest recall first",
  change: "Largest drop first",
  subject: "Subject, A to Z",
  find_homepage: "Lowest homepage recall first",
  find_institutions: "Lowest institutions recall first",
  find_sources: "Lowest sources recall first",
};

/** Which subject and type the side panel shows. */
export interface OpenScore {
  subject: string;
  type: AssignmentType;
}

/**
 * Every subject of the run, a row each, with its recall and precision on
 * each assignment type. A cell opens that score's entries.
 */
export function EvalScoresTable({
  rows,
  total,
  floors,
  comparing,
  sort,
  onSortChange,
  belowOnly,
  onBelowOnlyChange,
  open,
  onOpen,
  running,
}: {
  rows: SubjectRow[];
  /** How many subjects there are before the below-target filter. */
  total: number;
  floors: Partial<Record<AssignmentType, number>>;
  comparing: boolean;
  sort: SubjectSort;
  onSortChange: (sort: SubjectSort) => void;
  belowOnly: boolean;
  onBelowOnlyChange: (belowOnly: boolean) => void;
  open: OpenScore | null;
  onOpen: (open: OpenScore) => void;
  running: boolean;
}) {
  if (total === 0) {
    return (
      <EmptyState boxed>
        {running
          ? "Scores are recorded when every subject is done. This page refreshes until then."
          : "This run recorded no scores."}
      </EmptyState>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <TableToolbar
        filters={
          <>
            <OptionSelect
              value={sort}
              onValueChange={onSortChange}
              aria-label="Sort subjects"
              options={(Object.keys(sortLabels) as SubjectSort[]).map((value) => ({
                value,
                label: sortLabels[value],
                disabled: value === "change" && !comparing,
              }))}
            />
            <Label className="ml-2 flex items-center gap-2 font-normal">
              <Checkbox checked={belowOnly} onCheckedChange={onBelowOnlyChange} />
              Only subjects below target
            </Label>
          </>
        }
        count={`${rows.length === total ? total : `${rows.length} of ${total}`} ${total === 1 ? "subject" : "subjects"}`}
      />
      {rows.length === 0 ? (
        <EmptyState boxed>Every subject meets its targets.</EmptyState>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Subject</TableHead>
                {assignmentTypes.map((type) => (
                  <TableHead key={type} className="text-right">
                    <span className="block leading-tight">
                      {assignmentTypeLabels[type].replace("Find ", "")}
                      <br />
                      <span className="text-xs font-normal text-muted-foreground">
                        recall · precision
                      </span>
                    </span>
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.subject} className="hover:bg-transparent">
                  <TableCell className="font-medium">{row.subject}</TableCell>
                  {assignmentTypes.map((type) => (
                    <TableCell key={type} className="p-1 text-right">
                      <ScoreButton
                        row={row}
                        type={type}
                        floor={floors[type]}
                        selected={open?.subject === row.subject && open.type === type}
                        onOpen={onOpen}
                      />
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}

function ScoreButton({
  row,
  type,
  floor,
  selected,
  onOpen,
}: {
  row: SubjectRow;
  type: AssignmentType;
  floor: number | undefined;
  selected: boolean;
  onOpen: (open: OpenScore) => void;
}) {
  const score = row.scores[type];
  if (!score) {
    return (
      <span className="block px-2 py-1">
        <ScoreCell value={null} missing="Not judged on this type" />
      </span>
    );
  }
  const before = row.baseline[type];
  const { hits, misses } = scoreCounts(score);
  return (
    <button
      type="button"
      onClick={() => onOpen({ subject: row.subject, type })}
      aria-label={`${row.subject}, ${assignmentTypeLabels[type]}: show the entries`}
      aria-pressed={selected}
      className={cn(
        "flex w-full flex-col items-end gap-0.5 rounded-md px-2 py-1 outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50",
        selected && "bg-muted",
      )}
    >
      <span className="flex items-center gap-1.5">
        <ScoreChange value={change(score.recall, before?.recall)} />
        <ScoreCell
          value={score.recall}
          floor={floor}
          missing="Nothing to find"
          className="font-medium"
        />
        <span className="text-muted-foreground">·</span>
        <ScoreCell value={score.precision} missing="Nothing saved" />
      </span>
      {hits !== null && hits + misses > 0 && (
        <span className="text-xs text-muted-foreground tabular-nums">
          {hits}/{hits + misses} found
        </span>
      )}
    </button>
  );
}
