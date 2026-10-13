// @vitest-environment jsdom
import type { AssignmentOutput, RunDetail } from "@public-atlas/api-client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { toast } from "sonner";
import { afterEach, expect, test, vi } from "vite-plus/test";

import { assignmentKeys } from "@/features/assignments/queries";
import { ApiError } from "@/lib/api/errors";

import { RunActions } from "../components/run-actions";
import { pauseRun, releaseAssignments, resumeRun, stopRun } from "../mutations";
import { runKeys } from "../queries";
import { useRunActions } from "./use-run-actions";

// The API calls, as fakes that answer what the API would; nothing leaves the test.
vi.mock("../mutations", () => ({
  pauseRun: vi.fn<typeof pauseRun>(),
  resumeRun: vi.fn<typeof resumeRun>(),
  stopRun: vi.fn<typeof stopRun>(),
  releaseAssignments: vi.fn<typeof releaseAssignments>(),
}));

const RUN_ID = "0199e8b0-0000-7000-8000-00000000000a";

function run(status: RunDetail["status"] = "active", held = 3): RunDetail {
  return {
    id: RUN_ID,
    name: "Ontario",
    country_code: "CA",
    mode: "step",
    status,
    filter: {},
    is_eval: false,
    record_video: false,
    created_at: "2026-10-01T00:00:00Z",
    progress: { by_status: { held, running: 1 }, by_result: {}, cost: "0" },
  };
}

function assignment(n: number): AssignmentOutput {
  return {
    id: `0199e8b0-0000-7000-8000-0000000000${n}0`,
    run_id: RUN_ID,
    type: "find_sources",
    subject_id: "0199e8b0-0000-7000-8000-000000000001",
    status: "queued",
    result: null,
    budget_requests: 40,
    budget_tokens: 200000,
    requests_used: 0,
    tokens_used: 0,
    sessions: 0,
    handoff_note: null,
    summary: null,
    types_not_found: [],
    last_error: null,
    parent_assignment_id: null,
    created_at: "2026-10-01T00:00:00Z",
    started_at: null,
    finished_at: null,
  };
}

/** A run's page: the buttons and the dialog the hook renders. */
function Page({ run }: { run: RunDetail }) {
  const actions = useRunActions();
  return (
    <>
      <RunActions run={run} actions={actions} />
      {actions.dialog}
    </>
  );
}

function mount(detail: RunDetail) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidated = vi.spyOn(queryClient, "invalidateQueries");
  render(
    <QueryClientProvider client={queryClient}>
      <Page run={detail} />
    </QueryClientProvider>,
  );
  return { invalidated, user: userEvent.setup() };
}

const success = vi.spyOn(toast, "success");
const failure = vi.spyOn(toast, "error");

afterEach(() => {
  vi.clearAllMocks();
});

test.each([
  ["Pause", pauseRun, "Run paused", "active"],
  ["Resume", resumeRun, "Run resumed", "paused"],
  ["Stop", stopRun, "Run stopped", "active"],
] as const)(
  "%s calls the API with the run's id, says so, and refreshes runs and assignments",
  async (label, call, done, status) => {
    vi.mocked(call).mockResolvedValue(run(status));
    const { invalidated, user } = mount(run(status));

    await user.click(screen.getByRole("button", { name: label }));

    await waitFor(() => expect(success).toHaveBeenCalledWith(done));
    expect(call).toHaveBeenCalledExactlyOnceWith(RUN_ID);
    expect(invalidated.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([
      runKeys.all,
      assignmentKeys.all,
    ]);
  },
);

test("a move the API refuses is reported in the API's words and refreshes nothing", async () => {
  vi.mocked(stopRun).mockRejectedValue(new ApiError(409, "Run is already stopped"));
  const { invalidated, user } = mount(run());

  await user.click(screen.getByRole("button", { name: "Stop" }));

  await waitFor(() => expect(failure).toHaveBeenCalledWith("Run is already stopped"));
  expect(success).not.toHaveBeenCalled();
  expect(invalidated).not.toHaveBeenCalled();
});

test("a release of any type sends a null type, counts what came back, and refreshes", async () => {
  vi.mocked(releaseAssignments).mockResolvedValue([assignment(1), assignment(2)]);
  const { invalidated, user } = mount(run("active", 3));

  await user.click(screen.getByRole("button", { name: "Release held (3)" }));
  const dialog = await screen.findByRole("dialog", { name: "Release held assignments" });
  expect(dialog.textContent).toContain("3 assignments are held.");
  const howMany = screen.getByLabelText("How many");
  await user.clear(howMany);
  await user.type(howMany, "2");
  await user.click(screen.getByRole("button", { name: "Release" }));

  await waitFor(() => expect(success).toHaveBeenCalledWith("Released 2 assignments"));
  expect(releaseAssignments).toHaveBeenCalledExactlyOnceWith(RUN_ID, {
    limit: 2,
    assignment_type: null,
    assignment_ids: [],
  });
  expect(invalidated.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([
    runKeys.all,
    assignmentKeys.all,
  ]);
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

test("a release of one type sends that type, and one released reads in the singular", async () => {
  vi.mocked(releaseAssignments).mockResolvedValue([assignment(1)]);
  const { user } = mount(run("active", 1));

  await user.click(screen.getByRole("button", { name: "Release held (1)" }));
  const dialog = await screen.findByRole("dialog", { name: "Release held assignments" });
  expect(dialog.textContent).toContain("One assignment is held.");
  await user.click(screen.getByRole("combobox", { name: "Of type" }));
  await user.click(await screen.findByRole("option", { name: "Find sources" }));
  await user.click(screen.getByRole("button", { name: "Release" }));

  await waitFor(() => expect(success).toHaveBeenCalledWith("Released one assignment"));
  expect(releaseAssignments).toHaveBeenCalledExactlyOnceWith(RUN_ID, {
    limit: 1,
    assignment_type: "find_sources",
    assignment_ids: [],
  });
});

test("a release the API refuses stays open with the reason, and releases nothing", async () => {
  vi.mocked(releaseAssignments).mockRejectedValue(new ApiError(409, "Run is stopped"));
  const { invalidated, user } = mount(run("active", 3));

  await user.click(screen.getByRole("button", { name: "Release held (3)" }));
  await screen.findByRole("dialog");
  await user.click(screen.getByRole("button", { name: "Release" }));

  expect(await screen.findByText("Run is stopped")).toBeDefined();
  expect(screen.getByRole("dialog")).toBeDefined();
  expect(success).not.toHaveBeenCalled();
  expect(invalidated).not.toHaveBeenCalled();
});

test("a release of nothing is refused by the form before any request", async () => {
  const { user } = mount(run("active", 3));

  await user.click(screen.getByRole("button", { name: "Release held (3)" }));
  await screen.findByRole("dialog");
  const howMany = screen.getByLabelText("How many");
  await user.clear(howMany);
  await user.type(howMany, "0");
  await user.click(screen.getByRole("button", { name: "Release" }));

  expect(await screen.findByText("Release at least one")).toBeDefined();
  expect(releaseAssignments).not.toHaveBeenCalled();
});
