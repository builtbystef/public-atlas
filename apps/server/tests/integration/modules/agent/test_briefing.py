"""What a session is told: the standing instructions from the country tables, and the briefing
with the subject's ids, the places a body may be saved under, the checklist, where to look,
the homepages claimed before and the candidate to decide."""

from typing import TYPE_CHECKING, Any

from public_atlas.modules.agent import briefing, findings, prompts
from public_atlas.modules.assignments.models import Assignment, AssignmentType
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import EnteredBy, Homepage, Institution

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.integration.conftest import Database
    from tests.integration.modules.agent.conftest import Capture
    from tests.integration.modules.conftest import Build, World

    from public_atlas.modules.agent.context import SessionContext


TOWNS_URL = "https://www.elmcounty.ca/towns"
FIND_HOMEPAGE = AssignmentType.FIND_HOMEPAGE
FIND_INSTITUTIONS = AssignmentType.FIND_INSTITUTIONS
FIND_SOURCES = AssignmentType.FIND_SOURCES


def prompt_of(db: Database, ctx: SessionContext) -> str:
    async def read() -> str:
        async with db.session() as session:
            return await briefing.briefing(ctx, session)

    return db.run(read)


def lines_of(db: Database, ctx: SessionContext) -> list[str]:
    async def read() -> list[str]:
        async with db.session() as session:
            return await briefing.where_to_look(ctx, session)

    return db.run(read)


def test_the_instructions_come_from_the_country_tables(
    world: World,
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
):
    ctx = context(make_assignment(FIND_INSTITUTIONS, world.elm.id))
    text = prompts.instructions(ctx)
    assert text.startswith(prompts.COMMON)
    assert "Your goal:\n" + ctx.descriptor.goal in text
    assert "Country: Canada (CA)." in text
    assert "- region: regional_government; transit_agency, police_service" in text
    assert "- ministry: A ministry of a provincial or territorial government; " in text
    assert "names match /^(Ministry of |Ministère d)/" in text
    assert "- other: a public body that buys things and fits none of the types above" in text
    assert "- tender: Open calls for bids" in text
    assert "Platforms (fetchable, never trusted" in text
    assert "bidsandtenders.ca" in text


def test_a_place_subject_is_briefed_with_its_ids_checklist_and_places_to_save_under(
    db: Database,
    world: World,
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
):
    ctx = context(make_assignment(FIND_INSTITUTIONS, world.oakville.id))
    text = prompt_of(db, ctx)
    assert text.startswith("Assignment: find_institutions, session 0.")
    assert f"Subject: the place Oakville (municipality, id {world.oakville.id})." in text
    assert (
        "Its government: the institution Town of Oakville (municipal_government, id "
        f"{world.town.id})." in text
    )
    assert "Homepage: none known yet." in text
    assert "Types still to account for: conservation_authority, fire_service, library" in text
    assert (
        "Places to save under (place_id of save_institution): "
        f"Oakville (municipality) id={world.oakville.id}; Elm (region) id={world.elm.id}; "
        f"Ontario (province_territory) id={world.ontario.id}; "
    ) in text
    assert (
        "Where to look (the allowed domains tied to the subject; navigate refuses every other "
        "domain):" in text
    )
    assert "- elmcounty.ca: government of Elm (region)" in text
    assert text.index("Subject:") < text.index("Where to look") < text.index("Begin.")
    assert "Budget left: 50 requests." in text


def test_an_institution_subject_is_pointed_at_the_page_that_names_it_and_its_homepage(
    db: Database,
    world: World,
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    capture: Capture,
    call: Callable[..., Any],
):
    discover = context(make_assignment(FIND_INSTITUTIONS, world.elm.id))
    capture.towns(discover.assignment_id)
    saved = call(
        discover,
        findings.record_institution,
        name="Elm Conservation Authority",
        language="en",
        institution_type="conservation_authority",
        quote="Elm Conservation Authority, ECA, protects the watershed.",
        page_url=TOWNS_URL,
    )
    ctx = context(make_assignment(FIND_HOMEPAGE, saved.institution_id))
    lines = lines_of(db, ctx)
    assert lines[0].startswith(
        "Where to look (the allowed domains tied to the subject; navigate refuses every other "
        "domain until a search"
    )
    assert lines[1:] == [f"- elmcounty.ca: names it: {TOWNS_URL}; government of Elm (region)"]
    text = prompt_of(db, ctx)
    assert (
        f"It belongs to: Elm (region, id {world.elm.id}). Name the place in your searches." in text
    )
    assert "Places to save under" not in text

    sources = context(make_assignment(FIND_SOURCES, world.county.id))
    text = prompt_of(db, sources)
    assert "Homepage (verified): https://www.elmcounty.ca/" in text
    assert "Source types to find for a regional_government: " in text
    assert "Places to save under" in text
    assert lines_of(db, sources)[1:] == ["- elmcounty.ca: its homepage"]


def test_a_find_homepage_briefing_names_the_candidate_and_the_claims_rejected_before(
    db: Database,
    world: World,
    build: type[Build],
    claimed: Callable[..., Homepage],
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    in_session,
):
    async def rejected_before(session) -> None:
        town = await session.get_one(Institution, world.town.id)
        await build.claim(session, town, "https://www.oakville-old.ca/")
        old = await graph.domain_by_name(session, "oakville-old.ca")
        assert old is not None
        await status_changes.reject_domain(
            session, old, entered_by=EnteredBy.AGENT, reason="the host does not resolve"
        )

    in_session(rejected_before)
    claimed(world.town)
    ctx = context(make_assignment(FIND_HOMEPAGE, world.town.id))
    text = prompt_of(db, ctx)
    assert "Candidate homepage (candidate): https://www.oakville.ca/" in text
    assert "Homepages claimed for it before; do not save these again:" in text
    assert "- https://www.oakville-old.ca/: rejected (the host does not resolve)" in text
    assert (
        "Candidate to decide: https://www.oakville.ca/ on the candidate domain oakville.ca, "
        "which is open to you."
    ) in text
    assert f"Found as a link on the trusted page {TOWNS_URL}." in text
    assert "- oakville.ca: the candidate domain, yours to decide" in text
