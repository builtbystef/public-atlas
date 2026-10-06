"""`save_source` (spec sections 6.1 and 6.4): verified on trusted pages, checked on platforms
through the trusted page that links there, verified under a platform homepage's trusted path,
and reviewed when the chain is not trusted."""

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select

from public_atlas.modules.agent import findings
from public_atlas.modules.assignments.models import Assignment, AssignmentType
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.evidence.models import EvidenceKind, Snapshot
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import (
    EnteredBy,
    EntityStatus,
    Homepage,
    Institution,
    Source,
    SourceAccess,
    Webpage,
)
from public_atlas.modules.review.models import ReviewItem

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.integration.conftest import Database
    from tests.integration.modules.agent.conftest import Capture
    from tests.integration.modules.conftest import Build, World

    from public_atlas.modules.agent.context import SessionContext

FIND_SOURCES = AssignmentType.FIND_SOURCES
BUSINESS = "https://www.elmcounty.ca/doing-business"
PORTALS = "https://www.elmcounty.ca/tender-portals"
TENDERS = "https://elm.bidsandtenders.ca/Module/Tenders/en"
OTHER = "https://elm.bidsandtenders.ca/other"


@pytest.fixture
def sources(
    world: World,
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    capture: Capture,
) -> SessionContext:
    """A `find_sources` session on the county, with its pages and the portal captured."""
    assignment = make_assignment(FIND_SOURCES, world.county.id)
    capture(
        BUSINESS,
        "<html><body><h1>Doing business with the County of Elm</h1></body></html>",
        "Doing business with the County of Elm\nHow we buy goods and services.",
        assignment_id=assignment.id,
    )
    capture(
        PORTALS,
        "<html><body><h1>Where we post tenders</h1>"
        f'<a href="{TENDERS}"><b>Open</b> tenders</a><a href="{OTHER}">Other</a></body></html>',
        "Where we post tenders\nOpen tenders\nOther",
        assignment_id=assignment.id,
    )
    capture(
        TENDERS,
        "<html><body>County of Elm bids</body></html>",
        "County of Elm\nOpen bid opportunities",
        assignment_id=assignment.id,
    )
    capture(
        OTHER,
        "<html><body>Some other body</body></html>",
        "Some other body\nOpen bid opportunities",
        assignment_id=assignment.id,
    )
    return context(assignment)


def test_sources_are_verified_on_trusted_pages_and_checked_on_platforms(
    db: Database, world: World, sources: SessionContext, capture: Capture, call: Callable[..., Any]
):
    save = findings.record_source
    trusted = call(
        sources,
        save,
        url=BUSINESS,
        source_type="procurement",
        quote="How we buy goods and services",
    )
    assert "status verified" in str(trusted)
    with pytest.raises(findings.FindingError, match="Unknown source type"):
        call(sources, save, url=BUSINESS, source_type="newsletter", quote="How we buy goods")
    with pytest.raises(findings.FindingError, match="'public' or 'login'"):
        call(
            sources,
            save,
            url=BUSINESS,
            source_type="tender",
            quote="How we buy goods",
            access="paid",
        )
    no_link = call(sources, save, url=TENDERS, source_type="tender", quote="Open bid opportunities")
    assert "for review" in str(no_link)
    assert "pass linked_from_url" in str(no_link)
    platform = call(
        sources,
        save,
        url=TENDERS,
        source_type="contract_award",
        quote="Open bid opportunities",
        linked_from_url=PORTALS,
    )
    assert "status verified" in str(platform)
    unnamed = call(
        sources,
        save,
        url=OTHER,
        source_type="tender",
        quote="Open bid opportunities",
        linked_from_url=PORTALS,
    )
    assert "does not name the institution" in str(unnamed)
    # Saved again with what the agent learnt, the access is kept; saved again without the
    # linking page, the source stays verified and no review opens.
    relearnt = call(
        sources,
        save,
        url=TENDERS,
        source_type="contract_award",
        quote="Open bid opportunities",
        access="login",
        linked_from_url=PORTALS,
    )
    assert str(relearnt).startswith("Already recorded source contract_award")
    weaker = call(
        sources, save, url=TENDERS, source_type="contract_award", quote="Open bid opportunities"
    )
    assert "is already verified" in str(weaker)
    # A page on a domain that is neither trusted nor a platform is no source.
    capture.page(
        "https://www.oakville.ca/", "Tenders of the Town of Oakville", sources.assignment_id
    )
    with pytest.raises(findings.FindingError, match="not trusted and is not a platform"):
        call(
            sources,
            save,
            url="https://www.oakville.ca/",
            source_type="tender",
            quote="Tenders of the Town of Oakville",
        )

    async def check() -> tuple[list[tuple[str, EntityStatus, SourceAccess]], list, int]:
        async with db.session() as session:
            rows = await session.scalars(select(Source).order_by(Source.created_at))
            found = [(s.source_type, s.status, s.access) for s in rows]
            portal = (
                await session.scalars(select(Source).where(Source.source_type == "contract_award"))
            ).one()
            quotes = []
            for row in await evidence.evidence_for(session, portal.id):
                snapshot = await session.get_one(Snapshot, row.snapshot_id)
                page = await session.get_one(Webpage, snapshot.webpage_id)
                quotes.append((row.kind, row.quote, row.link_url, page.url))
            reviews = len((await session.scalars(select(ReviewItem))).all())
            return found, quotes, reviews

    found, quotes, reviews = db.run(check)
    assert found == [
        ("procurement", EntityStatus.VERIFIED, SourceAccess.PUBLIC),
        ("tender", EntityStatus.NEEDS_REVIEW, SourceAccess.PUBLIC),
        ("contract_award", EntityStatus.VERIFIED, SourceAccess.PUBLIC),
        ("tender", EntityStatus.NEEDS_REVIEW, SourceAccess.PUBLIC),
    ]
    assert reviews == 2  # the two tender pages, not the re-saved portal
    assert quotes[:2] == [
        (EvidenceKind.APPEARS_ON, "Open bid opportunities", None, TENDERS),
        # The link's own wording, with its tags stripped, against the trusted page's copy.
        (EvidenceKind.LINKS_TO, "Open tenders", TENDERS, PORTALS),
    ]


def test_a_platform_page_reached_through_a_redirect_counts_as_linked(
    db: Database,
    world: World,
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    capture: Capture,
    call: Callable[..., Any],
    in_session,
):
    """A trusted page links a portal address that answers from another one. The agent cites
    where it landed, and the redirect the browser recorded joins the two."""
    assignment = make_assignment(FIND_SOURCES, world.county.id)
    ctx = context(assignment)
    capture(
        "https://www.elmcounty.ca/tenders",
        '<html><body><a href="https://portal.biddingo.com/landingpage/elm">Bids</a></body></html>',
        "Bids",
        assignment_id=assignment.id,
    )
    capture(
        "https://biddingo.com/elm",
        "<html><body>County of Elm bids</body></html>",
        "County of Elm\nOpen bid opportunities",
        assignment_id=assignment.id,
    )
    unlinked = call(
        ctx,
        findings.record_source,
        url="https://biddingo.com/elm",
        source_type="tender",
        quote="Open bid opportunities",
        linked_from_url="https://www.elmcounty.ca/tenders",
    )
    assert "has no link to" in str(unlinked)

    async def redirected(session) -> None:
        await evidence.record_redirect(
            session,
            requested="https://portal.biddingo.com/landingpage/elm",
            landed="https://biddingo.com/elm",
            assignment_id=assignment.id,
        )

    in_session(redirected)
    linked = call(
        ctx,
        findings.record_source,
        url="https://biddingo.com/elm",
        source_type="contract_award",
        quote="Open bid opportunities",
        linked_from_url="https://www.elmcounty.ca/tenders",
    )
    assert "status verified" in str(linked)


def test_a_page_under_a_platform_homepages_trusted_path_is_verified(
    db: Database,
    world: World,
    build: type[Build],
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    capture: Capture,
    call: Callable[..., Any],
    in_session,
):
    """The town's verified homepage is on a platform: the pages under its path vouch for the
    town as a trusted domain's would (spec section 6.4), and the rest of the platform does not."""
    home = "https://elm.bidsandtenders.ca/oakville/home"

    async def verified_on_platform(session) -> Homepage:
        town = await session.get_one(Institution, world.town.id)
        claim = await build.claim(session, town, home)
        await status_changes.verify_homepage(session, claim, entered_by=EnteredBy.MANUAL)
        return claim

    claim = in_session(verified_on_platform)
    assert claim.trusted_path == "https://elm.bidsandtenders.ca/oakville/"
    assignment = make_assignment(FIND_SOURCES, world.town.id)
    ctx = context(assignment)
    under = "https://elm.bidsandtenders.ca/oakville/tenders"
    elsewhere = "https://elm.bidsandtenders.ca/milton/tenders"
    for url in (under, elsewhere):
        capture.page(url, "Open bid opportunities for suppliers", assignment.id)
    verified = call(
        ctx, findings.record_source, url=under, source_type="tender", quote="Open bid opportunities"
    )
    assert "status verified" in str(verified)
    reviewed = call(
        ctx,
        findings.record_source,
        url=elsewhere,
        source_type="tender",
        quote="Open bid opportunities",
    )
    assert "for review" in str(reviewed)

    async def statuses() -> dict[str, EntityStatus]:
        async with db.session() as session:
            found = {}
            for source in await session.scalars(
                select(Source).where(Source.institution_id == world.town.id)
            ):
                webpage = await session.get_one(Webpage, source.webpage_id)
                found[webpage.url] = source.status
            return found

    assert db.run(statuses) == {under: EntityStatus.VERIFIED, elsewhere: EntityStatus.NEEDS_REVIEW}


def test_a_source_needs_an_institution_and_a_quote_from_the_page(
    db: Database, world: World, sources: SessionContext, call: Callable[..., Any]
):
    with pytest.raises(findings.FindingError, match="not found word for word"):
        call(
            sources,
            findings.record_source,
            url=BUSINESS,
            source_type="procurement",
            quote="How we sell goods",
        )
    with pytest.raises(findings.FindingError, match="No institution with id"):
        call(
            sources,
            findings.record_source,
            url=BUSINESS,
            source_type="procurement",
            quote="How we buy goods and services",
            institution_id=str(uuid.uuid4()),
        )
    # Another institution's source, from the same session.
    outcome = call(
        sources,
        findings.record_source,
        url=BUSINESS,
        source_type="procurement",
        quote="How we buy goods and services",
        institution_id=str(world.town.id),
    )
    assert outcome.source_id != uuid.UUID(int=0)

    async def owner() -> uuid.UUID:
        async with db.session() as session:
            return (await session.get_one(Source, outcome.source_id)).institution_id

    assert db.run(owner) == world.town.id
    assert graph.is_domain_name("elmcounty.ca")
