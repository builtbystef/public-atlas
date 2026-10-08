import type { EntityKind, ReviewItemDetail, ReviewRow } from "@public-atlas/api-client";

import { entityKindLabels, humanize } from "@/lib/labels";

/**
 * The question the items of a kind ask, as a sentence, from the facts they
 * share; null for a rule whose items each ask their own.
 */
export function questionText(rule: string, question: Record<string, unknown>): string | null {
  const type = question["institution_type"];
  const level = question["level"];
  const suggested = question["suggested_type"];
  if (rule === "type_level" && typeof type === "string" && typeof level === "string") {
    return `Does a ${humanize(type).toLowerCase()} belong under a ${humanize(level).toLowerCase()}?`;
  }
  if (rule === "new_type" && typeof suggested === "string") {
    return `Is “${suggested}” a type the country should have?`;
  }
  return null;
}

/** "1 institution", "40 institutions". */
export function entityCount(count: number, kind: EntityKind): string {
  const noun = entityKindLabels[kind].toLowerCase();
  return `${count} ${count === 1 ? noun : `${noun}s`}`;
}

/**
 * The other open items of a question, from an item of it: "1 more
 * institution asks the same question", or, once the item is decided, "3
 * institutions still ask the same question".
 */
export function othersAsking(count: number, kind: EntityKind, open: boolean): string {
  const [number, ...noun] = entityCount(count, kind).split(" ");
  const verb = count === 1 ? "asks" : "ask";
  return open
    ? `${number} more ${noun.join(" ")} ${verb} the same question.`
    : `${number} ${noun.join(" ")} still ${verb} the same question.`;
}

/** A row that decides several items at once. */
export function isGroup(row: ReviewRow): row is ReviewRow & { kind: string } {
  return row.kind !== null && row.count > 1;
}

/** The first names of a row and how many more there are: "Elm, Oak and 38 more". */
export function memberSummary(row: ReviewRow, shown = 3): string {
  const names = row.members.slice(0, shown).map((member) => member.label);
  const more = row.count - names.length;
  return more > 0 ? `${names.join(", ")} and ${more} more` : names.join(", ");
}

/** "a", "a or b", "a, b or c". */
function listOf(words: string[], last: "and" | "or"): string {
  if (words.length <= 1) return words.join("");
  return `${words.slice(0, -1).join(", ")} ${last} ${words.at(-1)}`;
}

function typeWords(name: unknown): string | null {
  return typeof name === "string" ? humanize(name).toLowerCase() : null;
}

/**
 * The question one item asks, as a sentence about its entity and the
 * entities its question names; null when only the reasons can say it, as
 * when the agent asked.
 */
export function itemQuestion(item: ReviewItemDetail): string | null {
  const shared = questionText(item.rule, item.question);
  if (shared) return shared;
  const { label, subject, question } = item;
  const owner = subject.owner?.label;
  const platform = typeof question["platform"] === "string" ? question["platform"] : null;
  switch (item.rule) {
    case "duplicate": {
      const matches = item.related
        .filter((related) => related.fact === "duplicate_of")
        .map((related) => `“${related.entity.label}”`);
      if (matches.length === 0) return `Is “${label}” a duplicate?`;
      // More than two names make a sentence too long to read; the comparison names them.
      return matches.length > 2
        ? `Is “${label}” the same as one of ${entityCount(matches.length, item.entity_kind)} already saved?`
        : `Is “${label}” the same as ${listOf(matches, "or")}?`;
    }
    case "name_pattern": {
      const type = typeWords(question["institution_type"] ?? subject.institution_type);
      return type
        ? `Is “${label}” a ${type}, though its name misses the pattern?`
        : `Is “${label}” named as it should be?`;
    }
    case "domain_checks":
      return owner
        ? `Is ${label} an official domain of ${owner}?`
        : `Is ${label} an official domain?`;
    case "domain_moved":
      return owner ? `Is ${label} the homepage of ${owner}?` : `Is ${label} a homepage to keep?`;
    case "platform_homepage":
      return `Is this page${platform ? ` on ${platform}` : ""} the homepage of ${owner ?? "the institution"}?`;
    case "platform_source": {
      const type = typeWords(question["source_type"]) ?? "page";
      return `Is this ${type}${platform ? ` on ${platform}` : ""} published by ${owner ?? "the institution"}?`;
    }
    case "no_homepage":
      return `Does ${label} have a homepage the searches missed?`;
    case "gaps": {
      const missing = question["types_missing"];
      const types = Array.isArray(missing)
        ? missing.map(typeWords).filter((type) => type !== null)
        : [];
      return types.length > 0
        ? `Does ${label} really have no ${listOf(types, "or")}?`
        : `Is anything missing from ${label}?`;
    }
    default:
      return null;
  }
}

/** The entity in words, for a title: "the tender source of Moss Park Arena". */
export function subjectWords(item: ReviewItemDetail): string {
  const owner = item.subject.owner?.label;
  switch (item.entity_kind) {
    case "source": {
      const type = typeWords(item.entity["source_type"]) ?? "";
      return owner ? `the ${type} source of ${owner}`.replace("  ", " ") : item.label;
    }
    case "homepage":
      return owner ? `the homepage claim of ${owner}` : item.label;
    case "domain":
      return item.label;
    default:
      return `“${item.label}”`;
  }
}

/** The page's title: the question, else what the item is about. */
export function itemTitle(item: ReviewItemDetail): string {
  const question = itemQuestion(item);
  if (question) return question;
  const about = subjectWords(item);
  return item.rule === "agent"
    ? `The agent asks about ${about}`
    : `${about.charAt(0).toUpperCase()}${about.slice(1)}`;
}
