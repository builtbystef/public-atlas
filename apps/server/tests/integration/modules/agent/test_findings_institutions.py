"""`save_institution`: what a finding needs, duplicates, a type the country does not expect at
the level, a body no type fits, a name that misses its pattern, the parent and buyer a page
names, and the places a body may be saved under."""

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select

from public_atlas.modules.agent import findings
from public_atlas.modules.assignments.models import AssignmentType
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import (
    EnteredBy,
    EntityStatus,
    Homepage,
    Institution,
    Place,
    ProcurementHandledBy,
)
from public_atlas.modules.review.models import ReviewItem, ReviewStatus

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.integration.conftest import Database
    from tests.integration.modules.agent.conftest import Capture
    from tests.integration.modules.conftest import Build, World

    from public_atlas.modules.agent.context import SessionContext
    from public_atlas.modules.assignments.models import Assignment


TOWNS_URL = "https://www.elmcounty.ca/towns"
LIBRARY_URL = "https://www.elmcounty.ca/library"
PLATFORM_URL = "https://elm.bidsandtenders.ca/list"
FIND_INSTITUTIONS = AssignmentType.FIND_INSTITUTIONS


@pytest.fixture
def discover(
    world: World,
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    capture: Capture,
) -> SessionContext:
    """A `find_institutions` session on the region Elm, with the towns page captured."""
    assignment = make_assignment(FIND_INSTITUTIONS, world.elm.id)
    capture.towns(assignment.id)
    return context(assignment)


@pytest.fixture
def town_discover(
    world: World,
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    capture: Capture,
) -> SessionContext:
    """A `find_institutions` session on the town Oakville, reading the region's towns page."""
    assignment = make_assignment(FIND_INSTITUTIONS, world.oakville.id)
    capture.towns(assignment.id)
    return context(assignment)


def library(**overrides: object) -> dict[str, object]:
    """The library as the towns page names it."""
    return {
        "name": "Elm County Library",
        "language": "en",
        "institution_type": "library",
        "quote": "Elm County Library serves every town.",
        "page_url": TOWNS_URL,
        # "Elm County Library" is enough like "County of Elm" to be offered it.
        "decision": "new",
        **overrides,
    }


def test_a_finding_needs_an_opened_page_and_a_verbatim_quote_that_names_the_body(
    db: Database, discover: SessionContext, call: Callable[..., Any]
):
    save = findings.record_institution
    with pytest.raises(findings.FindingError, match="has not been opened"):
        call(discover, save, **library(page_url="https://www.elmcounty.ca/nowhere"))
    with pytest.raises(findings.FindingError, match="not found word for word") as refused:
        call(discover, save, **library(quote="The Elm County Library publishes this list"))
    assert "closest text on the page" in str(refused.value)
    with pytest.raises(findings.FindingError, match="Unknown institution type"):
        call(discover, save, **library(institution_type="bureau"))
    # A single word is on every page, so a quote that short proves nothing.
    with pytest.raises(findings.FindingError, match="too short"):
        call(discover, save, **library(quote="Library"))
    with pytest.raises(findings.FindingError, match="does not name the institution"):
        call(discover, save, **library(quote="publishes this list"))
    with pytest.raises(findings.FindingError, match="name is empty"):
        call(discover, save, **library(name="  "))
    with pytest.raises(findings.FindingError, match="'self' or 'parent'"):
        call(discover, save, **library(procurement_handled_by="itself"))
    with pytest.raises(findings.FindingError, match="to sit under"):
        call(discover, save, **library(parent_institution_id=str(uuid.uuid4())))

    async def saved() -> int:
        async with db.session() as session:
            rows = await session.scalars(
                select(Institution).where(Institution.institution_type == "library")
            )
            return len(rows.all())

    assert db.run(saved) == 0


def test_an_institution_on_a_trusted_page_is_verified_with_its_parent_and_buyer(
    db: Database, world: World, discover: SessionContext, call: Callable[..., Any]
):
    """The towns page is on the county's trusted domain: a body it names is verified from the
    quote, with the parent and buyer the agent read there. Its homepage on the same domain is
    not verified until that page is opened and quoted (see the homepage tests)."""
    outcome = call(
        discover,
        findings.record_institution,
        name="Elm Conservation Authority",
        language="en",
        institution_type="conservation_authority",
        acronym="ECA",
        quote="Elm Conservation Authority, ECA, protects the watershed.",
        page_url=TOWNS_URL,
        parent_institution_id=str(world.county.id),
        procurement_handled_by="parent",
        homepage_url="https://www.elmcounty.ca/conservation",
    )
    assert str(outcome).startswith(
        "Saved institution 'Elm Conservation Authority' (conservation_authority)"
    )
    assert "status verified" in str(outcome)
    assert "Sent for review" not in str(outcome)
    assert "elmcounty.ca is trusted, so the page is verified from its own text" in str(outcome)

    async def check() -> tuple[Institution, list[str], list[str], list[Homepage]]:
        async with db.session() as session:
            institution = (
                await session.scalars(
                    select(Institution).where(
                        Institution.institution_type == "conservation_authority"
                    )
                )
            ).one()
            names = [alias.text for alias in await graph.names_of(session, institution)]
            quotes = [row.quote for row in await evidence.evidence_for(session, institution.id)]
            return institution, names, quotes, await graph.homepages_of(session, institution)

    institution, names, quotes, claims = db.run(check)
    assert institution.status is EntityStatus.VERIFIED
    assert institution.parent_institution_id == world.county.id
    assert institution.procurement_handled_by is ProcurementHandledBy.PARENT
    assert institution.place_id == world.elm.id
    assert names == ["Elm Conservation Authority", "ECA"]
    assert quotes == ["Elm Conservation Authority, ECA, protects the watershed."]
    # The claim is recorded with the trusted page that linked to it, and waits to be read.
    assert institution.homepage_id is None
    assert [(claim.status, claim.found_on_webpage_id is not None) for claim in claims] == [
        (EntityStatus.CANDIDATE, True)
    ]


def test_a_body_defaults_to_the_places_government_as_its_parent(
    db: Database, world: World, discover: SessionContext, call: Callable[..., Any]
):
    outcome = call(discover, findings.record_institution, **library())
    assert str(outcome).startswith("Saved institution 'Elm County Library' (library)")

    async def parent() -> uuid.UUID | None:
        async with db.session() as session:
            row = (
                await session.scalars(
                    select(Institution).where(Institution.institution_type == "library")
                )
            ).one()
            return row.parent_institution_id

    assert db.run(parent) == world.county.id


def test_a_known_type_at_an_unexpected_level_is_kept_and_sent_for_review(
    db: Database, discover: SessionContext, call: Callable[..., Any]
):
    """Canada expects a library under a municipality. One found under a region is a gap in the
    tables, not a mistake to drop: it is saved, and a human decides, by kind."""
    outcome = call(discover, findings.record_institution, **library())
    assert "Sent for review: A library found under a region" in str(outcome)
    assert "status needs_review" in str(outcome)

    async def check() -> tuple[EntityStatus, ReviewItem]:
        async with db.session() as session:
            institution = (
                await session.scalars(
                    select(Institution).where(Institution.institution_type == "library")
                )
            ).one()
            item = (
                await session.scalars(
                    select(ReviewItem).where(ReviewItem.entity_id == institution.id)
                )
            ).one()
            return institution.status, item

    status, item = db.run(check)
    assert status is EntityStatus.NEEDS_REVIEW
    assert (item.status, item.rule, item.kind) == (
        ReviewStatus.OPEN,
        "type_level",
        "type_level:library@region",
    )
    assert item.question["institution_type"] == "library"
    assert item.question["level"] == "region"


def test_a_body_serving_a_place_above_is_saved_under_that_place(
    db: Database, world: World, town_discover: SessionContext, call: Callable[..., Any]
):
    """A regional body named on a page a town's session reads belongs to the region: saved
    there, it sits at the level the country expects, so no review is raised."""
    outcome = call(
        town_discover,
        findings.record_institution,
        name="Elm Conservation Authority",
        language="en",
        institution_type="conservation_authority",
        quote="Elm Conservation Authority, ECA, protects the watershed.",
        page_url=TOWNS_URL,
        place_id=str(world.elm.id),
    )
    assert "Sent for review" not in str(outcome)

    async def check() -> tuple[uuid.UUID, uuid.UUID | None, int]:
        async with db.session() as session:
            saved = (
                await session.scalars(
                    select(Institution).where(
                        Institution.institution_type == "conservation_authority"
                    )
                )
            ).one()
            reviews = len((await session.scalars(select(ReviewItem))).all())
            return saved.place_id, saved.parent_institution_id, reviews

    place_id, parent_id, reviews = db.run(check)
    assert place_id == world.elm.id
    # The parent defaults to the government of the place it was saved under.
    assert parent_id == world.county.id
    assert reviews == 0


def test_a_place_outside_the_chain_is_refused_with_the_allowed_ones_named(
    db: Database, world: World, town_discover: SessionContext, call: Callable[..., Any]
):
    canada = db.run(_canada, db, world)
    outsider = uuid.uuid4()
    with pytest.raises(findings.FindingError) as refused:
        call(town_discover, findings.record_institution, **library(place_id=str(outsider)))
    assert str(refused.value) == (
        f"place_id {outsider} is not a place this assignment may save under. Allowed: the "
        f"subject's place and the places above it: Oakville (municipality) "
        f"id={world.oakville.id}; Elm (region) id={world.elm.id}; "
        f"Ontario (province_territory) id={world.ontario.id}; Canada (country) id={canada}."
    )
    with pytest.raises(findings.FindingError, match="place_id is not an id"):
        call(town_discover, findings.record_institution, **library(place_id="elm"))


async def _canada(db: Database, world: World) -> uuid.UUID:
    async with db.session() as session:
        ontario = await session.get_one(Place, world.ontario.id)
        assert ontario.parent_place_id is not None
        return ontario.parent_place_id


def test_duplicates_are_offered_across_the_places_above_and_the_agent_decides(
    db: Database,
    world: World,
    discover: SessionContext,
    town_discover: SessionContext,
    call: Callable[..., Any],
):
    """The region's session saved the library. A town's session meeting it under another name
    is offered the match whether it saves under the town or the region; the agent then
    matches, declines, or leaves it to a human."""
    save = findings.record_institution
    # A decision naming an id that was never offered is refused, even with nothing to offer.
    with pytest.raises(findings.FindingError, match="was not offered"):
        call(
            discover,
            save,
            **library(
                name="Elm Transit",
                institution_type="transit_agency",
                quote="Elm Transit is operated by the County of Elm",
                decision=str(uuid.uuid4()),
            ),
        )
    first = call(discover, save, **library())
    assert str(first).startswith("Saved institution 'Elm County Library'")
    other_name = library(
        name="Elm County Public Library",
        quote="Elm County Public Library is another name for it",
        decision=None,
    )
    for place_id in (None, str(world.elm.id)):
        offered = call(town_discover, save, **other_name, place_id=place_id)
        assert isinstance(offered, findings.LikelyDuplicates)
        assert str(offered).startswith("Not saved: institution may already exist")
        assert "'Elm County Library'" in str(offered)
    existing_id = next(m.entity_id for m in offered.matches if m.alias == "Elm County Library")
    matched = call(town_discover, save, **{**other_name, "decision": str(existing_id)})
    assert str(matched).startswith("Matched existing institution")
    # A name unlike any recorded one is offered nothing, and can match nothing.
    with pytest.raises(findings.FindingError, match="was not offered"):
        call(
            town_discover,
            save,
            **library(
                name="Bibliothèque du comté d'Elm",
                language="fr",
                quote="Bibliothèque du comté d'Elm en français",
                decision=str(existing_id),
            ),
        )
    for wrong in (str(uuid.uuid4()), str(world.town.id)):
        with pytest.raises(findings.FindingError, match="not one of the likely matches"):
            call(town_discover, save, **{**other_name, "decision": wrong})
    # Two names of one institution make one offer, shown under the best-matching name.
    once_more = call(town_discover, save, **other_name)
    assert sum(m.entity_id == existing_id for m in once_more.matches) == 1
    unsure = call(town_discover, save, **{**other_name, "decision": "unsure"})
    assert str(unsure).startswith("Saved institution 'Elm County Public Library'")
    assert "Possible duplicate of" in str(unsure)

    async def check() -> tuple[list[str], list[tuple[str, EntityStatus, bool]]]:
        async with db.session() as session:
            existing = await session.get_one(Institution, existing_id)
            names = [alias.text for alias in await graph.names_of(session, existing)]
            rows = []
            for item in await session.scalars(
                select(ReviewItem).where(ReviewItem.rule == "duplicate")
            ):
                entity = await session.get_one(Institution, item.entity_id)
                rows.append(
                    (entity.name, entity.status, str(existing_id) in item.question["duplicate_of"])
                )
            return names, rows

    names, reviews = db.run(check)
    assert names == ["Elm County Library", "Elm County Public Library"]
    assert reviews == [("Elm County Public Library", EntityStatus.NEEDS_REVIEW, True)]


def test_a_candidate_found_again_on_a_trusted_page_is_verified(
    db: Database, discover: SessionContext, call: Callable[..., Any], capture
):
    """A platform page verifies nothing: the body is a candidate. Named again on a trusted page
    (matched by the agent), it is verified, and the review of one that has a question open
    stands: the status is a human's to move."""
    capture.platform(discover.assignment_id)
    first = call(
        discover,
        findings.record_institution,
        name="Town of Milton",
        language="en",
        institution_type="municipal_government",
        quote="Town of Milton bids",
        page_url=PLATFORM_URL,
    )
    assert "status needs_review" in str(first)  # a government found under a region
    reviewed_id = first.institution_id
    again = call(
        discover,
        findings.record_institution,
        name="Town of Milton",
        language="en",
        institution_type="municipal_government",
        quote="Town of Milton Lower tier",
        page_url=TOWNS_URL,
        decision=str(reviewed_id),
    )
    assert str(again).startswith("Matched existing institution")
    assert "Now verified" not in str(again)

    capture(
        "https://elm.bidsandtenders.ca/transit",
        "<html><body>Elm Transit bids</body></html>",
        "Elm Transit bids and tenders",
        assignment_id=discover.assignment_id,
    )
    candidate = call(
        discover,
        findings.record_institution,
        name="Elm Transit",
        language="en",
        institution_type="transit_agency",
        quote="Elm Transit bids and tenders",
        page_url="https://elm.bidsandtenders.ca/transit",
    )
    assert "status candidate" in str(candidate)
    verified = call(
        discover,
        findings.record_institution,
        name="Elm Transit",
        language="en",
        institution_type="transit_agency",
        quote="Elm Transit is operated by the County of Elm",
        page_url=TOWNS_URL,
        decision=str(candidate.institution_id),
    )
    assert "Now verified: the page is trusted" in str(verified)

    async def check() -> tuple[EntityStatus, int, EntityStatus]:
        async with db.session() as session:
            milton = await session.get_one(Institution, reviewed_id)
            transit = await session.get_one(Institution, candidate.institution_id)
            quotes = await evidence.evidence_for(session, reviewed_id)
            return milton.status, len(quotes), transit.status

    assert db.run(check) == (EntityStatus.NEEDS_REVIEW, 2, EntityStatus.VERIFIED)


def test_a_body_no_type_fits_is_saved_as_other_and_grouped_for_review(
    db: Database, discover: SessionContext, call: Callable[..., Any]
):
    """A public body is never dropped for want of a type: it is saved as `other` with the kind
    the agent took it for, and reviewed under that kind."""
    save = findings.record_institution
    reading_room = library(
        name="Elm Reading Room", quote="Elm Reading Room: the county's reference library."
    )
    with pytest.raises(findings.FindingError, match="needs suggested_type"):
        call(discover, save, **{**reading_room, "institution_type": "other"})
    with pytest.raises(findings.FindingError, match="or 'other' with suggested_type"):
        call(discover, save, **{**reading_room, "institution_type": "reading_room"})
    with pytest.raises(findings.FindingError, match="suggested_type goes with"):
        call(discover, save, **reading_room, suggested_type="research library")
    outcome = call(
        discover,
        save,
        **{**reading_room, "institution_type": "other"},
        suggested_type="  Research   Library ",
    )
    assert str(outcome).startswith("Saved institution 'Elm Reading Room' (other)")
    assert "Sent for review: No listed institution type fits" in str(outcome)
    assert "suggests 'Research Library'" in str(outcome)

    async def check() -> tuple[Institution, ReviewItem]:
        async with db.session() as session:
            institution = (
                await session.scalars(
                    select(Institution).where(Institution.institution_type == "other")
                )
            ).one()
            item = (
                await session.scalars(
                    select(ReviewItem).where(ReviewItem.entity_id == institution.id)
                )
            ).one()
            return institution, item

    institution, item = db.run(check)
    assert institution.status is EntityStatus.NEEDS_REVIEW
    assert institution.suggested_type == "Research Library"
    assert (item.rule, item.kind) == ("new_type", "new_type:research_library")
    assert item.question["suggested_type"] == "Research Library"
    assert item.question["level"] == "region"


def test_a_name_that_misses_its_types_pattern_goes_to_review(
    db: Database,
    world: World,
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    capture: Capture,
    call: Callable[..., Any],
):
    """A directory labels each ministry by its topic. A name that does not match the type's
    pattern is kept and sent to review; the full name from the body's page is not."""
    assignment = make_assignment(FIND_INSTITUTIONS, world.ontario.id)
    capture(
        "https://www.ontario.ca/page/ministries",
        "<html><body>Ministries: Transportation, Health. Ministry of Transportation: moving "
        "people and goods.</body></html>",
        "Ministries: Transportation, Health\nMinistry of Transportation: moving people and goods.",
        assignment_id=assignment.id,
    )
    ctx = context(assignment)
    outcome = call(
        ctx,
        findings.record_institution,
        name="Transportation",
        language="en",
        institution_type="ministry",
        quote="Ministries: Transportation, Health",
        page_url="https://www.ontario.ca/page/ministries",
    )
    assert "does not look like a ministry's name" in str(outcome)
    fine = call(
        ctx,
        findings.record_institution,
        name="Ministry of Transportation",
        language="en",
        institution_type="ministry",
        quote="Ministry of Transportation: moving people and goods.",
        page_url="https://www.ontario.ca/page/ministries",
        decision="new",  # not a duplicate of the label
    )
    assert "Sent for review" not in str(fine)

    async def statuses() -> dict[str, tuple[EntityStatus, str | None]]:
        async with db.session() as session:
            found = {}
            for institution in await session.scalars(
                select(Institution).where(Institution.institution_type == "ministry")
            ):
                item = await session.scalar(
                    select(ReviewItem).where(ReviewItem.entity_id == institution.id)
                )
                found[institution.name] = (institution.status, item.rule if item else None)
            return found

    assert db.run(statuses) == {
        "Transportation": (EntityStatus.NEEDS_REVIEW, "name_pattern"),
        "Ministry of Transportation": (EntityStatus.VERIFIED, None),
    }


def test_a_rejected_institution_takes_no_findings(
    db: Database,
    world: World,
    build: type[Build],
    discover: SessionContext,
    call: Callable[..., Any],
    in_session,
):
    async def make(session) -> Institution:
        elm = await session.get_one(Place, world.elm.id)
        row = await build.candidate_institution(session, elm, "Old Library")
        await status_changes.reject_institution(session, row, entered_by=EnteredBy.MANUAL)
        return row

    rejected = in_session(make)
    with pytest.raises(findings.FindingError, match="was rejected"):
        call(
            discover,
            findings.record_source,
            url=TOWNS_URL,
            source_type="procurement",
            quote="The County of Elm publishes this list.",
            institution_id=str(rejected.id),
        )
    with pytest.raises(findings.FindingError, match="was rejected"):
        call(
            discover,
            findings.record_homepage,
            url=LIBRARY_URL,
            institution_id=str(rejected.id),
            found_on_url=TOWNS_URL,
            link_quote="Elm County Library serves every town.",
        )
