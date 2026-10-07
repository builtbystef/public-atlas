"use client";

import type { RunDetail } from "@public-atlas/api-client";
import { PauseIcon, PlayIcon, SquareIcon, UnlockIcon } from "lucide-react";

import { Button } from "@/components/ui/button";

import type { useRunActions } from "../hooks/use-run-actions";

/** Pause or resume, stop, and release, as the run's status allows. */
export function RunActions({
  run,
  actions,
}: {
  run: RunDetail;
  actions: ReturnType<typeof useRunActions>;
}) {
  const pending = actions.pendingId === run.id;
  const held = run.progress.by_status["held"] ?? 0;
  const stopped = run.status === "stopped";
  return (
    <>
      <Button
        variant="outline"
        disabled={pending || stopped || held === 0}
        onClick={() => actions.openRelease(run)}
      >
        <UnlockIcon /> Release held{held > 0 && ` (${held})`}
      </Button>
      {run.status === "paused" ? (
        <Button variant="outline" disabled={pending} onClick={() => actions.move(run, "resume")}>
          <PlayIcon /> Resume
        </Button>
      ) : (
        <Button
          variant="outline"
          disabled={pending || stopped}
          onClick={() => actions.move(run, "pause")}
        >
          <PauseIcon /> Pause
        </Button>
      )}
      <Button
        variant="destructive"
        disabled={pending || stopped}
        onClick={() => actions.move(run, "stop")}
      >
        <SquareIcon /> Stop
      </Button>
    </>
  );
}
