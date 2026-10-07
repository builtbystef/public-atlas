"use client";

import type { RunDetail } from "@public-atlas/api-client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { assignmentKeys } from "@/features/assignments/queries";
import { errorMessage } from "@/lib/api/errors";

import { ReleaseDialog } from "../components/release-dialog";
import { pauseRun, releaseAssignments, resumeRun, stopRun } from "../mutations";
import { runKeys } from "../queries";

type Move = "pause" | "resume" | "stop";

const MOVES: Record<Move, { call: (id: string) => Promise<RunDetail>; done: string }> = {
  pause: { call: pauseRun, done: "Run paused" },
  resume: { call: resumeRun, done: "Run resumed" },
  stop: { call: stopRun, done: "Run stopped" },
};

/**
 * What a run's page can do in place: pause, resume, stop, and release held
 * assignments through a dialog. Render `dialog` once near the actions.
 */
export function useRunActions(): {
  move: (run: RunDetail, move: Move) => void;
  pendingId: string | null;
  openRelease: (run: RunDetail) => void;
  dialog: ReactNode;
} {
  const queryClient = useQueryClient();
  const [releasing, setReleasing] = useState<RunDetail | null>(null);

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: runKeys.all }),
      queryClient.invalidateQueries({ queryKey: assignmentKeys.all }),
    ]);
  };

  const mutation = useMutation({
    mutationFn: ({ run, move }: { run: RunDetail; move: Move }) => MOVES[move].call(run.id),
    onSuccess: async (_, { move }) => {
      toast.success(MOVES[move].done);
      await invalidate();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const release = useMutation({
    mutationFn: ({
      run,
      limit,
      assignment_type,
    }: {
      run: RunDetail;
      limit: number;
      assignment_type: string;
    }) =>
      releaseAssignments(run.id, {
        limit,
        assignment_type: assignment_type === "" ? null : (assignment_type as never),
        assignment_ids: [],
      }),
    onSuccess: async (released) => {
      toast.success(
        released.length === 1
          ? "Released one assignment"
          : `Released ${released.length} assignments`,
      );
      await invalidate();
    },
  });

  const dialog = releasing && (
    <ReleaseDialog
      open
      onOpenChange={(open) => {
        if (!open) setReleasing(null);
      }}
      held={releasing.progress.by_status["held"] ?? 0}
      onRelease={(values) => release.mutateAsync({ run: releasing, ...values })}
    />
  );

  return {
    move: (run, move) => mutation.mutate({ run, move }),
    pendingId: mutation.isPending ? mutation.variables.run.id : null,
    openRelease: setReleasing,
    dialog,
  };
}
