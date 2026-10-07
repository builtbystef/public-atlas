import type {
  AssignmentResult,
  AssignmentStatus,
  AssignmentType,
  EnteredBy,
  EntityKind,
  EntityStatus,
  EventKind,
  ReviewStatus,
  RunMode,
  RunStatus,
  SourceAccess,
} from "@public-atlas/api-client";

/**
 * What the console calls each value of the API's enums. The words are the
 * glossary's; the type names a country defines (`school_board`) have no
 * label here and go through `humanize`.
 */

export const assignmentTypes = [
  "find_homepage",
  "find_institutions",
  "find_sources",
] as const satisfies readonly AssignmentType[];

export const assignmentTypeLabels: Record<AssignmentType, string> = {
  find_homepage: "Find homepage",
  find_institutions: "Find institutions",
  find_sources: "Find sources",
};

export const assignmentStatuses = [
  "held",
  "queued",
  "running",
  "finished",
  "cancelled",
] as const satisfies readonly AssignmentStatus[];

export const assignmentStatusLabels: Record<AssignmentStatus, string> = {
  held: "Held",
  queued: "Queued",
  running: "Running",
  finished: "Finished",
  cancelled: "Cancelled",
};

export const assignmentResults = [
  "complete",
  "complete_with_gaps",
  "out_of_budget",
  "needs_review",
  "no_homepage",
  "failed",
] as const satisfies readonly AssignmentResult[];

export const assignmentResultLabels: Record<AssignmentResult, string> = {
  complete: "Complete",
  complete_with_gaps: "Complete with gaps",
  out_of_budget: "Out of budget",
  needs_review: "Needs review",
  no_homepage: "No homepage",
  failed: "Failed",
};

export const runStatusLabels: Record<RunStatus, string> = {
  active: "Active",
  paused: "Paused",
  stopped: "Stopped",
};

export const runModes = ["step", "auto"] as const satisfies readonly RunMode[];

export const runModeLabels: Record<RunMode, string> = {
  step: "Step: assignments wait to be released",
  auto: "Auto: assignments start as they are spawned",
};

export const runModeShortLabels: Record<RunMode, string> = { step: "Step", auto: "Auto" };

export const entityStatuses = [
  "verified",
  "candidate",
  "needs_review",
  "rejected",
] as const satisfies readonly EntityStatus[];

export const entityStatusLabels: Record<EntityStatus, string> = {
  candidate: "Candidate",
  verified: "Verified",
  rejected: "Rejected",
  needs_review: "Needs review",
};

export const entityKindLabels: Record<EntityKind, string> = {
  place: "Place",
  institution: "Institution",
  source: "Source",
  domain: "Domain",
  homepage: "Homepage",
};

export const reviewStatuses = [
  "open",
  "approved",
  "rejected",
  "merged",
] as const satisfies readonly ReviewStatus[];

export const reviewStatusLabels: Record<ReviewStatus, string> = {
  open: "Open",
  approved: "Approved",
  rejected: "Rejected",
  merged: "Merged",
};

/** The rules of review/service.py, in the order the queue shows them. */
export const reviewRules = [
  "type_level",
  "new_type",
  "name_pattern",
  "duplicate",
  "domain_checks",
  "domain_moved",
  "no_homepage",
  "gaps",
  "platform_source",
  "platform_homepage",
  "agent",
] as const;

export type ReviewRule = (typeof reviewRules)[number];

export const reviewRuleLabels: Record<ReviewRule, string> = {
  type_level: "Type at an unexpected level",
  new_type: "New institution type",
  name_pattern: "Name misses its pattern",
  duplicate: "Possible duplicate",
  domain_checks: "Domain checks failed",
  domain_moved: "Domain moved",
  no_homepage: "No homepage found",
  gaps: "Types still missing",
  platform_source: "Source on a platform",
  platform_homepage: "Homepage on a platform",
  agent: "The agent asked",
};

export const enteredByLabels: Record<EnteredBy, string> = {
  manual: "Manual",
  script: "Script",
  agent: "Agent",
};

export const sourceAccessLabels: Record<SourceAccess, string> = {
  public: "Public",
  login: "Behind a login",
};

export const eventKindLabels: Record<EventKind, string> = {
  prompt: "Prompt",
  text: "Model",
  tool_call: "Tool call",
  tool_result: "Tool result",
  video: "Video",
};

/** "school_board" as "School board": for the type names the country tables define. */
export function humanize(name: string): string {
  const words = name.replaceAll("_", " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The label of a value that may be outside the map (a rule the console does not know yet). */
export function labelOf<K extends string>(labels: Record<K, string>, value: string): string {
  return value in labels ? labels[value as K] : humanize(value);
}
