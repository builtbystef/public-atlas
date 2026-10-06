"""One descriptor per assignment type (spec sections 7.2, 7.4 and 8.4): what kind of entity it
works on, the tools it gets, which of them end it, its goal, the checklist it must account for,
its budget and its model. Product data: edit here, not in `Settings`."""

from dataclasses import dataclass
from enum import StrEnum

from public_atlas.integrations.ai import ModelChoice
from public_atlas.integrations.browser import TOOLS as BROWSING
from public_atlas.modules.assignments.models import AssignmentType
from public_atlas.modules.graph.models import EntityKind

__all__ = [
    "DESCRIPTORS",
    "HANDOFF_MODEL",
    "Budget",
    "Checklist",
    "Descriptor",
    "descriptor_for",
]


class Checklist(StrEnum):
    """What a discovery assignment must account for before it finishes: every type listed is
    saved under the subject or named in `types_not_found`."""

    # The institution types the country expects at the place's level.
    INSTITUTION_TYPES = "institution_types"
    # The source types the country expects for the institution's type.
    SOURCE_TYPES = "source_types"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class Budget:
    """What one assignment may spend over all its sessions. Past either limit it finishes
    `out_of_budget`. Tokens count the context resent on every request, so at 80k of context 150
    requests are 12M tokens, nearly all cached; the request cap is the one meant to bind."""

    requests: int
    tokens: int


@dataclass(frozen=True, slots=True)
class Descriptor:
    type: AssignmentType
    subject_kind: EntityKind
    # By name, as the agent module's adapter registers them (spec section 8.1).
    tools: tuple[str, ...]
    # The tools that end the assignment.
    finishing_tools: tuple[str, ...]
    # The goal, as the briefing states it.
    goal: str
    checklist: Checklist
    budget: Budget
    model: ModelChoice


LUNA = "gpt-6-luna"
# Luna's context window, in tokens.
LUNA_WINDOW = 272_000

# For handoff notes and summaries, which compress state the database already holds.
HANDOFF_MODEL = ModelChoice(LUNA, "medium", LUNA_WINDOW)

# What every type gets besides the browser: files, its own status, and a human to ask.
SHARED = ("read_file", "status", "request_review")

DESCRIPTORS: dict[AssignmentType, Descriptor] = {
    AssignmentType.FIND_HOMEPAGE: Descriptor(
        type=AssignmentType.FIND_HOMEPAGE,
        subject_kind=EntityKind.INSTITUTION,
        tools=(
            *BROWSING,
            *SHARED,
            "search",
            "save_homepage",
            "save_institution",
            "confirm_domain",
            "reject_domain",
            "domain_moved",
            "finish",
        ),
        finishing_tools=("confirm_domain", "reject_domain", "domain_moved", "finish"),
        goal=(
            "Find the institution's homepage: its official starting page on the web, not an "
            "article about it or a directory that lists it. A candidate homepage on a trusted "
            "domain: open it, judge it the institution's own, and save it with a quote from the "
            "page. A candidate on a new domain: open it, quote the pages that name the "
            "institution, then confirm_domain; reject_domain for a dead site or one that is "
            "another body's; domain_moved when it redirects elsewhere. No candidate: search the "
            "web (five searches at most), open the results, and save the page that is the "
            "institution's own. Finish with a summary when the homepage is saved, or when the "
            "searches found nothing."
        ),
        checklist=Checklist.NONE,
        budget=Budget(requests=60, tokens=4_000_000),
        model=ModelChoice(LUNA, "xhigh", LUNA_WINDOW),
    ),
    AssignmentType.FIND_INSTITUTIONS: Descriptor(
        type=AssignmentType.FIND_INSTITUTIONS,
        subject_kind=EntityKind.PLACE,
        tools=(*BROWSING, *SHARED, "save_institution", "save_homepage", "finish"),
        finishing_tools=("finish",),
        goal=(
            "Find every public body under the place: each institution type expected at the "
            "place's level, from the government's own pages (its departments, agencies, boards "
            "and commissions pages, its budget and its annual report). Save each body with its "
            "type, the body it sits under, whether it buys for itself or its parent buys for it, "
            "and a quote from the page that names it. Save a body's homepage when a page links "
            "to it. Finish only when every expected type is saved or named in types_not_found."
        ),
        checklist=Checklist.INSTITUTION_TYPES,
        budget=Budget(requests=150, tokens=12_000_000),
        model=ModelChoice(LUNA, "xhigh", LUNA_WINDOW),
    ),
    AssignmentType.FIND_SOURCES: Descriptor(
        type=AssignmentType.FIND_SOURCES,
        subject_kind=EntityKind.INSTITUTION,
        tools=(*BROWSING, *SHARED, "save_source", "save_institution", "save_homepage", "finish"),
        finishing_tools=("finish",),
        goal=(
            "Find the institution's sources: the web pages that carry procurement signals, one "
            "of each source type expected for the institution's type, starting from its "
            "homepage. Save each page with its source type and a quote from it. Finish only when "
            "every expected source type is saved or named in types_not_found."
        ),
        checklist=Checklist.SOURCE_TYPES,
        budget=Budget(requests=120, tokens=10_000_000),
        model=ModelChoice(LUNA, "xhigh", LUNA_WINDOW),
    ),
}


def descriptor_for(assignment_type: AssignmentType) -> Descriptor:
    return DESCRIPTORS[assignment_type]
