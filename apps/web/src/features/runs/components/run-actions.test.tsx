// @vitest-environment jsdom
import type { RunDetail } from "@public-atlas/api-client";
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vite-plus/test";

import type { useRunActions } from "../hooks/use-run-actions";
import { RunActions } from "./run-actions";

function run(status: RunDetail["status"], held: number): RunDetail {
  return {
    id: "0199e8b0-0000-7000-8000-00000000000a",
    name: "Ontario",
    country_code: "CA",
    mode: "step",
    status,
    filter: {},
    is_eval: false,
    record_video: false,
    created_at: "2026-10-01T00:00:00Z",
    progress: {
      by_status: held > 0 ? { held, running: 1 } : { running: 1 },
      by_result: {},
      cost: "0",
    },
  };
}

function actions(pendingId: string | null = null): ReturnType<typeof useRunActions> {
  return {
    move: vi.fn<(run: RunDetail, move: "pause" | "resume" | "stop") => void>(),
    pendingId,
    openRelease: vi.fn<(run: RunDetail) => void>(),
    dialog: null,
  };
}

function buttons() {
  return Object.fromEntries(
    screen.getAllByRole("button").map((button) => [button.textContent?.trim(), button]),
  ) as Record<string, HTMLButtonElement>;
}

test("a stopped run offers no actions", () => {
  render(<RunActions run={run("stopped", 3)} actions={actions()} />);
  const all = buttons();
  expect(Object.keys(all)).toEqual(["Release held (3)", "Pause", "Stop"]);
  expect(all["Release held (3)"]!.disabled).toBe(true);
  expect(all["Pause"]!.disabled).toBe(true);
  expect(all["Stop"]!.disabled).toBe(true);
});

test("release is disabled at zero held, while pause and stop stay open", () => {
  render(<RunActions run={run("active", 0)} actions={actions()} />);
  const all = buttons();
  expect(Object.keys(all)).toEqual(["Release held", "Pause", "Stop"]);
  expect(all["Release held"]!.disabled).toBe(true);
  expect(all["Pause"]!.disabled).toBe(false);
  expect(all["Stop"]!.disabled).toBe(false);
});

test("a paused run offers resume in place of pause", () => {
  const given = actions();
  render(<RunActions run={run("paused", 2)} actions={given} />);
  const all = buttons();
  expect(Object.keys(all)).toEqual(["Release held (2)", "Resume", "Stop"]);
  all["Resume"]!.click();
  expect(given.move).toHaveBeenCalledWith(run("paused", 2), "resume");
  all["Release held (2)"]!.click();
  expect(given.openRelease).toHaveBeenCalledWith(run("paused", 2));
});

test("while this run's move is pending every action waits", () => {
  render(<RunActions run={run("active", 2)} actions={actions(run("active", 2).id)} />);
  expect(Object.values(buttons()).map((button) => button.disabled)).toEqual([true, true, true]);
  // Another run's pending move does not hold this one.
  render(<RunActions run={run("active", 2)} actions={actions("another-run")} />);
  expect(Object.values(buttons()).filter((button) => !button.disabled)).toHaveLength(3);
});
