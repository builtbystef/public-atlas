import type {
  DecisionPreviewOutput,
  PlannedOutput,
  StatusChangeOutput,
} from "@public-atlas/api-client";

import { assignmentTypeLabels } from "@/lib/labels";

import { entityCount } from "./question";

/** A decision's preview in plain sentences. */
export interface Effects {
  /** What changes in the graph. */
  changes: string[];
  /** The work that starts. */
  starts: string[];
  /** The work asked for that will not start, and why. */
  held: string[];
}

// More entities than this of one kind, or of one piece of work, read as a count.
const NAMED = 3;

function groupBy<T>(items: T[], key: (item: T) => string): T[][] {
  const groups = new Map<string, T[]>();
  for (const item of items) groups.set(key(item), [...(groups.get(key(item)) ?? []), item]);
  return [...groups.values()];
}

function changeText(change: StatusChangeOutput): string {
  const { label, entity_kind: kind } = change.entity;
  switch (change.after) {
    case "verified":
      if (kind === "domain") return `${label} becomes a trusted domain`;
      if (kind === "homepage") return `${label} becomes a verified homepage`;
      return `${label} becomes verified`;
    case "rejected":
      return `${label} is rejected`;
    case "needs_review":
      return `${label} goes to review`;
    case "candidate":
      return `${label} becomes a candidate again`;
  }
}

function changesText(group: StatusChangeOutput[]): string[] {
  const [first] = group;
  if (!first || group.length <= NAMED) return group.map(changeText);
  const many = entityCount(group.length, first.entity.entity_kind);
  switch (first.after) {
    case "verified":
      return [
        first.entity.entity_kind === "domain"
          ? `${group.length} domains become trusted`
          : `${many} become verified`,
      ];
    case "rejected":
      return [`${many} are rejected`];
    default:
      return group.map(changeText);
  }
}

/** "Find homepage for Oakville Library", or "Find homepage for 40 institutions". */
function workText(group: PlannedOutput[]): string[] {
  const [first] = group;
  if (!first) return [];
  const type = assignmentTypeLabels[first.type];
  if (group.length <= NAMED) return group.map((one) => `${type} for ${one.subject.label}`);
  return [`${type} for ${entityCount(group.length, first.subject.entity_kind)}`];
}

const HELD_BECAUSE: Record<NonNullable<PlannedOutput["skipped"]>, string> = {
  already_open: "is under way already",
  out_of_scope: "is outside the run's filter, so it won't start",
  no_run: "waits for the next run of the country, since none is going",
  run_stopped: "won't start, since the run is stopped",
};

/**
 * What a preview says, as sentences: the status changes, the work that
 * starts, and the work that won't. The entity a merge folds away reads as
 * merged, not rejected, which is how the merge records it.
 */
export function describeEffects(
  preview: DecisionPreviewOutput,
  merged?: { id: string; into: string },
): Effects {
  const mergedAway = preview.changes.filter((change) => change.entity.id === merged?.id);
  const others = preview.changes.filter((change) => change.entity.id !== merged?.id);
  const starting = preview.spawn.filter((planned) => planned.skipped === null);
  const held = preview.spawn.filter((planned) => planned.skipped !== null);
  return {
    changes: [
      ...mergedAway.map((change) => `${change.entity.label} is merged into ${merged?.into}`),
      ...groupBy(others, (change) => `${change.after}:${change.entity.entity_kind}`).flatMap(
        changesText,
      ),
    ],
    starts: groupBy(starting, (planned) => planned.type).flatMap(workText),
    held: groupBy(held, (planned) => `${planned.skipped}:${planned.type}`).flatMap((group) =>
      workText(group).map((work) => `${work} ${HELD_BECAUSE[group[0]?.skipped ?? "no_run"]}`),
    ),
  };
}
