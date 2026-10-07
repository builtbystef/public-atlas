import type { AssignmentOutput, ReleaseInput, RunDetail, RunInput } from "@public-atlas/api-client";

import { browserApi } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";

export async function createRun(body: RunInput): Promise<RunDetail> {
  return unwrap(await browserApi.POST("/runs", { body }));
}

export async function pauseRun(id: string): Promise<RunDetail> {
  return unwrap(
    await browserApi.POST("/runs/{run_id}/pause", { params: { path: { run_id: id } } }),
  );
}

export async function resumeRun(id: string): Promise<RunDetail> {
  return unwrap(
    await browserApi.POST("/runs/{run_id}/resume", { params: { path: { run_id: id } } }),
  );
}

export async function stopRun(id: string): Promise<RunDetail> {
  return unwrap(await browserApi.POST("/runs/{run_id}/stop", { params: { path: { run_id: id } } }));
}

/** Queues held assignments of the run: the next `limit`, or the ones named. */
export async function releaseAssignments(
  id: string,
  body: ReleaseInput,
): Promise<AssignmentOutput[]> {
  return unwrap(
    await browserApi.POST("/runs/{run_id}/release", { params: { path: { run_id: id } }, body }),
  );
}
