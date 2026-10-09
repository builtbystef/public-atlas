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
    saved under the subject (for institution types, under it or a place above it) or named in
    `types_not_found`."""

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

# For the discovery types, which read long lists. On the first crawl, reading a list's CSV
# took 4 sessions where paging the HTML table 20 rows at a time took 7 or more.
DOWNLOAD_FIRST = (
    "When a list page links to a download of the list (CSV, spreadsheet, JSON) on an allowed "
    "domain, read it once with read_file instead of paging the table, and compare its row "
    "count with the total the page states: page the table only when there is no download or "
    "the counts disagree (a file can lag the page). "
)

# What gets a row (eval dataset README, "Scope"): a body with buying power of its own. The
# first eval run saved eighteen arenas and community centres from one city's agencies page and
# filled a village of 579 people's checklist with a provincial contractor and an old health unit.
BUYING_POWER = (
    "What counts as an institution: a body gets a row only when it buys on its own account, "
    "which shows as its own procurement page, its own budget, or its own board that approves "
    "spending. Not institutions, so never saved: a board of management for one facility (an "
    "arena, a community centre, a theatre, one street); a non-profit the government funds but "
    "does not control; a holding company above a utility (save the operating utility the "
    "public deals with); a subsidiary that buys through its parent; a board that invests or "
    "grants the government's money; a partnership or contractor the government does not "
    "control; and business improvement areas, council committees, tribunals and advisory "
    "boards. When in doubt, the consolidated financial statements decide: a body not "
    "consolidated there is not the government's. Most small municipalities have only a fire "
    "service and a library of their own; transit, police, health and utilities are run by a "
    "place above or a contractor, and naming those types in types_not_found is the right "
    "answer, not a provincial body or a contractor saved to fill the slot. "
)

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
        finishing_tools=("confirm_domain", "finish"),
        goal=(
            "Find the institution's homepage: its official starting page on the web, not an "
            "article about it or a directory that lists it. Three paths, in one assignment.\n"
            "A candidate on a trusted domain (the briefing lists it): open it, judge it the "
            "institution's own, and save it with save_homepage and page_quote, a phrase from "
            "the page that names the institution. A body with no site of its own that lives "
            "on its parent's pages has its page there: judge that it is the page for this body "
            "and not a mention of it.\n"
            "A candidate on a new domain (the briefing names it as yours to decide): you are "
            "the only assignment allowed to open it. Open the candidate page, the home page "
            "with and without www, about, contact and the footer, and gather quotes in which "
            "the site presents itself as the institution: its name, its address, a copyright "
            "line. Then decide it: confirm_domain with the quotes (at least one containing the "
            "institution's name or acronym, each with the exact URL you opened it on; when the "
            "site calls itself by the opening words of the recorded name or by its place name "
            "with another designator, pass that as name_used); domain_moved when the candidate "
            "or the home page redirects to another domain, which navigate reports as outside "
            "the allowed domains; reject_domain when it is dead, parked or another body's, then "
            "keep looking; request_review on the domain when it is a platform many bodies "
            "publish on, when the site is live but refuses you, or when you cannot tell.\n"
            "No candidate: search the pages of its government on the allowed domains for a "
            "link to it or its address written out (a directory, a contact list, a PDF's "
            "footer), and save what you find with save_homepage, found_on_url and link_quote. "
            "When the allowed pages have no link, search the web (five searches in all, so name "
            "the place and the institution in each); the sites a search returns open for you "
            "for the rest of the session. Open the likely result, judge it as above, save it "
            "with save_homepage (no linking page needed), and decide it. A homepage listed in "
            "the briefing as rejected is dead or not this body's: do not save it again.\n"
            "Finish with a summary when the homepage is verified or with a human, or when the "
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
            "Find every public body under the place that buys on its own account: each "
            "institution type expected at the place's level, from the government's own pages "
            "(organization charts, 'ministries and agencies', 'boards and committees', "
            "'departments', 'agencies, boards and commissions', the budget, the annual report, "
            "directories). The page that lists every body the government owns is its "
            "consolidated financial statements (in the annual financial report): the entities "
            "consolidated there are its bodies, so open it early and work from its list. "
            "Save each body with save_institution: its type, the body it sits under "
            "(parent_institution_id, when a page says so), whether it buys for itself or its "
            "parent buys for it (procurement_handled_by), and a quote from the page that names "
            "it; pass homepage_url whenever the page links to the body, as the exact href in "
            "snapshot's link list. A body on the government's own domain (a ministry, a "
            "department) has its page there: open it and save it with save_homepage and "
            "page_quote. "
            + DOWNLOAD_FIRST
            + "A directory's short label ('Transportation', 'Health') is not a name: open the "
            "body's own page and save the full name it writes ('Ministry of Transportation'), "
            "quoting from that page. Pick the type by what the body is, from the descriptions "
            "below. A body of a municipality or region (a housing corporation, a parking "
            "authority, a city-owned corporation) is never a provincial type such as agency. A "
            "police, transit or library board is part of the service it governs: save the "
            "service, not the board.\n"
            + BUYING_POWER
            + "A public body that passes that test and fits none of the listed types is still "
            "saved: pass 'other' with suggested_type, and a human adds the type. Never use "
            "'other' when a listed type fits. A body is saved under the place it serves, not "
            "the page it was found on: one serving the whole of a place above the subject goes "
            "under that place, with its id from the briefing's 'Places to save under' line as "
            "place_id. A type the briefing lists as already recorded from an official list is "
            "done: skip the directory pages that list that type. Finish only when every "
            "expected type is saved or named in types_not_found, with a summary of what was "
            "found and where you looked for the rest; a finish that leaves a type out is "
            "refused once."
        ),
        checklist=Checklist.INSTITUTION_TYPES,
        # 250 requests: Toronto's discovery spent 150 with bodies still unfound. The stall rule
        # in `agent/runner.py` ends an assignment that has stopped finding things, so the
        # larger cap is not spent on nothing.
        budget=Budget(requests=250, tokens=20_000_000),
        model=ModelChoice(LUNA, "xhigh", LUNA_WINDOW),
    ),
    AssignmentType.FIND_SOURCES: Descriptor(
        type=AssignmentType.FIND_SOURCES,
        subject_kind=EntityKind.INSTITUTION,
        tools=(*BROWSING, *SHARED, "save_source", "save_institution", "save_homepage", "finish"),
        finishing_tools=("finish",),
        goal=(
            "Find the institution's sources: the web pages that carry procurement signals, one "
            "of each source type expected for the institution's type, and save each with "
            "save_source, quoting from the page itself. Start from the institution's homepage: "
            "menus such as 'Doing business with us', 'Procurement', 'Bids and tenders', "
            "'Budget', 'Finance', 'Council', 'Board', 'Plans and reports', 'About us'. Follow "
            "links into platforms (bids portals, meeting hosts) when a page links there, and "
            "pass that page as linked_from_url. A page that requires a supplier login is still "
            "a source, with access='login'. Save the standing page for each type, the one that "
            "stays and lists every edition: the budget page, not one year's budget PDF or a "
            "news release about it; the council meetings page or the meetings portal it links "
            "to, not one agenda. A capital plan is its own page (capital budget, capital "
            "forecast, asset management plan): do not save the operating budget page as the "
            "capital plan. When an institution has two pages of one type (its own meetings page "
            "and the portal it links to), save both. A document published at more than one URL, "
            "or in more than one edition (accessible, condensed, French), is one source: save "
            "one, the full edition on the institution's own site. Not sources, so never saved: "
            "a platform's root or front page (the Biddingo or MERX home page), a single meeting "
            "or a single tender, and a search results page (a MERX search URL); save the "
            "institution's standing page on the platform instead, or name the type in "
            "types_not_found. The parent's page is never saved as the child's: when a body's "
            "budget, tenders or procurement run through the body it sits under (a transit "
            "agency's budget in the city's), do not save the parent's page for it; name the "
            "type in types_not_found and say in the summary that the parent covers it. Save a "
            "body you meet that is missing with save_institution, then return to the sources. "
            "Finish only when every expected source type is saved or named in "
            "types_not_found, with a summary of what was found and where you looked for the "
            "rest; a finish that leaves a type out is refused once."
        ),
        checklist=Checklist.SOURCE_TYPES,
        budget=Budget(requests=120, tokens=10_000_000),
        model=ModelChoice(LUNA, "xhigh", LUNA_WINDOW),
    ),
}


def descriptor_for(assignment_type: AssignmentType) -> Descriptor:
    return DESCRIPTORS[assignment_type]
