import type {
  EvalRunDetail as EvalRunDetailOutput,
  EvalScoreOutput,
} from "@public-atlas/api-client";
import Link from "next/link";

import { Detail } from "@/components/shared/detail-list";
import { EmptyState } from "@/components/shared/empty-state";
import { JsonView } from "@/components/shared/json-view";
import { PageHeader } from "@/components/shared/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime } from "@/lib/formatting/dates";
import { formatCost } from "@/lib/formatting/money";
import { assignmentTypeLabels, assignmentTypes } from "@/lib/labels";
import { paths } from "@/lib/routes";

import { ScoreCell } from "./score-cell";

interface Entry {
  line?: unknown;
  bucket?: unknown;
  group?: unknown;
}

/**
 * One eval run (spec section 10): the mean per assignment type, then every
 * subject's recall and precision with the misses and false positives
 * behind them, grouped by the bucket the scorer put each in.
 */
export function EvalRunDetail({ run, timeZone }: { run: EvalRunDetailOutput; timeZone: string }) {
  const subjects = new Map<string, EvalScoreOutput[]>();
  for (const score of run.scores) {
    const list = subjects.get(score.subject) ?? [];
    list.push(score);
    subjects.set(score.subject, list);
  }

  return (
    <>
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-3">
            Eval run of {formatDateTime(run.started_at, timeZone)}
            {!run.finished_at && <Badge variant="outline">Running</Badge>}
          </span>
        }
        description={`${run.model} on dataset ${run.dataset_version}`}
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {assignmentTypes.map((type) => {
          const summary = run.summary[type];
          return (
            <Card key={type}>
              <CardHeader>
                <CardDescription>{assignmentTypeLabels[type]}</CardDescription>
                <CardTitle className="text-2xl">
                  <ScoreCell value={summary?.mean_recall} />
                  <span className="text-base font-normal text-muted-foreground"> recall</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">
                <ScoreCell value={summary?.mean_precision} /> precision over{" "}
                {summary?.subjects ?? 0} {summary?.subjects === 1 ? "subject" : "subjects"}
              </CardContent>
            </Card>
          );
        })}
        <Card>
          <CardHeader>
            <CardDescription>Cost</CardDescription>
            <CardTitle className="text-2xl tabular-nums">{formatCost(run.cost)}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {run.finished_at
              ? `Finished ${formatDateTime(run.finished_at, timeZone)}`
              : "Still running"}
          </CardContent>
        </Card>
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Card>
          <CardHeader>
            <CardTitle>Scores by subject</CardTitle>
            <CardDescription>
              Open a row to see what was missed and what was saved wrongly.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {subjects.size === 0 ? (
              <EmptyState>No scores yet.</EmptyState>
            ) : (
              <div className="overflow-x-auto rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Subject</TableHead>
                      <TableHead>Assignment type</TableHead>
                      <TableHead className="text-right">Recall</TableHead>
                      <TableHead className="text-right">Precision</TableHead>
                      <TableHead className="text-right">Misses</TableHead>
                      <TableHead className="text-right">False positives</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {[...subjects.entries()].flatMap(([subject, scores]) =>
                      scores.map((score, index) => (
                        <ScoreRow
                          key={score.id}
                          score={score}
                          subject={index === 0 ? subject : null}
                        />
                      )),
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Run</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <dl className="flex flex-col gap-3 text-sm">
              <Detail label="Run">
                <Link href={paths.run(run.run_id)} className="font-mono text-xs hover:underline">
                  {run.run_id}
                </Link>
              </Detail>
              <Detail label="Model">{run.model}</Detail>
              <Detail label="Dataset">{run.dataset_version}</Detail>
              <Detail label="Started">{formatDateTime(run.started_at, timeZone)}</Detail>
              <Detail label="Finished">{formatDateTime(run.finished_at, timeZone)}</Detail>
            </dl>
            <div className="flex flex-col gap-1">
              <h4 className="text-xs font-medium text-muted-foreground uppercase">Settings</h4>
              <JsonView value={run.settings} />
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function ScoreRow({ score, subject }: { score: EvalScoreOutput; subject: string | null }) {
  const misses = score.misses as Entry[];
  const falsePositives = score.false_positives as Entry[];
  const open = misses.length > 0 || falsePositives.length > 0;
  return (
    <>
      <TableRow>
        <TableCell className="font-medium">{subject ?? ""}</TableCell>
        <TableCell>{assignmentTypeLabels[score.assignment_type]}</TableCell>
        <TableCell className="text-right">
          <ScoreCell value={score.recall} />
        </TableCell>
        <TableCell className="text-right">
          <ScoreCell value={score.precision} />
        </TableCell>
        <TableCell className="text-right tabular-nums">{misses.length}</TableCell>
        <TableCell className="text-right tabular-nums">{falsePositives.length}</TableCell>
      </TableRow>
      {open && (
        <TableRow className="hover:bg-transparent">
          <TableCell colSpan={6} className="p-0">
            <details className="group">
              <summary className="cursor-pointer px-3 py-2 text-xs text-muted-foreground select-none hover:text-foreground">
                Show the misses and false positives
              </summary>
              <div className="grid gap-4 px-3 pb-3 md:grid-cols-2">
                <EntryList title="Missed" entries={misses} />
                <EntryList title="Saved wrongly" entries={falsePositives} />
              </div>
            </details>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

function EntryList({ title, entries }: { title: string; entries: Entry[] }) {
  const buckets = new Map<string, Entry[]>();
  for (const entry of entries) {
    const bucket = typeof entry.bucket === "string" ? entry.bucket : "other";
    const list = buckets.get(bucket) ?? [];
    list.push(entry);
    buckets.set(bucket, list);
  }
  return (
    <div className="flex flex-col gap-2 text-sm">
      <h4 className="font-medium">
        {title} <span className="text-muted-foreground">({entries.length})</span>
      </h4>
      {entries.length === 0 ? (
        <EmptyState>None.</EmptyState>
      ) : (
        [...buckets.entries()].map(([bucket, list]) => (
          <div key={bucket} className="flex flex-col gap-1">
            <p className="text-xs text-muted-foreground">
              {bucket} · {list.length}
            </p>
            <ul className="flex list-disc flex-col gap-0.5 pl-5">
              {list.map((entry, index) => (
                <li key={index} className="break-words">
                  {typeof entry.line === "string" ? entry.line : JSON.stringify(entry.line)}
                  {typeof entry.group === "string" && (
                    <span className="ml-1 text-xs text-muted-foreground">({entry.group})</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </div>
  );
}
