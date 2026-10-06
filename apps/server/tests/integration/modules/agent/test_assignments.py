"""Each assignment type run end to end by a scripted model through the runner, reaching every
end state of spec section 7.2 that a finding decides: `find_homepage` on its three paths
(trusted domain, new domain, search) and ending `complete`, `needs_review` and `no_homepage`;
`find_institutions` ending `complete` and `complete_with_gaps`; `find_sources` ending
`complete`. The budget, failure, requeue and cancellation endings are in the runner tests."""

import uuid
from dataclasses import replace
from typing import TYPE_CHECKING

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo
from sqlalchemy import select

from public_atlas.integrations.search import MemorySearcher, SearchResult
from public_atlas.modules.agent import runner
from public_atlas.modules.assignments import service as assignments
from public_atlas.modules.assignments.models import (
    Assignment,
    AssignmentResult,
    AssignmentStatus,
    AssignmentType,
)
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph.models import EntityStatus, Homepage, Institution, Source
from public_atlas.modules.review.models import ReviewItem

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.integration.conftest import Database, InlineConnector
    from tests.integration.modules.agent.conftest import Capture
    from tests.integration.modules.conftest import Build, Script, World

    from public_atlas.resources import Resources


TOWNS_URL = "https://www.elmcounty.ca/towns"
LIBRARY_URL = "https://www.elmcounty.ca/library"
FIND_HOMEPAGE = AssignmentType.FIND_HOMEPAGE
FIND_INSTITUTIONS = AssignmentType.FIND_INSTITUTIONS
FIND_SOURCES = AssignmentType.FIND_SOURCES
OAKVILLE = "https://www.oakville.ca/"
REGIONAL_TYPES = [
    "conservation_authority",
    "municipal_corporation",
    "police_service",
    "public_health_unit",
    "public_utility",
    "transit_agency",
]


def steps(*calls: tuple[str, dict[str, object]]) -> Script:
    """A model that makes the given tool calls in order, one per response, whatever the tools
    answer, and finishes with a summary once they are spent."""

    def script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        made = sum(
            isinstance(part, ToolCallPart)
            for message in messages
            if isinstance(message, ModelResponse)
            for part in message.parts
        )
        if made < len(calls):
            name, args = calls[made]
            return ModelResponse(parts=[ToolCallPart(name, dict(args))])
        return ModelResponse(parts=[ToolCallPart("finish", {"summary": "Out of steps."})])

    return script


def run(db: Database, res: Resources, assignment: Assignment) -> tuple[str, Assignment]:
    outcome = db.run(runner.run_assignment, res, assignment.id)

    async def read() -> Assignment:
        async with db.session() as session:
            return await session.get_one(Assignment, assignment.id)

    return outcome, db.run(read)


def spawned_for(
    db: Database, subject_id: uuid.UUID
) -> list[tuple[AssignmentType, AssignmentStatus]]:
    async def read() -> list[tuple[AssignmentType, AssignmentStatus]]:
        async with db.session() as session:
            rows = await assignments.list_assignments(session, subject_id=subject_id)
            return [(row.type, row.status) for row in rows if row.parent_assignment_id is not None]

    return db.run(read)


def reviews(db: Database) -> list[tuple[uuid.UUID, str]]:
    async def read() -> list[tuple[uuid.UUID, str]]:
        async with db.session() as session:
            rows = await session.scalars(select(ReviewItem).order_by(ReviewItem.id))
            return [(row.entity_id, row.rule) for row in rows]

    return db.run(read)


# --- find_homepage ---


def test_find_homepage_on_a_trusted_domain_opens_the_candidate_quotes_it_and_finishes(
    db: Database,
    world: World,
    build: type[Build],
    scripted: Callable[[Script], Resources],
    make_assignment: Callable[..., Assignment],
    capture: Capture,
):
    """The library's candidate homepage sits on the county's trusted site: the session saves
    it with the page's own quote, which verifies it, and finishes `complete`; its sources are
    looked for next."""

    async def make() -> Institution:
        async with db.session() as session:
            elm = await session.get_one(type(world.elm), world.elm.id)
            library = await build.candidate_institution(session, elm, "Elm County Library")
            towns = await graph.ensure_webpage(session, TOWNS_URL)
            await build.claim(session, library, LIBRARY_URL, found_on=towns)
            await session.commit()
            return library

    library = db.run(make)
    assignment = make_assignment(FIND_HOMEPAGE, library.id)
    capture.towns(assignment.id)
    capture.library(assignment.id)
    res = scripted(
        steps(
            ("status", {}),
            (
                "save_homepage",
                {
                    "url": LIBRARY_URL,
                    "found_on_url": TOWNS_URL,
                    "link_quote": "Elm County Library serves every town.",
                    "page_quote": "Elm County Library",
                },
            ),
            ("finish", {"summary": "Verified the library's page on the county site."}),
        )
    )
    outcome, row = run(db, res, assignment)
    assert (outcome, row.result) == ("complete", AssignmentResult.COMPLETE)
    assert row.summary == "Verified the library's page on the county site."

    async def check() -> tuple[Institution, EntityStatus]:
        async with db.session() as session:
            institution = await session.get_one(Institution, library.id)
            assert institution.homepage_id is not None
            homepage = await session.get_one(Homepage, institution.homepage_id)
            return institution, homepage.status

    _, status = db.run(check)
    assert status is EntityStatus.VERIFIED
    assert spawned_for(db, library.id) == [(FIND_SOURCES, AssignmentStatus.HELD)]


def test_find_homepage_on_a_new_domain_confirms_it_and_ends_complete(
    db: Database,
    world: World,
    scripted: Callable[[Script], Resources],
    claimed: Callable[..., Homepage],
    make_assignment: Callable[..., Assignment],
    capture: Capture,
):
    claim = claimed(world.town)
    assignment = make_assignment(FIND_HOMEPAGE, world.town.id)
    capture.page(OAKVILLE, "Welcome to the Town of Oakville", assignment.id)
    res = scripted(
        steps(
            (
                "confirm_domain",
                {"quotes": [{"url": OAKVILLE, "quote": "Welcome to the Town of Oakville"}]},
            ),
        )
    )
    outcome, row = run(db, res, assignment)
    assert (outcome, row.result) == ("complete", AssignmentResult.COMPLETE)
    assert row.summary is not None
    assert row.summary.startswith("Verified oakville.ca")

    async def check() -> tuple[uuid.UUID | None, EntityStatus]:
        async with db.session() as session:
            town = await session.get_one(Institution, world.town.id)
            domain = await graph.domain_by_name(session, "oakville.ca")
            assert domain is not None
            return town.homepage_id, domain.status

    assert db.run(check) == (claim.id, EntityStatus.VERIFIED)
    assert spawned_for(db, world.town.id) == [(FIND_SOURCES, AssignmentStatus.HELD)]
    assert spawned_for(db, world.oakville.id) == [(FIND_INSTITUTIONS, AssignmentStatus.HELD)]


def test_find_homepage_ends_needs_review_when_the_checks_disagree(
    db: Database,
    world: World,
    scripted: Callable[[Script], Resources],
    claimed: Callable[..., Homepage],
    make_assignment: Callable[..., Assignment],
    capture: Capture,
):
    """Three confirmations with a quote that is not on the page: the first two are sent back,
    the third sends the domain to a human and ends the assignment `needs_review`."""
    claim = claimed(world.town)
    assignment = make_assignment(FIND_HOMEPAGE, world.town.id)
    capture.page(OAKVILLE, "Welcome to the Town of Oakville", assignment.id)
    wrong: tuple[str, dict[str, object]] = (
        "confirm_domain",
        {"quotes": [{"url": OAKVILLE, "quote": "Welcome to our fine town"}]},
    )
    res = scripted(steps(wrong, wrong, wrong))
    outcome, row = run(db, res, assignment)
    assert (outcome, row.result) == ("needs_review", AssignmentResult.NEEDS_REVIEW)
    assert row.summary is not None
    assert row.summary.startswith("confirm_domain checks failed")

    async def check() -> tuple[EntityStatus, EntityStatus]:
        async with db.session() as session:
            domain = await graph.domain_by_name(session, "oakville.ca")
            assert domain is not None
            homepage = await session.get_one(Homepage, claim.id)
            return domain.status, homepage.status

    assert db.run(check) == (EntityStatus.NEEDS_REVIEW, EntityStatus.NEEDS_REVIEW)
    assert [rule for _, rule in reviews(db)] == ["domain_checks"]
    assert spawned_for(db, world.town.id) == []


def test_find_homepage_searches_the_web_and_a_human_confirms_the_unlinked_site(
    db: Database,
    world: World,
    queue: InlineConnector,
    scripted: Callable[[Script], Resources],
    make_assignment: Callable[..., Assignment],
    capture: Capture,
):
    """No candidate and no link on the allowed pages: the session searches, the result's site
    opens, it saves and confirms it, and with no trusted link behind it a reviewer decides. The
    agent and the checks agree, so the assignment ends `complete`."""
    assignment = make_assignment(FIND_HOMEPAGE, world.town.id)
    capture.page(OAKVILLE, "Welcome to the Town of Oakville", assignment.id)
    res = scripted(
        steps(
            ("search", {"query": "Town of Oakville official website", "domains": []}),
            ("save_homepage", {"url": OAKVILLE}),
            (
                "confirm_domain",
                {"quotes": [{"url": OAKVILLE, "quote": "Welcome to the Town of Oakville"}]},
            ),
        )
    )
    searcher = MemorySearcher([SearchResult(OAKVILLE, "Town of Oakville", "Official site")])
    queue.resources = res = replace(res, searcher=searcher)
    outcome, row = run(db, res, assignment)
    assert (outcome, row.result) == ("complete", AssignmentResult.COMPLETE)
    assert searcher.queries == ["Town of Oakville official website"]

    async def check() -> tuple[EntityStatus, list[EntityStatus], uuid.UUID]:
        async with db.session() as session:
            domain = await graph.domain_by_name(session, "oakville.ca")
            assert domain is not None
            town = await session.get_one(Institution, world.town.id)
            claims = await graph.homepages_of(session, town)
            return domain.status, [c.status for c in claims], domain.id

    status, claims, domain_id = db.run(check)
    assert status is EntityStatus.NEEDS_REVIEW
    assert claims == [EntityStatus.NEEDS_REVIEW]
    assert reviews(db) == [(domain_id, "domain_checks")]


def test_find_homepage_ends_no_homepage_when_the_searches_find_nothing(
    db: Database,
    world: World,
    queue: InlineConnector,
    scripted: Callable[[Script], Resources],
    make_assignment: Callable[..., Assignment],
):
    assignment = make_assignment(FIND_HOMEPAGE, world.town.id)
    res = scripted(
        steps(
            ("search", {"query": "Town of Oakville", "domains": ["elmcounty.ca"]}),
            ("search", {"query": "Town of Oakville official website", "domains": []}),
            ("finish", {"summary": "Two searches, no site of its own."}),
        )
    )
    queue.resources = res = replace(res, searcher=MemorySearcher([]))
    outcome, row = run(db, res, assignment)
    assert (outcome, row.result) == ("no_homepage", AssignmentResult.NO_HOMEPAGE)
    assert row.summary == "Two searches, no site of its own."
    assert reviews(db) == [(world.town.id, "no_homepage")]
    # Settled: the next run does not search again; a reviewer adds the address.
    assert spawned_for(db, world.town.id) == []


# --- find_institutions ---


def test_find_institutions_saves_bodies_and_finishes_complete(
    db: Database,
    world: World,
    scripted: Callable[[Script], Resources],
    make_assignment: Callable[..., Assignment],
    capture: Capture,
):
    assignment = make_assignment(FIND_INSTITUTIONS, world.elm.id)
    capture.towns(assignment.id)
    res = scripted(
        steps(
            (
                "save_institution",
                {
                    "name": "Elm Conservation Authority",
                    "language": "en",
                    "institution_type": "conservation_authority",
                    "acronym": "ECA",
                    "quote": "Elm Conservation Authority, ECA, protects the watershed.",
                    "page_url": TOWNS_URL,
                    "homepage_url": "https://www.elmcounty.ca/conservation",
                },
            ),
            (
                "finish",
                {
                    "summary": "The authority; nothing else on the county site.",
                    "types_not_found": [t for t in REGIONAL_TYPES if t != "conservation_authority"],
                },
            ),
        )
    )
    outcome, row = run(db, res, assignment)
    assert (outcome, row.result) == ("complete", AssignmentResult.COMPLETE)
    assert row.types_not_found == [t for t in REGIONAL_TYPES if t != "conservation_authority"]

    async def check() -> Institution:
        async with db.session() as session:
            return (
                await session.scalars(
                    select(Institution).where(
                        Institution.institution_type == "conservation_authority"
                    )
                )
            ).one()

    authority = db.run(check)
    assert authority.status is EntityStatus.VERIFIED
    # The finish spawned its homepage search, held in the step-mode run.
    assert spawned_for(db, authority.id) == [(FIND_HOMEPAGE, AssignmentStatus.HELD)]


def test_find_institutions_finished_short_twice_ends_complete_with_gaps(
    db: Database,
    world: World,
    scripted: Callable[[Script], Resources],
    make_assignment: Callable[..., Assignment],
):
    assignment = make_assignment(FIND_INSTITUTIONS, world.oakville.id)
    res = scripted(
        steps(
            ("finish", {"summary": "The town site lists nothing."}),
            ("finish", {"summary": "The town site lists nothing."}),
        )
    )
    outcome, row = run(db, res, assignment)
    assert (outcome, row.result) == ("complete_with_gaps", AssignmentResult.COMPLETE_WITH_GAPS)
    assert row.summary is not None
    assert row.summary.startswith("Not accounted for: ")
    assert reviews(db) == [(world.oakville.id, "gaps")]


# --- find_sources ---


def test_find_sources_saves_a_source_and_finishes_complete(
    db: Database,
    world: World,
    scripted: Callable[[Script], Resources],
    make_assignment: Callable[..., Assignment],
    capture: Capture,
):
    assignment = make_assignment(FIND_SOURCES, world.county.id)
    capture(
        "https://www.elmcounty.ca/budget",
        "<html><body><h1>County Budget</h1></body></html>",
        "County Budget\nThe county's budget, each year.",
        assignment_id=assignment.id,
    )
    expected = world.rules.expected_source_types(world.county.institution_type)
    res = scripted(
        steps(
            (
                "save_source",
                {
                    "url": "https://www.elmcounty.ca/budget",
                    "source_type": "budget",
                    "quote": "The county's budget, each year.",
                },
            ),
            (
                "finish",
                {
                    "summary": "The budget page; the rest is not on the site.",
                    "types_not_found": [t for t in expected if t != "budget"],
                },
            ),
        )
    )
    outcome, row = run(db, res, assignment)
    assert (outcome, row.result) == ("complete", AssignmentResult.COMPLETE)

    async def check() -> list[tuple[str, EntityStatus]]:
        async with db.session() as session:
            rows = await session.scalars(
                select(Source).where(Source.institution_id == world.county.id)
            )
            return [(s.source_type, s.status) for s in rows]

    assert db.run(check) == [("budget", EntityStatus.VERIFIED)]
    assert reviews(db) == []
