"""`status`, `finish`, `request_review`, `search` and `read_file`: what a session reports, the
types a discovery finish has to account for, how a `find_homepage` ends, what a review request
does, what one search covers and records, and files fetched under the session's allowlist."""

from dataclasses import replace
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import select

from public_atlas.integrations.browser import BrowserPolicy
from public_atlas.integrations.search import MemorySearcher, SearchResult
from public_atlas.modules.agent import findings
from public_atlas.modules.assignments.models import (
    Assignment,
    AssignmentResult,
    AssignmentType,
    Usage,
    UsageKind,
)
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import (
    EnteredBy,
    EntityStatus,
    Homepage,
    Institution,
    Place,
)
from public_atlas.modules.review.models import ReviewItem

if TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic_ai import RunContext
    from tests.integration.conftest import Database, FixtureSite
    from tests.integration.modules.agent.conftest import Capture
    from tests.integration.modules.conftest import Build, World

    from public_atlas.modules.agent.context import SessionContext


TOWNS_URL = "https://www.elmcounty.ca/towns"
FIND_HOMEPAGE = AssignmentType.FIND_HOMEPAGE
FIND_INSTITUTIONS = AssignmentType.FIND_INSTITUTIONS
FIND_SOURCES = AssignmentType.FIND_SOURCES
# The institution types Canada expects under a region, sorted, as the checklist names them.
REGIONAL_TYPES = [
    "conservation_authority",
    "municipal_corporation",
    "police_service",
    "public_health_unit",
    "public_utility",
    "transit_agency",
]


@pytest.fixture
def discover(
    world: World,
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    capture: Capture,
) -> SessionContext:
    assignment = make_assignment(FIND_INSTITUTIONS, world.elm.id)
    capture.towns(assignment.id)
    return context(assignment)


def reload(db: Database, assignment_id) -> Assignment:
    async def read() -> Assignment:
        async with db.session() as session:
            return await session.get_one(Assignment, assignment_id)

    return db.run(read)


def test_status_lists_what_the_assignment_saved_and_opened(
    db: Database, discover: SessionContext, call: Callable[..., Any]
):
    saved = call(
        discover,
        findings.record_institution,
        name="Elm Conservation Authority",
        language="en",
        institution_type="conservation_authority",
        quote="Elm Conservation Authority, ECA, protects the watershed.",
        page_url=TOWNS_URL,
    )
    text = str(call(discover, findings.status_of))
    assert "Saved in this assignment:" in text
    assert (
        "institution 'Elm Conservation Authority' (conservation_authority, verified) "
        f"id={saved.institution_id}" in text
    )
    assert TOWNS_URL in text
    assert (
        "Types still to account for: "
        + ", ".join(t for t in REGIONAL_TYPES if t != "conservation_authority")
        in text
    )
    assert "Budget left: 50 requests" in text


def test_a_discovery_finish_accounts_for_every_expected_type(
    db: Database, discover: SessionContext, call: Callable[..., Any]
):
    # A finish that accounts for nothing is refused once, naming what is left.
    with pytest.raises(findings.FindingError) as refused:
        call(discover, findings.finish_assignment, summary="Done.", types_not_found=None)
    assert (
        "neither saved under the subject (or a place above it) nor named in types_not_found: "
        + ", ".join(REGIONAL_TYPES)
    ) in str(refused.value)
    assert discover.ended is None
    # A name the country does not list is refused on its own, and does not count as a second
    # short finish.
    with pytest.raises(findings.FindingError, match="names no institution type"):
        call(
            discover,
            findings.finish_assignment,
            summary="Done.",
            types_not_found=["library", "space_agency"],
        )
    # Reported in full (with a repeat and some whitespace), the finish goes through.
    finished = call(
        discover,
        findings.finish_assignment,
        summary="Looked through the directory for each.",
        types_not_found=[" police_service", *REGIONAL_TYPES, "transit_agency "],
    )
    assert finished.result is AssignmentResult.COMPLETE
    assert str(finished) == "Assignment finished (complete)."
    assert discover.ended is not None
    assert discover.ended.result is AssignmentResult.COMPLETE
    row = reload(db, discover.assignment_id)
    assert row.summary == "Looked through the directory for each."
    # As given, trimmed, once each.
    assert row.types_not_found == [
        "police_service",
        *[t for t in REGIONAL_TYPES if t != "police_service"],
    ]


def test_a_body_under_a_place_above_the_subject_counts_for_its_type(
    db: Database,
    world: World,
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    capture: Capture,
    call: Callable[..., Any],
):
    """A regional conservation authority is saved under the region, as the goal text asks, so
    a town under that region must not end `complete_with_gaps` for want of one of its own. A
    rejected body above counts no more than one under the subject would."""
    assignment = make_assignment(FIND_INSTITUTIONS, world.oakville.id)
    capture.towns(assignment.id)
    ctx = context(assignment)
    assert "conservation_authority" in call(ctx, findings.remaining_checklist)
    # Saved under Elm from a page found while working on Oakville.
    call(
        ctx,
        findings.record_institution,
        name="Elm Conservation Authority",
        language="en",
        institution_type="conservation_authority",
        quote="Elm Conservation Authority, ECA, protects the watershed.",
        page_url=TOWNS_URL,
        place_id=str(world.elm.id),
    )

    async def rejected_above() -> None:
        async with db.session() as session:
            elm = await session.get_one(Place, world.elm.id)
            utility = await graph.create_institution(
                session,
                name="Elm Hydro",
                institution_type="public_utility",
                place=elm,
                entered_by=EnteredBy.SCRIPT,
            )
            await status_changes.reject_institution(session, utility, entered_by=EnteredBy.SCRIPT)
            await session.commit()

    db.run(rejected_above)
    remaining = call(ctx, findings.remaining_checklist)
    assert "conservation_authority" not in remaining
    assert "public_utility" in remaining
    finished = call(
        ctx,
        findings.finish_assignment,
        summary="The region's conservation authority covers the town.",
        types_not_found=remaining,
    )
    assert finished.result is AssignmentResult.COMPLETE


def test_a_second_short_finish_ends_complete_with_gaps_and_raises_a_review_item(
    db: Database, world: World, discover: SessionContext, call: Callable[..., Any]
):
    with pytest.raises(findings.FindingError, match="Not finished"):
        call(discover, findings.finish_assignment, summary="Nothing here.", types_not_found=None)
    finished = call(
        discover,
        findings.finish_assignment,
        summary="Nothing here.",
        types_not_found=["transit_agency", "police_service"],
    )
    assert finished.result is AssignmentResult.COMPLETE_WITH_GAPS
    row = reload(db, discover.assignment_id)
    assert row.summary == (
        "Not accounted for: conservation_authority, municipal_corporation, public_health_unit, "
        "public_utility. Nothing here."
    )
    assert row.types_not_found == ["transit_agency", "police_service"]

    async def item() -> ReviewItem:
        async with db.session() as session:
            return (await session.scalars(select(ReviewItem))).one()

    found = db.run(item)
    assert (found.entity_id, found.rule) == (world.elm.id, "gaps")
    assert found.question["types_missing"] == [
        "conservation_authority",
        "municipal_corporation",
        "public_health_unit",
        "public_utility",
    ]


def test_a_sources_finish_accounts_for_every_source_type_of_the_institution(
    db: Database,
    world: World,
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    capture: Capture,
    call: Callable[..., Any],
):
    assignment = make_assignment(FIND_SOURCES, world.county.id)
    ctx = context(assignment)
    capture(
        "https://www.elmcounty.ca/budget",
        "<html><body><h1>County Budget</h1></body></html>",
        "County Budget\nThe county's budget, each year.",
        assignment_id=assignment.id,
    )
    expected = sorted(world.rules.expected_source_types(world.county.institution_type))
    all_but_budget = [t for t in expected if t != "budget"]
    with pytest.raises(findings.FindingError) as refused:
        call(
            ctx,
            findings.finish_assignment,
            summary="Nothing on the site.",
            types_not_found=all_but_budget,
        )
    assert "these source types are neither saved" in str(refused.value)
    assert str(refused.value).count("budget") == 1
    saved = call(
        ctx,
        findings.record_source,
        url="https://www.elmcounty.ca/budget",
        source_type="budget",
        quote="The county's budget, each year.",
    )
    assert "status verified" in str(saved)
    text = str(call(ctx, findings.status_of))
    assert "Types still to account for: " + ", ".join(all_but_budget) in text
    finished = call(
        ctx, findings.finish_assignment, summary="Only the budget.", types_not_found=all_but_budget
    )
    assert finished.result is AssignmentResult.COMPLETE
    assert reload(db, assignment.id).types_not_found == all_but_budget


def test_a_homepage_finish_ends_complete_or_no_homepage(
    db: Database,
    world: World,
    claimed: Callable[..., Homepage],
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    call: Callable[..., Any],
):
    """With a candidate undecided the finish is refused; with the searches done and nothing
    found the assignment ends `no_homepage` with a review item asking for the address; with
    the homepage verified it ends `complete`."""
    claimed(world.town)
    ctx = context(make_assignment(FIND_HOMEPAGE, world.town.id))
    with pytest.raises(findings.FindingError, match="decide the candidate you saved first"):
        call(ctx, findings.finish_assignment, summary="Could not decide.", types_not_found=None)
    call(ctx, findings.reject_candidate, reason="dead")
    finished = call(
        ctx, findings.finish_assignment, summary="Five searches, nothing.", types_not_found=None
    )
    assert finished.result is AssignmentResult.NO_HOMEPAGE
    assert ctx.ended is not None
    assert ctx.ended.result is AssignmentResult.NO_HOMEPAGE

    async def item() -> ReviewItem:
        async with db.session() as session:
            return (
                await session.scalars(
                    select(ReviewItem).where(ReviewItem.entity_id == world.town.id)
                )
            ).one()

    found = db.run(item)
    assert found.rule == "no_homepage"
    assert "Five searches, nothing." in found.question["reasons"][0]

    # The county has its homepage: its finish is `complete`.
    done = context(make_assignment(FIND_HOMEPAGE, world.county.id))
    assert (
        call(done, findings.finish_assignment, summary="Has one.", types_not_found=None).result
        is AssignmentResult.COMPLETE
    )


def test_request_review_sends_an_entity_to_a_human_and_ends_on_the_candidate_domain(
    db: Database,
    world: World,
    claimed: Callable[..., Homepage],
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    call: Callable[..., Any],
):
    claim = claimed(world.town)
    ctx = context(make_assignment(FIND_HOMEPAGE, world.town.id))
    with pytest.raises(findings.FindingError, match="Nothing with id"):
        call(ctx, findings.raise_item, entity_id=str(claim.id)[::-1], reason="?")
    with pytest.raises(findings.FindingError, match="must say what"):
        call(ctx, findings.raise_item, entity_id=str(world.town.id), reason="  ")
    asked = call(
        ctx, findings.raise_item, entity_id=str(world.town.id), reason="Is this body still a town?"
    )
    assert not asked.ended
    assert ctx.ended is None
    assert ctx.candidate is not None
    ended = call(
        ctx,
        findings.raise_item,
        entity_id=str(ctx.candidate.domain_id),
        reason="A shared platform.",
    )
    assert ended.ended
    assert ctx.candidate is None
    assert ctx.ended is not None
    assert ctx.ended.result is AssignmentResult.NEEDS_REVIEW

    async def check() -> tuple[EntityStatus, EntityStatus, list[str]]:
        async with db.session() as session:
            town = await session.get_one(Institution, world.town.id)
            homepage = await session.get_one(Homepage, claim.id)
            rules = list(await session.scalars(select(ReviewItem.rule).order_by(ReviewItem.id)))
            return town.status, homepage.status, rules

    town_status, homepage_status, rules = db.run(check)
    # A verified body keeps its status while the question is open; the claim waits with it.
    assert (town_status, homepage_status) == (EntityStatus.VERIFIED, EntityStatus.NEEDS_REVIEW)
    assert rules == ["agent", "agent"]


# --- search ---


def test_one_request_searches_every_domain_and_is_recorded_as_usage(
    db: Database,
    world: World,
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
):
    assignment = make_assignment(FIND_HOMEPAGE, world.town.id)
    searcher = MemorySearcher(
        [
            SearchResult("https://www.elmcounty.ca/oakville", "Oakville", "..."),
            SearchResult("https://www.ontario.ca/page/oakville", "Oakville", "..."),
            SearchResult("https://example.com/oakville", "Elsewhere", "..."),
        ]
    )
    ctx = replace(context(assignment), searcher=searcher)
    with pytest.raises(findings.FindingError, match="not an allowed domain"):
        db.run(findings.search_web, ctx, "Oakville", ["example.com"])
    answer = db.run(findings.search_web, ctx, "Oakville", ["elmcounty.ca", "ontario.ca"])
    assert searcher.queries == ["Oakville (site:elmcounty.ca OR site:ontario.ca)"]
    assert [r.url for r in answer.results] == [
        "https://www.elmcounty.ca/oakville",
        "https://www.ontario.ca/page/oakville",
    ]
    assert "example.com" not in str(answer)
    assert "example.com" not in ctx.allowed_domains

    async def usage() -> list[Usage]:
        async with db.session() as session:
            return list(
                await session.scalars(select(Usage).where(Usage.assignment_id == assignment.id))
            )

    [row] = db.run(usage)
    assert (row.kind, row.provider, row.purpose, row.units) == (
        UsageKind.SEARCH,
        "memory",
        "find_homepage",
        1,
    )


def test_a_whole_web_search_opens_the_results_sites_and_a_result_can_be_saved(
    db: Database,
    world: World,
    build: type[Build],
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    call: Callable[..., Any],
    in_session,
):
    assignment = make_assignment(FIND_HOMEPAGE, world.town.id)
    searcher = MemorySearcher(
        [SearchResult("https://www.oakville.ca/", "Town of Oakville", "Official site")]
    )
    ctx = replace(context(assignment), searcher=searcher)
    # Before the search, the result's site is outside the allowlist like any other, and a
    # claim on it needs a linking page.
    with pytest.raises(findings.FindingError, match="Pass found_on_url"):
        call(ctx, findings.record_homepage, url="https://www.oakville.ca/")
    assert not ctx.file_policy().permits("www.oakville.ca")
    answer = db.run(findings.search_web, ctx, "Town of Oakville official website", [])
    assert str(answer).startswith("Leads, not evidence. These results' sites are open to you now")
    assert ctx.search_hosts == {"oakville.ca"}
    assert ctx.file_policy().permits("www.oakville.ca")
    assert ctx.file_policy().permits("oakville.ca")
    assert not ctx.file_policy().permits("example.com")
    outcome = call(ctx, findings.record_homepage, url="https://www.oakville.ca/")
    assert "candidate domain oakville.ca, which is yours to decide" in str(outcome)
    assert "No trusted page links to it" in str(outcome)
    assert ctx.candidate is not None
    assert ctx.candidate.domain_name == "oakville.ca"
    assert ctx.allowed_domains.count("oakville.ca") == 1

    async def state() -> Homepage:
        async with db.session() as session:
            return (
                await session.scalars(
                    select(Homepage).where(Homepage.institution_id == world.town.id)
                )
            ).one()

    claim = db.run(state)
    assert (claim.status, claim.found_on_webpage_id) == (EntityStatus.CANDIDATE, None)

    # The search result's site is not the session's to claim for another body.
    async def other(session) -> Institution:
        oakville = await session.get_one(Place, world.oakville.id)
        return await build.candidate_institution(session, oakville, "Oakville Library")

    library = in_session(other)
    with pytest.raises(findings.FindingError, match="Pass found_on_url"):
        call(
            ctx,
            findings.record_homepage,
            url="https://www.oakville.ca/",
            institution_id=str(library.id),
        )


def test_an_assignment_gets_five_searches_on_domains_or_the_whole_web(
    db: Database,
    world: World,
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
):
    ctx = replace(
        context(make_assignment(FIND_HOMEPAGE, world.town.id)), searcher=MemorySearcher([])
    )
    searcher = cast("MemorySearcher", ctx.searcher)
    # Site-scoped and whole-web searches share the one counter: the engine bills each alike.
    for query, domains in (
        ("Oakville", ["elmcounty.ca"]),
        ("Oakville town", []),
        ("Oakville", ["elmcounty.ca", "ontario.ca"]),
        ("Town of Oakville", []),
        ("Oakville council", ["ontario.ca"]),
    ):
        assert db.run(findings.search_web, ctx, query, domains).note is None
    assert len(searcher.queries) == findings.MAX_SEARCHES == 5
    for domains in ([], ["elmcounty.ca"]):
        capped = db.run(findings.search_web, ctx, "Oakville", domains)
        assert str(capped).startswith("Error: this assignment has made its 5 searches")
    assert len(searcher.queries) == 5
    without = replace(ctx, searcher=None)
    assert str(db.run(findings.search_web, without, "Oakville", [])).startswith(
        "Error: no search engine"
    )


# --- read_file ---


def test_read_file_fetches_under_the_sessions_allowlist(
    db: Database,
    world: World,
    site: FixtureSite,
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
):
    """The tool reads a document through the evidence module under the session's policy: a
    file on an allowed host is parsed and chunked, one elsewhere is refused."""
    assignment = make_assignment(FIND_SOURCES, world.county.id)
    ctx = context(assignment)
    ctx.allowed_domains.append("127.0.0.1")
    ctx.policy = BrowserPolicy(ctx.allowed_domains, block_private_addresses=False, min_interval=0)
    run_ctx = cast("RunContext[SessionContext]", SimpleNamespace(deps=ctx))
    text = str(db.run(findings.read_file, run_ctx, f"{site.allowed}/notes.txt"))
    assert "Council notes: tenders close Friday." in text
    refused = str(db.run(findings.read_file, run_ctx, f"{site.outside}/notes.txt"))
    assert refused.startswith("Error: domain not in allowed_domains")
    status = str(db.run(findings.status_of, ctx, db.session()))
    assert f"{site.allowed}/notes.txt: ready" in status
