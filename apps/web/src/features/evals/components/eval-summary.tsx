import type { EvalRunDetail, GateOutput } from "@public-atlas/api-client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCount, formatPercent } from "@/lib/formatting/money";
import { assignmentTypeLabels, assignmentTypes } from "@/lib/labels";

import { change } from "../scores";
import { ScoreCell, ScoreChange } from "./score-cell";

/**
 * A card per assignment type: the gate it is held to and whether the run
 * passed it, then the mean recall and precision over the subjects and the
 * entries behind them, each against the run compared with.
 */
export function EvalSummary({
  run,
  baseline,
}: {
  run: EvalRunDetail;
  baseline: EvalRunDetail | undefined;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {assignmentTypes.map((type) => {
        const summary = run.summary[type];
        const before = baseline?.summary[type];
        const gates = run.gates.filter((gate) => gate.assignment_type === type);
        const floor = gates[0]?.floor;
        return (
          <Card key={type}>
            <CardHeader>
              <CardDescription>{assignmentTypeLabels[type]}</CardDescription>
              <CardTitle className="flex items-baseline gap-2 text-2xl">
                <ScoreCell value={summary?.mean_recall} floor={floor} />
                <span className="text-base font-normal text-muted-foreground">recall</span>
                <ScoreChange
                  value={change(summary?.mean_recall, before?.mean_recall)}
                  showZero={before !== undefined}
                  className="self-center"
                />
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-sm">
              <p className="flex flex-wrap items-baseline gap-x-1.5 text-muted-foreground">
                <ScoreCell value={summary?.mean_precision} missing="Nothing saved" /> precision
                <ScoreChange value={change(summary?.mean_precision, before?.mean_precision)} />
                <span>
                  · mean of {summary?.subjects ?? 0}{" "}
                  {summary?.subjects === 1 ? "subject" : "subjects"}
                </span>
              </p>
              {summary && (
                <p className="text-muted-foreground">
                  {summary.hits !== null && <>{formatCount(summary.hits)} found, </>}
                  {formatCount(summary.misses)} missed, {formatCount(summary.false_positives)} saved
                  wrongly
                </p>
              )}
              {gates.map((gate) => (
                <GateLine
                  key={gate.name}
                  gate={gate}
                  before={baseline?.gates.find((other) => other.name === gate.name)}
                  running={!run.finished_at}
                />
              ))}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

/** A gate: its floor, the run's recall over the gate's scope, and the verdict. */
function GateLine({
  gate,
  before,
  running,
}: {
  gate: GateOutput;
  before: GateOutput | undefined;
  running: boolean;
}) {
  const { hits, misses } = gate;
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-2.5 py-1.5"
      title={gate.what}
    >
      <span className="text-xs text-muted-foreground">
        Target {formatPercent(gate.floor)} recall
      </span>
      {hits !== null && misses !== null ? (
        <span className="flex items-center gap-1.5">
          {gate.recall !== null && (
            <span className="text-xs text-muted-foreground tabular-nums">
              {hits}/{hits + misses}
            </span>
          )}
          <ScoreCell value={gate.recall} floor={gate.floor} missing="Nothing in scope" />
          <ScoreChange value={change(gate.recall, before?.recall)} />
          <GateVerdict verdict={gate.verdict} />
        </span>
      ) : (
        <Badge variant="outline">{running ? "Waiting for scores" : "Not recorded"}</Badge>
      )}
    </div>
  );
}

function GateVerdict({ verdict }: { verdict: GateOutput["verdict"] }) {
  if (verdict === "pass") return <Badge variant="success">Pass</Badge>;
  if (verdict === "fail") return <Badge variant="destructive">Fail</Badge>;
  return (
    <Badge variant="outline" title="This run scored nothing in the gate's scope">
      Not judged
    </Badge>
  );
}

/** The run's verdict across its gates, for the header: how many it met of those judged. */
export function GatesVerdict({ gates }: { gates: readonly GateOutput[] }) {
  const judged = gates.filter((gate) => gate.verdict !== null);
  if (judged.length === 0) return null;
  const passed = judged.filter((gate) => gate.verdict === "pass").length;
  const all = passed === judged.length;
  return (
    <Badge variant={all ? "success" : "destructive"}>
      {all
        ? `${judged.length === 1 ? "Target" : `All ${judged.length} targets`} met`
        : `${passed} of ${judged.length} targets met`}
    </Badge>
  );
}
