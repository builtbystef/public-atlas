"use client";

import type {
  DecisionOutput,
  EntityKind,
  KindDecisionOutput,
  ReviewRow,
  SpawnOutput,
} from "@public-atlas/api-client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { assignmentKeys } from "@/features/assignments/queries";
import { graphKeys } from "@/features/graph/queries";
import { runKeys } from "@/features/runs/queries";
import { assignmentTypeLabels, entityKindLabels, humanize, labelOf } from "@/lib/labels";
import { TYPE_NAME } from "@/lib/validation";

import { DecisionDialog } from "../components/decision-dialog";
import { DecisionEffects } from "../components/decision-effects";
import { MergeDialog } from "../components/merge-dialog";
import {
  approveReviewItem,
  approveReviewKind,
  mergeReviewItem,
  rejectReviewItem,
  rejectReviewKind,
} from "../mutations";
import { entityCount, questionText } from "../question";
import { reviewKeys } from "../queries";
import { kindTypeName } from "../schemas";

/** What a decision on one item needs to know of it. */
export interface DecisionTarget {
  id: string;
  label: string;
  entity_kind: EntityKind;
  entity_id: string;
  /** The question the item shares with others, for the type an approval suggests. */
  kind?: string | null;
}

type Pending =
  | { what: "approve"; item: DecisionTarget }
  | { what: "reject"; item: DecisionTarget }
  | { what: "merge"; item: DecisionTarget; intoId?: string | undefined }
  | { what: "approve-all"; row: ReviewRow & { kind: string } }
  | { what: "reject-all"; row: ReviewRow & { kind: string } };

/** A type as typed, when it is a type name; the field's own validation says what is wrong. */
function typeOrNull(typed: string): string | null {
  return TYPE_NAME.test(typed) ? typed : null;
}

function spawnSummary(spawn: SpawnOutput[]): string {
  if (spawn.length === 0) return "";
  const counts = new Map<string, number>();
  for (const s of spawn) counts.set(s.type, (counts.get(s.type) ?? 0) + 1);
  return [...counts.entries()]
    .map(([type, n]) => `${n} ${labelOf(assignmentTypeLabels, type)}`)
    .join(", ");
}

/** The entities a decision on a whole row changes, for its dialog. */
function RowMembers({ row }: { row: ReviewRow }) {
  const more = row.count - row.members.length;
  return (
    <ul className="flex max-h-44 flex-col divide-y overflow-y-auto rounded-lg border text-sm">
      {row.members.map((member) => (
        <li key={member.id} className="truncate px-3 py-1.5" title={member.label}>
          {member.label}
        </li>
      ))}
      {more > 0 && <li className="px-3 py-1.5 text-muted-foreground">and {more} more</li>}
    </ul>
  );
}

/**
 * The decisions of spec section 6.5: approve, reject or merge one item, and
 * approve or reject every item of a row that asks one question for several.
 * Each opens a dialog for the note; render `dialog` once near the list.
 */
export function useReviewActions(): {
  approve: (item: DecisionTarget) => void;
  reject: (item: DecisionTarget) => void;
  /** `intoId` picks the entity to merge into, such as a duplicate the question names. */
  merge: (item: DecisionTarget, intoId?: string) => void;
  approveAll: (row: ReviewRow & { kind: string }) => void;
  rejectAll: (row: ReviewRow & { kind: string }) => void;
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

  const row = useMutation({
    mutationFn: async ({
      pending,
      values,
    }: {
      pending: Pending;
      values: { note: string | null; institution_type?: string | null };
    }): Promise<KindDecisionOutput> => {
      switch (pending.what) {
        case "approve-all":
          return approveReviewKind({
            kind: pending.row.kind,
            item_ids: pending.row.item_ids,
            note: values.note,
            institution_type: values.institution_type ?? null,
          });
        case "reject-all":
          return rejectReviewKind({
            kind: pending.row.kind,
            item_ids: pending.row.item_ids,
            note: values.note,
          });
        default:
          throw new Error("not a decision on a row");
      }
    },
    onSuccess: (result, { pending }) =>
      decided(
        `${pending.what === "approve-all" ? "Approved" : "Rejected"} ${result.review_items.length} items`,
        result.spawn,
      ),
  });

  let dialog: ReactNode = null;
  if (pending) {
    switch (pending.what) {
      case "approve": {
        const institution = pending.item.entity_kind === "institution";
        const kind = pending.item.kind;
        dialog = (
          <DecisionDialog
            open
            onOpenChange={close}
            title={`Approve this ${entityKindLabels[pending.item.entity_kind].toLowerCase()}`}
            subject={pending.item.label}
            description="It is what the agent said it is."
            confirmLabel="Approve"
            typeField={
              institution
                ? {
                    initial: kind?.startsWith("new_type:") ? kindTypeName(kind) : "",
                    description:
                      "Give the type when the body was saved as “other”; leave empty to keep it.",
                  }
                : undefined
            }
            preview={({ institution_type }) => {
              const type = typeOrNull(institution_type);
              return (
                <DecisionEffects
                  tone="approve"
                  request={{
                    decision: "approve",
                    id: pending.item.id,
                    body: { institution_type: type },
                  }}
                  extra={type ? [`Its type becomes ${humanize(type).toLowerCase()}`] : []}
                />
              );
            }}
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
            title={`Reject this ${entityKindLabels[pending.item.entity_kind].toLowerCase()}`}
            subject={pending.item.label}
            description="It is not what the agent said, and the agent will not save it again."
            confirmLabel="Reject"
            destructive
            preview={() => (
              <DecisionEffects
                tone="reject"
                request={{ decision: "reject", id: pending.item.id, body: {} }}
              />
            )}
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
            initialIntoId={pending.intoId}
            preview={(into) => (
              <DecisionEffects
                tone="merge"
                request={{ decision: "merge", id: pending.item.id, body: { into_id: into.id } }}
                merged={{ id: pending.item.entity_id, into: into.name }}
              />
            )}
            onConfirm={(values) => item.mutateAsync({ pending, values })}
          />
        );
        break;
      case "approve-all":
      case "reject-all": {
        const target = pending.row;
        const approving = pending.what === "approve-all";
        const what = entityCount(target.count, target.members[0]?.entity_kind ?? "institution");
        const question = questionText(target.rule, target.question);
        dialog = (
          <DecisionDialog
            open
            onOpenChange={close}
            title={`${approving ? "Approve" : "Reject"} all ${what}`}
            subject={question}
            description={
              approving
                ? "Each of these is what the agent said it is."
                : "None of these is what the agent said, and the agent will not save them again."
            }
            details={<RowMembers row={target} />}
            confirmLabel={`${approving ? "Approve" : "Reject"} ${target.count}`}
            destructive={!approving}
            typeField={
              approving && target.rule === "new_type"
                ? {
                    initial: kindTypeName(target.kind),
                    description:
                      "The type these bodies get. It must be one of the country's types.",
                  }
                : undefined
            }
            preview={({ institution_type }) => {
              const body = { kind: target.kind, item_ids: target.item_ids };
              const type = target.rule === "new_type" ? typeOrNull(institution_type) : null;
              return approving ? (
                <DecisionEffects
                  tone="approve"
                  request={{ decision: "approve-all", body: { ...body, institution_type: type } }}
                  extra={type ? [`Their type becomes ${humanize(type).toLowerCase()}`] : []}
                />
              ) : (
                <DecisionEffects tone="reject" request={{ decision: "reject-all", body }} />
              );
            }}
            onConfirm={(values) => row.mutateAsync({ pending, values })}
          />
        );
        break;
      }
      default:
        break;
    }
  }

  return {
    approve: (target) => setPending({ what: "approve", item: target }),
    reject: (target) => setPending({ what: "reject", item: target }),
    merge: (target, intoId) => setPending({ what: "merge", item: target, intoId }),
    approveAll: (target) => setPending({ what: "approve-all", row: target }),
    rejectAll: (target) => setPending({ what: "reject-all", row: target }),
    dialog,
  };
}
