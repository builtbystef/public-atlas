import type {
  ApproveInput,
  DecisionInput,
  DecisionOutput,
  KindApproveInput,
  KindDecisionInput,
  KindDecisionOutput,
  MergeInput,
} from "@public-atlas/api-client";

import { browserApi } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";

const path = (id: string) => ({ params: { path: { review_item_id: id } } });

export async function approveReviewItem(id: string, body: ApproveInput): Promise<DecisionOutput> {
  return unwrap(
    await browserApi.POST("/review-items/{review_item_id}/approve", { ...path(id), body }),
  );
}

export async function rejectReviewItem(id: string, body: DecisionInput): Promise<DecisionOutput> {
  return unwrap(
    await browserApi.POST("/review-items/{review_item_id}/reject", { ...path(id), body }),
  );
}

/** Folds the item's entity into another, moving its names, evidence and claims. */
export async function mergeReviewItem(id: string, body: MergeInput): Promise<DecisionOutput> {
  return unwrap(
    await browserApi.POST("/review-items/{review_item_id}/merge", { ...path(id), body }),
  );
}

export async function approveReviewKind(body: KindApproveInput): Promise<KindDecisionOutput> {
  return unwrap(await browserApi.POST("/review-items/kinds/approve", { body }));
}

export async function rejectReviewKind(body: KindDecisionInput): Promise<KindDecisionOutput> {
  return unwrap(await browserApi.POST("/review-items/kinds/reject", { body }));
}
