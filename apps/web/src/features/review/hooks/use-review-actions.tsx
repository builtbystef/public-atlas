"use client";

import type {
  DecisionOutput,
  KindDecisionOutput,
  KindOutput,
  ReviewItemDetail,
  ReviewItemRow,
  SpawnOutput,
} from "@public-atlas/api-client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { assignmentKeys } from "@/features/assignments/queries";
import { graphKeys } from "@/features/graph/queries";
import { runKeys } from "@/features/runs/queries";
import { assignmentTypeLabels, labelOf } from "@/lib/labels";

import { DecisionDialog } from "../components/decision-dialog";
import { MergeDialog } from "../components/merge-dialog";
import {
  approveReviewItem,
  approveReviewKind,
  mergeReviewItem,
  rejectReviewItem,
  rejectReviewKind,
} from "../mutations";
import { reviewKeys } from "../queries";
import { kindTypeName } from "../schemas";

type Item = ReviewItemRow | ReviewItemDetail;

type Pending =
  | { what: "approve"; item: Item }
  | { what: "reject"; item: Item }
  | { what: "merge"; item: Item }
  | { what: "approve-kind"; kind: KindOutput }
  | { what: "reject-kind"; kind: KindOutput };

function spawnSummary(spawn: SpawnOutput[]): string {
  if (spawn.length === 0) return "";
  const counts = new Map<string, number>();
  for (const s of spawn) counts.set(s.type, (counts.get(s.type) ?? 0) + 1);
  return [...counts.entries()]
    .map(([type, n]) => `${n} ${labelOf(assignmentTypeLabels, type)}`)
    .join(", ");
}

/**
 * The decisions of spec section 6.5: approve, reject or merge one item, and
 * approve or reject every item of a kind at once. Each opens a dialog for
 * the note; render `dialog` once near the list.
 */
export function useReviewActions(): {
  approve: (item: Item) => void;
  reject: (item: Item) => void;
  merge: (item: Item) => void;
  approveKind: (kind: KindOutput) => void;
  rejectKind: (kind: KindOutput) => void;
  dialog: ReactNode;
} {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<Pending | null>(null);
  const close = (open: boolean) => {
    if (!open) setPending(null);
  };

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: reviewKeys.all }),
      queryClient.invalidateQueries({ queryKey: graphKeys.all }),
      queryClient.invalidateQueries({ queryKey: assignmentKeys.all }),
      queryClient.invalidateQueries({ queryKey: runKeys.all }),
    ]);
  };

  const decided = async (verb: string, spawn: SpawnOutput[]) => {
    const summary = spawnSummary(spawn);
    toast.success(summary ? `${verb}; spawned ${summary}` : verb);
    await invalidate();
  };

  const item = useMutation({
    mutationFn: async ({
      pending,
      values,
    }: {
      pending: Pending;
      values: { note: string | null; institution_type?: string | null; into_id?: string };
    }): Promise<DecisionOutput> => {
      switch (pending.what) {
        case "approve":
          return approveReviewItem(pending.item.id, {
            note: values.note,
            institution_type: values.institution_type ?? null,
          });
        case "reject":
          return rejectReviewItem(pending.item.id, { note: values.note });
        case "merge":
          return mergeReviewItem(pending.item.id, {
            note: values.note,
            into_id: values.into_id ?? "",
          });
        default:
          throw new Error("not an item decision");
      }
    },
    onSuccess: (result, { pending }) =>
      decided(
        { approve: "Approved", reject: "Rejected", merge: "Merged" }[
          pending.what as "approve" | "reject" | "merge"
        ],
        result.spawn,
      ),
  });

  const kind = useMutation({
    mutationFn: async ({
      pending,
      values,
    }: {
      pending: Pending;
      values: { note: string | null; institution_type?: string | null };
    }): Promise<KindDecisionOutput> => {
      switch (pending.what) {
        case "approve-kind":
          return approveReviewKind({
            kind: pending.kind.kind,
            note: values.note,
            institution_type: values.institution_type ?? null,
          });
        case "reject-kind":
          return rejectReviewKind({ kind: pending.kind.kind, note: values.note });
        default:
          throw new Error("not a kind decision");
      }
    },
    onSuccess: (result, { pending }) =>
      decided(
        `${pending.what === "approve-kind" ? "Approved" : "Rejected"} ${result.review_items.length} items`,
        result.spawn,
      ),
  });

  let dialog: ReactNode = null;
  if (pending) {
    switch (pending.what) {
      case "approve": {
        const institution = pending.item.entity_kind === "institution";
        dialog = (
          <DecisionDialog
            open
            onOpenChange={close}
            title={`Approve “${pending.item.label}”`}
            description="Verifies the entity and spawns what follows from it."
            confirmLabel="Approve"
            typeField={
              institution
                ? {
                    initial: "",
                    description:
                      "Give the type when the body was saved as “other”; leave empty to keep it.",
                  }
                : undefined
            }
            onConfirm={(values) => item.mutateAsync({ pending, values })}
          />
        );
        break;
      }
      case "reject":
        dialog = (
          <DecisionDialog
            open
            onOpenChange={close}
            title={`Reject “${pending.item.label}”`}
            description="Marks the entity rejected; the agent will not save it again."
            confirmLabel="Reject"
            destructive
            onConfirm={(values) => item.mutateAsync({ pending, values })}
          />
        );
        break;
      case "merge":
        dialog = (
          <MergeDialog
            open
            onOpenChange={close}
            label={pending.item.label}
            entityKind={pending.item.entity_kind}
            onConfirm={(values) => item.mutateAsync({ pending, values })}
          />
        );
        break;
      case "approve-kind":
        dialog = (
          <DecisionDialog
            open
            onOpenChange={close}
            title="Approve the whole kind"
            description={`Verifies all ${pending.kind.count} entities that raised this question.`}
            confirmLabel={`Approve ${pending.kind.count}`}
            typeField={
              pending.kind.rule === "new_type"
                ? {
                    initial: kindTypeName(pending.kind.kind),
                    description: "The type these bodies get. It is added to the country's types.",
                  }
                : undefined
            }
            onConfirm={(values) => kind.mutateAsync({ pending, values })}
          />
        );
        break;
      case "reject-kind":
        dialog = (
          <DecisionDialog
            open
            onOpenChange={close}
            title="Reject the whole kind"
            description={`Rejects all ${pending.kind.count} entities that raised this question.`}
            confirmLabel={`Reject ${pending.kind.count}`}
            destructive
            onConfirm={(values) => kind.mutateAsync({ pending, values })}
          />
        );
        break;
      default:
        break;
    }
  }

  return {
    approve: (target) => setPending({ what: "approve", item: target }),
    reject: (target) => setPending({ what: "reject", item: target }),
    merge: (target) => setPending({ what: "merge", item: target }),
    approveKind: (target) => setPending({ what: "approve-kind", kind: target }),
    rejectKind: (target) => setPending({ what: "reject-kind", kind: target }),
    dialog,
  };
}
