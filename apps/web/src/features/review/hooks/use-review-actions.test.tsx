// @vitest-environment jsdom
import type { ReviewItemOutput, ReviewRow, SpawnOutput } from "@public-atlas/api-client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { toast } from "sonner";
import { afterEach, expect, test, vi } from "vite-plus/test";

import { assignmentKeys } from "@/features/assignments/queries";
import { graphKeys } from "@/features/graph/queries";
import { runKeys } from "@/features/runs/queries";
import { ApiError } from "@/lib/api/errors";

import {
  approveReviewItem,
  approveReviewKind,
  mergeReviewItem,
  rejectReviewItem,
  rejectReviewKind,
} from "../mutations";
import { reviewKeys } from "../queries";
import { useReviewActions, type DecisionTarget } from "./use-review-actions";

// The API calls, as fakes that answer what the API would; nothing leaves the test.
vi.mock("../mutations", () => ({
  approveReviewItem: vi.fn<typeof approveReviewItem>(),
  rejectReviewItem: vi.fn<typeof rejectReviewItem>(),
  mergeReviewItem: vi.fn<typeof mergeReviewItem>(),
  approveReviewKind: vi.fn<typeof approveReviewKind>(),
  rejectReviewKind: vi.fn<typeof rejectReviewKind>(),
}));

const ITEM_ID = "0199e8b0-0000-7000-8000-00000000000e";
const ENTITY_ID = "0199e8b0-0000-7000-8000-000000000001";
const INTO_ID = "0199e8b0-0000-7000-8000-000000000002";

const target: DecisionTarget = {
  id: ITEM_ID,
  label: "Oakville Library",
  entity_kind: "institution",
  entity_id: ENTITY_ID,
  kind: null,
};

const row: ReviewRow & { kind: string } = {
  id: "new_type:conservation_authority",
  kind: "new_type:conservation_authority",
  rule: "new_type",
  status: "open",
  question: { suggested_type: "conservation_authority" },
  count: 2,
  raised_at: "2026-10-01T00:00:00Z",
  decided_at: null,
  members: [
    {
      id: ITEM_ID,
      entity_id: ENTITY_ID,
      entity_kind: "institution",
      label: "Halton Conservation",
      country_code: "CA",
      reasons: [],
      raised_at: "2026-10-01T00:00:00Z",
      raised_by_assignment_id: null,
    },
    {
      id: "0199e8b0-0000-7000-8000-00000000000f",
      entity_id: "0199e8b0-0000-7000-8000-000000000003",
      entity_kind: "institution",
      label: "Credit Valley Conservation",
      country_code: "CA",
      reasons: [],
      raised_at: "2026-10-01T00:00:00Z",
      raised_by_assignment_id: null,
    },
  ],
  item_ids: [ITEM_ID, "0199e8b0-0000-7000-8000-00000000000f"],
};

function decided(id: string, status: ReviewItemOutput["status"]): ReviewItemOutput {
  return {
    id,
    entity_id: ENTITY_ID,
    rule: "agent",
    question: {},
    kind: null,
    status,
    raised_by_assignment_id: null,
    decided_at: "2026-10-02T00:00:00Z",
    note: null,
  };
}

const spawned: SpawnOutput[] = [
  { type: "find_sources", subject_id: ENTITY_ID },
  { type: "find_homepage", subject_id: ENTITY_ID },
  { type: "find_sources", subject_id: "0199e8b0-0000-7000-8000-000000000003" },
];

/** A queue page: a button per decision, and the dialog the hook renders. */
function Page() {
  const actions = useReviewActions();
  return (
    <>
      <button onClick={() => actions.approve(target)}>approve</button>
      <button onClick={() => actions.reject(target)}>reject</button>
      <button onClick={() => actions.merge(target)}>merge</button>
      <button onClick={() => actions.merge(target, INTO_ID)}>merge into</button>
      <button onClick={() => actions.approveAll(row)}>approve all</button>
      <button onClick={() => actions.rejectAll(row)}>reject all</button>
      {actions.dialog}
    </>
  );
}

function mount() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidated = vi.spyOn(queryClient, "invalidateQueries");
  render(
    <QueryClientProvider client={queryClient}>
      <Page />
    </QueryClientProvider>,
  );
  return { invalidated, user: userEvent.setup() };
}

const success = vi.spyOn(toast, "success");

const ALL_FOUR = [reviewKeys.all, graphKeys.all, assignmentKeys.all, runKeys.all];

afterEach(() => {
  vi.clearAllMocks();
});

test("an approval with the type left blank sends a null type, names the work spawned, and refreshes the four query families", async () => {
  vi.mocked(approveReviewItem).mockResolvedValue({
    review_item: decided(ITEM_ID, "approved"),
    spawn: spawned,
    assignment_ids: [],
  });
  const { invalidated, user } = mount();

  await user.click(screen.getByRole("button", { name: "approve" }));
  const dialog = await screen.findByRole("dialog", { name: "Approve this institution" });
  expect(dialog.textContent).toContain("Oakville Library");
  expect(screen.getByLabelText("Institution type")).toHaveProperty("value", "");
  await user.click(screen.getByRole("button", { name: "Approve" }));

  await waitFor(() =>
    expect(success).toHaveBeenCalledWith("Approved; spawned 2 Find sources, 1 Find homepage"),
  );
  expect(approveReviewItem).toHaveBeenCalledExactlyOnceWith(ITEM_ID, {
    note: null,
    institution_type: null,
  });
  expect(invalidated.mock.calls.map(([filters]) => filters?.queryKey)).toEqual(ALL_FOUR);
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

test("an approval with a type and a note sends both, and a decision that spawns nothing says only the verb", async () => {
  vi.mocked(approveReviewItem).mockResolvedValue({
    review_item: decided(ITEM_ID, "approved"),
    spawn: [],
    assignment_ids: [],
  });
  const { user } = mount();

  await user.click(screen.getByRole("button", { name: "approve" }));
  await screen.findByRole("dialog");
  await user.type(screen.getByLabelText("Institution type"), "school_board");
  await user.type(screen.getByLabelText("Note (optional)"), "A board, not a school");
  await user.click(screen.getByRole("button", { name: "Approve" }));

  await waitFor(() => expect(success).toHaveBeenCalledWith("Approved"));
  expect(approveReviewItem).toHaveBeenCalledExactlyOnceWith(ITEM_ID, {
    note: "A board, not a school",
    institution_type: "school_board",
  });
});

test("a type that is not a type name is refused by the form before any request", async () => {
  const { user } = mount();

  await user.click(screen.getByRole("button", { name: "approve" }));
  await screen.findByRole("dialog");
  await user.type(screen.getByLabelText("Institution type"), "School Board");
  await user.click(screen.getByRole("button", { name: "Approve" }));

  expect(
    await screen.findByText("Lowercase letters, digits and underscores, starting with a letter"),
  ).toBeDefined();
  expect(approveReviewItem).not.toHaveBeenCalled();
  expect(success).not.toHaveBeenCalled();
});

test("a rejection sends the note alone", async () => {
  vi.mocked(rejectReviewItem).mockResolvedValue({
    review_item: decided(ITEM_ID, "rejected"),
    spawn: [{ type: "find_homepage", subject_id: ENTITY_ID }],
    assignment_ids: [],
  });
  const { invalidated, user } = mount();

  await user.click(screen.getByRole("button", { name: "reject" }));
  await screen.findByRole("dialog", { name: "Reject this institution" });
  expect(screen.queryByLabelText("Institution type")).toBeNull();
  await user.type(screen.getByLabelText("Note (optional)"), "  ");
  await user.click(screen.getByRole("button", { name: "Reject" }));

  await waitFor(() => expect(success).toHaveBeenCalledWith("Rejected; spawned 1 Find homepage"));
  expect(rejectReviewItem).toHaveBeenCalledExactlyOnceWith(ITEM_ID, { note: null });
  expect(invalidated.mock.calls.map(([filters]) => filters?.queryKey)).toEqual(ALL_FOUR);
});

test("a merge into the entity the question named sends that id", async () => {
  vi.mocked(mergeReviewItem).mockResolvedValue({
    review_item: decided(ITEM_ID, "merged"),
    spawn: [],
    assignment_ids: [],
  });
  const { invalidated, user } = mount();

  await user.click(screen.getByRole("button", { name: "merge into" }));
  await screen.findByRole("dialog", { name: "Merge this institution" });
  await user.click(screen.getByRole("button", { name: "Merge" }));

  await waitFor(() => expect(success).toHaveBeenCalledWith("Merged"));
  expect(mergeReviewItem).toHaveBeenCalledExactlyOnceWith(ITEM_ID, {
    note: null,
    into_id: INTO_ID,
  });
  expect(invalidated.mock.calls.map(([filters]) => filters?.queryKey)).toEqual(ALL_FOUR);
});

test("a merge never posts an empty into_id", async () => {
  const { user } = mount();

  await user.click(screen.getByRole("button", { name: "merge" }));
  await screen.findByRole("dialog", { name: "Merge this institution" });
  await user.click(screen.getByRole("button", { name: "Merge" }));

  expect(await screen.findByText("Choose what to merge into")).toBeDefined();
  expect(mergeReviewItem).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog")).toBeDefined();
});

test("approving a row gives its bodies the type the question suggested, and counts the items", async () => {
  vi.mocked(approveReviewKind).mockResolvedValue({
    kind: row.kind,
    review_items: row.item_ids.map((id) => decided(id, "approved")),
    spawn: spawned,
    assignment_ids: [],
  });
  const { invalidated, user } = mount();

  await user.click(screen.getByRole("button", { name: "approve all" }));
  const dialog = await screen.findByRole("dialog", { name: "Approve all 2 institutions" });
  expect(dialog.textContent).toContain(
    "Is “conservation_authority” a type the country should have?",
  );
  expect(dialog.textContent).toContain("Halton Conservation");
  expect(dialog.textContent).toContain("Credit Valley Conservation");
  expect(screen.getByLabelText("Institution type")).toHaveProperty(
    "value",
    "conservation_authority",
  );
  await user.click(screen.getByRole("button", { name: "Approve 2" }));

  await waitFor(() =>
    expect(success).toHaveBeenCalledWith(
      "Approved 2 items; spawned 2 Find sources, 1 Find homepage",
    ),
  );
  expect(approveReviewKind).toHaveBeenCalledExactlyOnceWith({
    kind: "new_type:conservation_authority",
    item_ids: row.item_ids,
    note: null,
    institution_type: "conservation_authority",
  });
  expect(invalidated.mock.calls.map(([filters]) => filters?.queryKey)).toEqual(ALL_FOUR);
});

test("rejecting a row sends its kind and items, and lists the members it changes", async () => {
  vi.mocked(rejectReviewKind).mockResolvedValue({
    kind: row.kind,
    review_items: row.item_ids.map((id) => decided(id, "rejected")),
    spawn: [],
    assignment_ids: [],
  });
  const { user } = mount();

  await user.click(screen.getByRole("button", { name: "reject all" }));
  await screen.findByRole("dialog", { name: "Reject all 2 institutions" });
  expect(screen.queryByLabelText("Institution type")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Reject 2" }));

  await waitFor(() => expect(success).toHaveBeenCalledWith("Rejected 2 items"));
  expect(rejectReviewKind).toHaveBeenCalledExactlyOnceWith({
    kind: "new_type:conservation_authority",
    item_ids: row.item_ids,
    note: null,
  });
});

test("a decision the API refuses stays open with the reason and refreshes nothing", async () => {
  vi.mocked(approveReviewItem).mockRejectedValue(new ApiError(409, "The item was decided already"));
  const { invalidated, user } = mount();

  await user.click(screen.getByRole("button", { name: "approve" }));
  await screen.findByRole("dialog");
  await user.click(screen.getByRole("button", { name: "Approve" }));

  expect(await screen.findByText("The item was decided already")).toBeDefined();
  expect(screen.getByRole("dialog")).toBeDefined();
  expect(success).not.toHaveBeenCalled();
  expect(invalidated).not.toHaveBeenCalled();
});

test("closing the dialog decides nothing", async () => {
  const { user } = mount();

  await user.click(screen.getByRole("button", { name: "reject" }));
  await screen.findByRole("dialog");
  await user.click(screen.getByRole("button", { name: "Cancel" }));

  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(rejectReviewItem).not.toHaveBeenCalled();
});
