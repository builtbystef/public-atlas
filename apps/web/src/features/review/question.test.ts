import type { EntitySummaryOutput, ReviewItemDetail } from "@public-atlas/api-client";
import { expect, test } from "vite-plus/test";

import { itemQuestion, itemTitle, othersAsking } from "./question";

function summary(overrides: Partial<EntitySummaryOutput> = {}): EntitySummaryOutput {
  return {
    id: "01a00000-0000-7000-8000-000000000001",
    entity_kind: "institution",
    status: "needs_review",
    label: "Oakville Library",
    names: [],
    institution_type: "library",
    suggested_type: null,
    administrative_level: null,
    country_code: "CA",
    place: null,
    parent: null,
    owner: null,
    url: null,
    homepage_url: null,
    evidence_count: 0,
    ...overrides,
  };
}

function item(overrides: Partial<ReviewItemDetail> = {}): ReviewItemDetail {
  return {
    id: "01a00000-0000-7000-8000-000000000009",
    entity_id: "01a00000-0000-7000-8000-000000000001",
    rule: "agent",
    question: { reasons: ["why"] },
    kind: null,
    status: "open",
    raised_by_assignment_id: null,
    decided_at: null,
    note: null,
    entity_kind: "institution",
    label: "Oakville Library",
    subject: summary(),
    entity: {},
    evidence: [],
    related: [],
    raised_at: "2026-10-08T12:00:00Z",
    raised_by: null,
    same_kind_open: 0,
    started_since: [],
    next_open_id: null,
    ...overrides,
  };
}

test("a duplicate asks whether the entity is any of its matches", () => {
  const related = (label: string) => ({
    fact: "duplicate_of",
    entity: summary({ label, status: "verified" }),
  });
  expect(
    itemQuestion(
      item({
        rule: "duplicate",
        related: [related("Oakville Public Library"), related("OPL"), related("Oak Library")],
      }),
    ),
  ).toBe("Is “Oakville Library” the same as one of 3 institutions already saved?");
  expect(
    itemQuestion(item({ rule: "duplicate", related: [related("OPL"), related("Oak Library")] })),
  ).toBe("Is “Oakville Library” the same as “OPL” or “Oak Library”?");
  expect(itemQuestion(item({ rule: "duplicate" }))).toBe("Is “Oakville Library” a duplicate?");
});

test("a shared question reads as the queue's row does", () => {
  expect(
    itemQuestion(
      item({ rule: "type_level", question: { institution_type: "school_board", level: "region" } }),
    ),
  ).toBe("Does a school board belong under a region?");
});

test("the questions about the web name the institution they are for", () => {
  const owner = { id: "x", entity_kind: "institution" as const, label: "Town of Oakville" };
  const domain = item({
    rule: "domain_checks",
    label: "oakville.ca",
    entity_kind: "domain",
    subject: summary({ entity_kind: "domain", label: "oakville.ca", owner }),
  });
  expect(itemQuestion(domain)).toBe("Is oakville.ca an official domain of Town of Oakville?");
  const source = item({
    rule: "platform_source",
    question: { source_type: "annual_report", platform: "issuu.com" },
    subject: summary({ entity_kind: "source", owner }),
  });
  expect(itemQuestion(source)).toBe(
    "Is this annual report on issuu.com published by Town of Oakville?",
  );
});

test("gaps list the types still missing, and the agent's own question has no sentence", () => {
  expect(
    itemQuestion(
      item({
        rule: "gaps",
        label: "Elm",
        question: { types_missing: ["library", "school_board"] },
      }),
    ),
  ).toBe("Does Elm really have no library or school board?");
  expect(itemQuestion(item())).toBeNull();
});

test("an item of a shared question counts the others that still ask it", () => {
  expect(othersAsking(1, "institution", true)).toBe("1 more institution asks the same question.");
  expect(othersAsking(3, "place", false)).toBe("3 places still ask the same question.");
});

test("an item without a question is titled by what it is about", () => {
  const owner = { id: "x", entity_kind: "institution" as const, label: "Moss Park Arena" };
  expect(
    itemTitle(
      item({
        entity_kind: "source",
        label: "tender https://www.toronto.ca/bids",
        entity: { source_type: "tender" },
        subject: summary({ entity_kind: "source", owner }),
      }),
    ),
  ).toBe("The agent asks about the tender source of Moss Park Arena");
  expect(itemTitle(item())).toBe("The agent asks about “Oakville Library”");
});

test("a suggested type asks whether the country should have it", () => {
  expect(
    itemQuestion(
      item({ rule: "new_type", question: { suggested_type: "Conservation Authority" } }),
    ),
  ).toBe("Is “Conservation Authority” a type the country should have?");
  // Without the suggestion there is no shared question; the agent's reasons must say it.
  expect(itemQuestion(item({ rule: "new_type", question: {} }))).toBeNull();
});

test("a moved domain asks whether the new address is the owner's homepage", () => {
  const owner = { id: "x", entity_kind: "institution" as const, label: "Town of Oakville" };
  const named = item({
    rule: "domain_moved",
    label: "https://oakville.ca/",
    entity_kind: "homepage",
    subject: summary({ entity_kind: "homepage", label: "https://oakville.ca/", owner }),
  });
  expect(itemQuestion(named)).toBe("Is https://oakville.ca/ the homepage of Town of Oakville?");
  const orphan = item({
    rule: "domain_moved",
    label: "https://oakville.ca/",
    entity_kind: "homepage",
    subject: summary({ entity_kind: "homepage", label: "https://oakville.ca/" }),
  });
  expect(itemQuestion(orphan)).toBe("Is https://oakville.ca/ a homepage to keep?");
});

test("a homepage on a platform asks whether the platform page is the homepage", () => {
  const owner = { id: "x", entity_kind: "institution" as const, label: "Elm Library" };
  expect(
    itemQuestion(
      item({
        rule: "platform_homepage",
        entity_kind: "homepage",
        question: { platform: "facebook.com" },
        subject: summary({ entity_kind: "homepage", owner }),
      }),
    ),
  ).toBe("Is this page on facebook.com the homepage of Elm Library?");
  expect(
    itemQuestion(
      item({
        rule: "platform_homepage",
        entity_kind: "homepage",
        question: {},
        subject: summary({ entity_kind: "homepage" }),
      }),
    ),
  ).toBe("Is this page the homepage of the institution?");
});

test("a name off its pattern asks about the type the question or the subject names", () => {
  expect(
    itemQuestion(item({ rule: "name_pattern", question: { institution_type: "school_board" } })),
  ).toBe("Is “Oakville Library” a school board, though its name misses the pattern?");
  // The subject's own type is the fallback (the summary helper's is "library").
  expect(itemQuestion(item({ rule: "name_pattern", question: {} }))).toBe(
    "Is “Oakville Library” a library, though its name misses the pattern?",
  );
  expect(
    itemQuestion(
      item({ rule: "name_pattern", question: {}, subject: summary({ institution_type: null }) }),
    ),
  ).toBe("Is “Oakville Library” named as it should be?");
});

test("an institution without a homepage asks whether the searches missed one", () => {
  expect(itemQuestion(item({ rule: "no_homepage", label: "Elm" }))).toBe(
    "Does Elm have a homepage the searches missed?",
  );
});

test("gaps without a readable type list ask the open question", () => {
  expect(itemQuestion(item({ rule: "gaps", label: "Elm", question: { types_missing: [] } }))).toBe(
    "Is anything missing from Elm?",
  );
  expect(itemQuestion(item({ rule: "gaps", label: "Elm", question: { types_missing: [7] } }))).toBe(
    "Is anything missing from Elm?",
  );
});

test("an item that has a question is titled by it, and a rule's item without one by its subject", () => {
  expect(itemTitle(item({ rule: "no_homepage", label: "Elm" }))).toBe(
    "Does Elm have a homepage the searches missed?",
  );
  const owner = { id: "x", entity_kind: "institution" as const, label: "Elm Library" };
  expect(
    itemTitle(
      item({
        rule: "quote_check",
        entity_kind: "homepage",
        label: "https://elm.ca/",
        subject: summary({ entity_kind: "homepage", owner }),
      }),
    ),
  ).toBe("The homepage claim of Elm Library");
  expect(itemTitle(item({ rule: "quote_check", entity_kind: "domain", label: "elm.ca" }))).toBe(
    "Elm.ca",
  );
});
