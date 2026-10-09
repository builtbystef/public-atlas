"""`save_homepage` and the domain decisions of a `find_homepage` session (spec sections 6.3, 6.4
and 7.2): a homepage on a trusted domain or a platform is verified from its own text, a link to
a new domain makes a candidate, and `confirm_domain`, `reject_domain` and `domain_moved` run
every check and set the follow-up work in motion."""

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select

from public_atlas.modules.agent import findings
from public_atlas.modules.agent.findings import MAX_CONFIRM_ATTEMPTS, Quote
from public_atlas.modules.assignments import lifecycle
from public_atlas.modules.assignments import service as assignments
from public_atlas.modules.assignments.models import Assignment, AssignmentResult, AssignmentType
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.evidence.models import EvidenceKind
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import (
    Domain,
    EnteredBy,
    EntityStatus,
    Homepage,
    Institution,
    Place,
    Webpage,
)
from public_atlas.modules.review.models import ReviewItem

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.integration.conftest import Database
    from tests.integration.modules.agent.conftest import Capture
    from tests.integration.modules.conftest import Build, World

    from public_atlas.modules.agent.context import SessionContext


TOWNS_URL = "https://www.elmcounty.ca/towns"
LIBRARY_URL = "https://www.elmcounty.ca/library"
PLATFORM_URL = "https://elm.bidsandtenders.ca/list"
FIND_HOMEPAGE = AssignmentType.FIND_HOMEPAGE
FIND_INSTITUTIONS = AssignmentType.FIND_INSTITUTIONS
OAKVILLE = "https://www.oakville.ca/"


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


@pytest.fixture
def library(db: Database, world: World, build: type[Build]) -> Institution:
    """A verified library under Elm with no homepage yet."""

    async def make() -> Institution:
        async with db.session() as session:
            elm = await session.get_one(Place, world.elm.id)
            row = await build.candidate_institution(session, elm, "Elm County Library")
            await status_changes.verify_institution(session, row, entered_by=EnteredBy.SCRIPT)
            await session.commit()
            return row

    return db.run(make)


def homepage_of(db: Database, institution_id: uuid.UUID) -> tuple[Institution, list[Homepage]]:
    async def read() -> tuple[Institution, list[Homepage]]:
        async with db.session() as session:
            row = await session.get_one(Institution, institution_id)
            return row, await graph.homepages_of(session, row)

    return db.run(read)


def spawned_for(db: Database, subject_id: uuid.UUID) -> list[tuple[AssignmentType, str]]:
    async def read() -> list[tuple[AssignmentType, str]]:
        async with db.session() as session:
            rows = await assignments.list_assignments(session, subject_id=subject_id)
            return [
                (row.type, row.status.value) for row in rows if row.parent_assignment_id is not None
            ]

    return db.run(read)


# --- save_homepage ---


def test_a_homepage_on_a_trusted_domain_is_verified_from_its_own_text(
    db: Database,
    world: World,
    discover: SessionContext,
    library: Institution,
    capture: Capture,
    call: Callable[..., Any],
):
    """The towns page's link gets the claim in and proves nothing about what the page is. The
    agent has to open the page, judge it the institution's own, and quote it; the quote must
    name the institution."""
    claim = {
        "institution_id": str(library.id),
        "url": LIBRARY_URL,
        "found_on_url": TOWNS_URL,
        "link_quote": "Elm County Library serves every town.",
    }
    with pytest.raises(findings.FindingError, match="link_quote goes with found_on_url"):
        call(
            discover,
            findings.record_homepage,
            url=LIBRARY_URL,
            institution_id=str(library.id),
            link_quote="x" * 12,
        )
    with pytest.raises(findings.FindingError, match="Pass found_on_url"):
        call(discover, findings.record_homepage, url=LIBRARY_URL, institution_id=str(library.id))
    with pytest.raises(findings.FindingError, match="has no link to"):
        call(discover, findings.record_homepage, **{**claim, "url": "https://www.elmcounty.ca/x"})
    unread = call(discover, findings.record_homepage, **claim)
    assert str(unread).startswith(
        f"Recorded {LIBRARY_URL} as a candidate homepage; elmcounty.ca is trusted"
    )
    assert "call save_homepage again with page_quote" in str(unread)
    with pytest.raises(findings.FindingError, match="has not been opened"):
        call(discover, findings.record_homepage, **claim, page_quote="Elm County Library")
    capture.library(discover.assignment_id)
    with pytest.raises(findings.FindingError, match="does not name the institution"):
        call(
            discover,
            findings.record_homepage,
            **claim,
            page_quote="serves every town of the county",
        )
    with pytest.raises(findings.FindingError, match="not found word for word"):
        call(discover, findings.record_homepage, **claim, page_quote="Elm County Library, Ontario")
    institution, claims = homepage_of(db, library.id)
    assert institution.homepage_id is None
    assert [c.status for c in claims] == [EntityStatus.CANDIDATE]

    verified = call(discover, findings.record_homepage, **claim, page_quote="Elm County Library")
    assert str(verified).startswith(
        f"Verified {LIBRARY_URL} as the homepage of 'Elm County Library' (elmcounty.ca is trusted)"
    )
    assert "Queued: find_sources (held)" in str(verified)

    async def check() -> tuple[Institution, list[tuple[EvidenceKind, str, str]]]:
        async with db.session() as session:
            row = await session.get_one(Institution, library.id)
            assert row.homepage_id is not None
            homepage = await session.get_one(Homepage, row.homepage_id)
            on = {}
            for url in (TOWNS_URL, LIBRARY_URL):
                webpage = await graph.webpage_by_url(session, url)
                assert webpage is not None
                snapshot = await evidence.latest_snapshot(session, webpage.id)
                assert snapshot is not None
                on[snapshot.id] = url
            rows = await evidence.evidence_for(session, homepage.id)
            return row, [(r.kind, r.quote, on[r.snapshot_id]) for r in rows]

    institution, rows = db.run(check)
    assert institution.homepage_id == claims[0].id
    # One quote on the towns page, around the link; one on the library's own page, naming it.
    assert rows == [
        (EvidenceKind.LINKS_TO, "Elm County Library serves every town.", TOWNS_URL),
        (EvidenceKind.APPEARS_ON, "Elm County Library", LIBRARY_URL),
    ]
    assert spawned_for(db, library.id) == [(AssignmentType.FIND_SOURCES, "held")]
    again = call(discover, findings.record_homepage, **claim, page_quote="Elm County Library")
    assert str(again).endswith("is the verified homepage of 'Elm County Library' already.")
    with pytest.raises(findings.FindingError, match="has a verified homepage already"):
        call(
            discover, findings.record_homepage, **{**claim, "url": "https://www.elmcounty.ca/lib2"}
        )


def test_a_link_to_a_new_domain_makes_a_candidate_a_find_homepage_assignment_decides(
    db: Database,
    world: World,
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    capture: Capture,
    call: Callable[..., Any],
):
    """From a discovery session on the town the claim is recorded as a candidate; the
    `find_homepage` assignment spawned at its finish starts out with the candidate to decide."""
    discover = context(make_assignment(FIND_INSTITUTIONS, world.oakville.id))
    capture.towns(discover.assignment_id)
    outcome = call(
        discover,
        findings.record_institution,
        name="Town of Oakville",
        language="en",
        institution_type="municipal_government",
        quote="Town of Oakville Lower tier",
        page_url=TOWNS_URL,
        decision=str(world.town.id),
        homepage_url="https://www.oakville.ca",
    )
    assert "oakville.ca is a candidate domain, which a find_homepage assignment for" in str(outcome)
    assert "No trusted page links to it" not in str(outcome)

    async def check() -> tuple[Domain, Homepage, Webpage]:
        async with db.session() as session:
            domain = await graph.domain_by_name(session, "oakville.ca")
            assert domain is not None
            claim = (
                await session.scalars(
                    select(Homepage).where(Homepage.institution_id == world.town.id)
                )
            ).one()
            return domain, claim, await session.get_one(Webpage, claim.webpage_id)

    domain, claim, webpage = db.run(check)
    # Stored without the `www.`: the allowlist admits any host under oakville.ca.
    assert (domain.status, domain.domain_kind.value) == (EntityStatus.CANDIDATE, "official")
    assert claim.status is EntityStatus.CANDIDATE
    assert claim.found_on_webpage_id is not None
    assert webpage.url == OAKVILLE
    assert webpage.domain_id == domain.id

    finished = call(
        discover,
        findings.finish_assignment,
        summary="Only the town.",
        types_not_found=world.rules.expected_institution_types("municipality"),
    )
    assert finished.result is AssignmentResult.COMPLETE
    assert discover.ended is not None

    async def spawn_it() -> Assignment:
        async with db.session() as session:
            row = await session.get_one(Assignment, discover.assignment_id)
            lifecycle.start(row)
            lifecycle.finish(row, AssignmentResult.COMPLETE)
            (spawned,) = await assignments.spawn_on_finish(session, discover.jobs, row)
            await session.commit()
            return spawned

    spawned = db.run(spawn_it)
    assert (spawned.type, spawned.subject_id, spawned.status.value) == (
        FIND_HOMEPAGE,
        world.town.id,
        "held",
    )
    ctx = context(spawned)
    assert ctx.candidate is not None
    assert (ctx.candidate.domain_id, ctx.candidate.homepage_id) == (domain.id, claim.id)
    assert "oakville.ca" in ctx.allowed_domains


def test_a_claim_from_an_untrusted_page_has_no_linking_page_on_record(
    db: Database,
    world: World,
    discover: SessionContext,
    capture: Capture,
    call: Callable[..., Any],
):
    """A link on a platform page proves nothing by itself, so the claim has no linking page."""
    capture.platform(discover.assignment_id)
    milton = call(
        discover,
        findings.record_institution,
        name="Town of Milton",
        language="en",
        institution_type="municipal_government",
        quote="Town of Milton Lower tier",
        page_url=TOWNS_URL,
    )
    untrusted = call(
        discover,
        findings.record_homepage,
        institution_id=str(milton.institution_id),
        url="https://www.milton.ca/",
        found_on_url=PLATFORM_URL,
        link_quote="Town of Milton bids",
    )
    assert "milton.ca is a candidate domain" in str(untrusted)
    assert "No trusted page links to it" in str(untrusted)
    _, claims = homepage_of(db, milton.institution_id)
    assert [(c.status, c.found_on_webpage_id) for c in claims] == [(EntityStatus.CANDIDATE, None)]
    # A trusted page's link found later is recorded on the same claim.
    capture(
        "https://www.elmcounty.ca/milton",
        '<p><a href="https://www.milton.ca/">Town of Milton</a> website</p>',
        "Town of Milton website",
        assignment_id=discover.assignment_id,
    )
    trusted = call(
        discover,
        findings.record_homepage,
        institution_id=str(milton.institution_id),
        url="https://www.milton.ca/",
        found_on_url="https://www.elmcounty.ca/milton",
        link_quote="Town of Milton website",
    )
    assert "No trusted page links to it" not in str(trusted)
    _, claims = homepage_of(db, milton.institution_id)
    assert [c.found_on_webpage_id is not None for c in claims] == [True]


def test_a_homepage_on_a_platform_needs_a_trusted_link_and_its_own_text(
    db: Database,
    world: World,
    discover: SessionContext,
    library: Institution,
    capture: Capture,
    call: Callable[..., Any],
):
    """The same rule on a platform, with one more: a trusted page must link to it. Verified,
    the homepage carries its trusted path (spec section 6.4)."""
    portal = "https://elm.bidsandtenders.ca/library/home"
    capture(
        "https://www.elmcounty.ca/portals",
        f'<p><a href="{portal}">Elm County Library</a> bids</p>',
        "Elm County Library bids",
        assignment_id=discover.assignment_id,
    )
    capture.page(portal, "Bids and tenders of the Elm County Library", discover.assignment_id)
    claim = {"institution_id": str(library.id), "url": portal}
    # No linking page and no page text: a candidate the session may not open on its own.
    with pytest.raises(findings.FindingError, match="Pass found_on_url"):
        call(discover, findings.record_homepage, **claim)
    unread = call(
        discover,
        findings.record_homepage,
        **claim,
        found_on_url="https://www.elmcounty.ca/portals",
        link_quote="Elm County Library bids",
    )
    assert "bidsandtenders.ca is a platform, so the page is verified from its own text" in str(
        unread
    )
    verified = call(
        discover,
        findings.record_homepage,
        **claim,
        found_on_url="https://www.elmcounty.ca/portals",
        link_quote="Elm County Library bids",
        page_quote="Bids and tenders of the Elm County Library",
    )
    assert "bidsandtenders.ca is a platform and a trusted page links to it" in str(verified)
    institution, claims = homepage_of(db, library.id)
    assert institution.homepage_id == claims[0].id
    assert claims[0].trusted_path == "https://elm.bidsandtenders.ca/library/"


def test_a_platform_homepage_no_trusted_page_links_to_goes_to_review(
    db: Database,
    world: World,
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    capture: Capture,
    call: Callable[..., Any],
):
    """A `find_homepage` session finds the town's portal page by search: the page names the
    town, but with no trusted link a human decides."""
    portal = "https://elm.bidsandtenders.ca/oakville/home"
    ctx = context(make_assignment(FIND_HOMEPAGE, world.town.id))
    ctx.search_hosts.add("bidsandtenders.ca")
    capture.page(portal, "Bids of the Town of Oakville", ctx.assignment_id)
    outcome = call(
        ctx, findings.record_homepage, url=portal, page_quote="Bids of the Town of Oakville"
    )
    assert "sent to review" in str(outcome)

    async def check() -> tuple[list[EntityStatus], ReviewItem]:
        async with db.session() as session:
            town = await session.get_one(Institution, world.town.id)
            claims = await graph.homepages_of(session, town)
            item = (await session.scalars(select(ReviewItem))).one()
            return [c.status for c in claims], item

    statuses, item = db.run(check)
    assert statuses == [EntityStatus.NEEDS_REVIEW]
    assert item.rule == "platform_homepage"
    assert item.question["platform"] == "bidsandtenders.ca"


# --- The domain decisions ---


@pytest.fixture
def finding(
    world: World,
    claimed: Callable[..., Homepage],
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
) -> tuple[SessionContext, Homepage]:
    """A `find_homepage` session on the town, with its candidate on oakville.ca found on the
    county's trusted towns page."""
    claim = claimed(world.town)
    ctx = context(make_assignment(FIND_HOMEPAGE, world.town.id))
    assert ctx.candidate is not None
    assert ctx.candidate.homepage_id == claim.id
    assert ctx.allowed_domains[-1] == "oakville.ca"
    return ctx, claim


def domain_status(db: Database, name: str) -> EntityStatus:
    async def read() -> EntityStatus:
        async with db.session() as session:
            domain = await graph.domain_by_name(session, name)
            assert domain is not None
            return domain.status

    return db.run(read)


def test_confirm_domain_verifies_the_domain_and_the_homepage_and_spawns(
    db: Database,
    world: World,
    build: type[Build],
    finding: tuple[SessionContext, Homepage],
    capture: Capture,
    call: Callable[..., Any],
    in_session,
):
    ctx, claim = finding
    capture.page(OAKVILLE, "Welcome to the Town of Oakville\n© Town of Oakville", ctx.assignment_id)
    capture.page(
        "https://www.oakville.ca/contact",
        "Contact the Town of Oakville at 1225 Trafalgar Road",
        ctx.assignment_id,
    )
    # The towns page is captured again without the link: the check must read the copy the link
    # evidence cites, not whichever copy is newest.
    capture(TOWNS_URL, "<html><body>Towns of Elm County</body></html>", capture.TOWNS_TEXT)

    # A second claim on the domain by another body, with no linking page: the domain's
    # verification must not sweep it up.
    async def claim_from_nowhere(session) -> Institution:
        oakville = await session.get_one(Place, world.oakville.id)
        other = await build.candidate_institution(session, oakville, "Oakville Library")
        await build.claim(session, other, "https://www.oakville.ca/library")
        return other

    other = in_session(claim_from_nowhere)
    outcome = call(
        ctx,
        findings.confirm_candidate,
        quotes=[
            Quote(url=OAKVILLE, quote="Welcome to the Town of Oakville"),
            Quote(url="https://www.oakville.ca/contact", quote="1225 Trafalgar Road"),
        ],
    )
    assert str(outcome).startswith(
        "Verified oakville.ca as an official domain of 'Town of Oakville'"
    )
    assert "Queued: find_sources (held), find_institutions (held)" in str(outcome)
    assert ctx.ended is not None
    assert ctx.ended.result is AssignmentResult.COMPLETE
    assert ctx.candidate is None

    async def check() -> tuple[Domain, Institution, Homepage, Institution, list[str]]:
        async with db.session() as session:
            domain = await graph.domain_by_name(session, "oakville.ca")
            assert domain is not None
            town = await session.get_one(Institution, world.town.id)
            homepage = await session.get_one(Homepage, claim.id)
            library = await session.get_one(Institution, other.id)
            quotes = [row.quote for row in await evidence.evidence_for(session, domain.id)]
            return domain, town, homepage, library, quotes

    domain, town, homepage, library, quotes = db.run(check)
    assert (domain.status, domain.entered_by.value) == (EntityStatus.VERIFIED, "agent")
    assert graph.is_trusted(domain)
    assert (homepage.status, town.homepage_id) == (EntityStatus.VERIFIED, claim.id)
    assert library.homepage_id is None
    assert quotes == ["Welcome to the Town of Oakville", "1225 Trafalgar Road"]
    assert spawned_for(db, world.town.id) == [(AssignmentType.FIND_SOURCES, "held")]
    assert spawned_for(db, world.oakville.id) == [(FIND_INSTITUTIONS, "held")]


def test_confirm_domain_sends_a_fixable_failure_back_then_the_domain_to_review(
    db: Database,
    world: World,
    finding: tuple[SessionContext, Homepage],
    capture: Capture,
    call: Callable[..., Any],
):
    """A quote that is not word for word, or a page never opened, is the agent's to fix; the
    domain goes to a human only on the third failed call, and the assignment ends
    `needs_review`: the agent and the checks disagree."""
    ctx, claim = finding
    capture.page(OAKVILLE, "Welcome to the Town of Oakville, on the lake", ctx.assignment_id)
    with pytest.raises(findings.FindingError, match="attempt 1 of 3") as first:
        call(
            ctx,
            findings.confirm_candidate,
            quotes=[Quote(url=OAKVILLE, quote="Welcome to Town of Oakville")],
        )
    assert "closest text on that page" in str(first.value)
    with pytest.raises(findings.FindingError, match="attempt 2 of 3") as second:
        call(
            ctx,
            findings.confirm_candidate,
            quotes=[Quote(url="https://www.oakville.ca/about", quote="Town of Oakville")],
        )
    assert "has not been opened" in str(second.value)
    assert f"Pages opened on www.oakville.ca: {OAKVILLE}" in str(second.value)
    assert ctx.confirm_attempts == MAX_CONFIRM_ATTEMPTS - 1
    outcome = call(
        ctx,
        findings.confirm_candidate,
        quotes=[Quote(url=OAKVILLE, quote="Welcome to our fine town")],
    )
    assert "goes to a human" in str(outcome)
    assert "quote not found" in str(outcome)
    assert ctx.ended is not None
    assert ctx.ended.result is AssignmentResult.NEEDS_REVIEW

    async def check() -> tuple[EntityStatus, ReviewItem]:
        async with db.session() as session:
            homepage = await session.get_one(Homepage, claim.id)
            item = (await session.scalars(select(ReviewItem))).one()
            return homepage.status, item

    status, item = db.run(check)
    assert domain_status(db, "oakville.ca") is EntityStatus.NEEDS_REVIEW
    assert status is EntityStatus.NEEDS_REVIEW
    assert (item.rule, item.question["homepage_id"]) == ("domain_checks", str(claim.id))


def test_a_claim_no_trusted_page_links_to_is_confirmed_by_a_human(
    db: Database,
    world: World,
    claimed: Callable[..., Homepage],
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    capture: Capture,
    call: Callable[..., Any],
):
    """The quotes are checked and kept, but with no trusted link behind the claim the
    confirmation goes to a human; the agent and the checks agree, so the assignment ends
    `complete` (spec section 7.2)."""
    claim = claimed(world.town, found_on=False)
    ctx = context(make_assignment(FIND_HOMEPAGE, world.town.id))
    capture.page(OAKVILLE, "Welcome to the Town of Oakville", ctx.assignment_id)
    outcome = call(
        ctx,
        findings.confirm_candidate,
        quotes=[Quote(url=OAKVILLE, quote="Welcome to the Town of Oakville")],
    )
    assert "goes to a human" in str(outcome)
    assert "found by a web search or on an untrusted page" in str(outcome)
    assert ctx.ended is not None
    assert ctx.ended.result is AssignmentResult.COMPLETE

    async def check() -> tuple[int, EntityStatus]:
        async with db.session() as session:
            domain = await graph.domain_by_name(session, "oakville.ca")
            assert domain is not None
            kept = await evidence.evidence_for(session, domain.id)
            return len(kept), (await session.get_one(Homepage, claim.id)).status

    assert db.run(check) == (1, EntityStatus.NEEDS_REVIEW)


def test_a_claim_an_official_list_links_to_is_verified_without_a_human(
    db: Database,
    world: World,
    build: type[Build],
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    capture: Capture,
    call: Callable[..., Any],
    in_session,
):
    """The loader records a government's homepage from a directory on a trusted domain with the
    directory line as the link quote and no page it was found on: that line is the trusted
    link, and the session's confirmation verifies the domain."""
    directory = "https://data.ontario.ca/dataset/municipalities.csv"
    _, snapshot = capture(
        directory,
        "name,website\nOakville,http://www.oakville.ca/\n",
        "name,website\nOakville,http://www.oakville.ca/\n",
    )

    async def loaded(session) -> Homepage:
        town = await session.get_one(Institution, world.town.id)
        claim = await build.claim(session, town, OAKVILLE)
        await evidence.add_evidence(
            session,
            entity_id=claim.id,
            snapshot=snapshot,
            kind=EvidenceKind.LINKS_TO,
            quote="Oakville,http://www.oakville.ca/",
            entered_by=EnteredBy.SCRIPT,
            locator=2,
            link_url=OAKVILLE,
        )
        return claim

    claim = in_session(loaded)
    assert claim.found_on_webpage_id is None
    ctx = context(make_assignment(FIND_HOMEPAGE, world.town.id))
    capture.page(OAKVILLE, "Welcome to the Town of Oakville", ctx.assignment_id)
    outcome = call(
        ctx,
        findings.confirm_candidate,
        quotes=[Quote(url=OAKVILLE, quote="Welcome to the Town of Oakville")],
    )
    assert str(outcome).startswith("Verified oakville.ca as an official domain")
    institution, _ = homepage_of(db, world.town.id)
    assert institution.homepage_id == claim.id


def test_confirm_domain_accepts_the_name_the_site_uses(
    db: Database,
    world: World,
    finding: tuple[SessionContext, Homepage],
    capture: Capture,
    call: Callable[..., Any],
    in_session,
):
    """The directory records "Town of Oakville"; the site writes "Oakville Township" (the place
    name with another designator) or the opening words of a longer recorded name. Those count,
    and are saved as a name."""
    ctx, _ = finding
    capture.page(OAKVILLE, "Welcome to Oakville Township, on the lake", ctx.assignment_id)
    quotes = [Quote(url=OAKVILLE, quote="Welcome to Oakville Township")]
    with pytest.raises(findings.FindingError, match="too short"):
        call(ctx, findings.confirm_candidate, quotes=quotes, name_used="Township")
    with pytest.raises(
        findings.FindingError, match="nor is it one of them with another designator"
    ):
        call(ctx, findings.confirm_candidate, quotes=quotes, name_used="Oakville Falls Township")
    outcome = call(ctx, findings.confirm_candidate, quotes=quotes, name_used="Oakville Township")
    assert str(outcome).startswith("Verified oakville.ca as an official domain")

    async def names() -> list[str]:
        async with db.session() as session:
            town = await session.get_one(Institution, world.town.id)
            return [alias.text for alias in await graph.names_of(session, town)]

    assert db.run(names) == ["Oakville Township", "Town of Oakville"]


def test_a_quote_cited_by_the_redirected_from_url_is_read_on_the_page_that_answered(
    db: Database,
    finding: tuple[SessionContext, Homepage],
    capture: Capture,
    call: Callable[..., Any],
    in_session,
):
    ctx, _ = finding
    capture.page(
        "https://www.oakville.ca/en/contact", "Contact the Town of Oakville", ctx.assignment_id
    )

    async def redirected(session) -> None:
        await evidence.record_redirect(
            session,
            requested="https://www.oakville.ca/contact",
            landed="https://www.oakville.ca/en/contact",
            assignment_id=ctx.assignment_id,
        )

    in_session(redirected)
    outcome = call(
        ctx,
        findings.confirm_candidate,
        quotes=[Quote(url="https://www.oakville.ca/contact", quote="Contact the Town of Oakville")],
    )
    assert str(outcome).startswith("Verified oakville.ca as an official domain")


def test_domain_moved_follows_a_recorded_redirect_to_a_new_candidate(
    db: Database,
    world: World,
    finding: tuple[SessionContext, Homepage],
    capture: Capture,
    call: Callable[..., Any],
    in_session,
):
    """`domain_moved` passes the claim to the page the old address redirects to, which becomes
    the session's candidate. The redirect must be on record; the agent's word is not enough."""
    ctx, claim = finding
    with pytest.raises(findings.FindingError, match="is on record as redirecting"):
        call(ctx, findings.candidate_moved, url="https://www.oakville.on.ca/en")

    async def redirected(session) -> None:
        await evidence.record_redirect(
            session,
            requested=OAKVILLE,
            landed="https://www.oakville.on.ca/en",
            assignment_id=ctx.assignment_id,
        )

    in_session(redirected)
    with pytest.raises(findings.FindingError, match="is on record as redirecting"):
        call(ctx, findings.candidate_moved, url="https://www.oakville.on.ca/fr")
    outcome = call(ctx, findings.candidate_moved, url="https://www.oakville.on.ca/en")
    assert f"{OAKVILLE} redirects to https://www.oakville.on.ca/en" in str(outcome)
    assert "oakville.on.ca is now this session's candidate" in str(outcome)
    assert ctx.ended is None
    candidate = ctx.candidate
    assert candidate is not None
    assert candidate.domain_name == "oakville.on.ca"
    assert "oakville.on.ca" in ctx.allowed_domains
    assert "oakville.ca" not in ctx.allowed_domains

    async def check() -> tuple[Homepage, Homepage, list[tuple[EvidenceKind, str, str | None]]]:
        async with db.session() as session:
            old = await session.get_one(Homepage, claim.id)
            new = await session.get_one(Homepage, candidate.homepage_id)
            rows = await evidence.evidence_for(session, new.id)
            return old, new, [(r.kind, r.quote, r.link_url) for r in rows]

    old, new, rows = db.run(check)
    assert domain_status(db, "oakville.ca") is EntityStatus.REJECTED
    assert (old.status, old.rejected_reason) == (
        EntityStatus.REJECTED,
        "redirects to https://www.oakville.on.ca/en",
    )
    assert new.status is EntityStatus.CANDIDATE
    assert new.found_on_webpage_id == claim.found_on_webpage_id
    # The trusted page's link to the old URL vouches for the new one.
    assert rows == [(EvidenceKind.LINKS_TO, "Town of Oakville", OAKVILLE)]

    # The session follows the move and confirms the new domain: the recorded redirect carries
    # the trusted link to the new address.
    capture.page(
        "https://www.oakville.on.ca/en", "Welcome to the Town of Oakville", ctx.assignment_id
    )
    confirmed = call(
        ctx,
        findings.confirm_candidate,
        quotes=[
            Quote(url="https://www.oakville.on.ca/en", quote="Welcome to the Town of Oakville")
        ],
    )
    assert str(confirmed).startswith("Verified oakville.on.ca as an official domain")
    institution, _ = homepage_of(db, world.town.id)
    assert institution.homepage_id == new.id


def test_domain_moved_to_a_trusted_domain_verifies_the_homepage_there(
    db: Database,
    world: World,
    finding: tuple[SessionContext, Homepage],
    call: Callable[..., Any],
    in_session,
):
    """The listed address is dead but the domain's bare home page forwards to a page on the
    county's trusted site; that redirect counts as the site moving, and the page is verified."""
    ctx, _ = finding

    async def redirected(session) -> None:
        await evidence.record_redirect(
            session,
            requested="http://oakville.ca/",
            landed="https://www.elmcounty.ca/oakville",
            assignment_id=ctx.assignment_id,
        )

    in_session(redirected)
    outcome = call(ctx, findings.candidate_moved, url="https://www.elmcounty.ca/oakville")
    assert "elmcounty.ca is trusted, so https://www.elmcounty.ca/oakville is verified" in str(
        outcome
    )
    assert ctx.ended is not None
    assert ctx.ended.result is AssignmentResult.COMPLETE
    institution, claims = homepage_of(db, world.town.id)
    assert institution.homepage_id is not None
    assert sorted(c.status.value for c in claims) == ["rejected", "verified"]
    assert spawned_for(db, world.oakville.id) == [(FIND_INSTITUTIONS, "held")]


def test_reject_domain_rejects_the_site_and_the_session_keeps_looking(
    db: Database,
    world: World,
    build: type[Build],
    finding: tuple[SessionContext, Homepage],
    call: Callable[..., Any],
    in_session,
):
    """The domain is rejected, every body that claimed a homepage on it looks again, and this
    session keeps looking itself. With `another_body` only this claim is withdrawn."""
    ctx, claim = finding

    async def other_claim(session) -> Institution:
        oakville = await session.get_one(Place, world.oakville.id)
        library = await build.candidate_institution(session, oakville, "Oakville Library")
        await build.claim(session, library, "https://www.oakville.ca/library")
        return library

    library = in_session(other_claim)
    outcome = call(ctx, findings.reject_candidate, reason="the host does not resolve")
    assert str(outcome).startswith("Rejected oakville.ca: the host does not resolve.")
    assert "Queued: find_homepage (held)" in str(outcome)
    assert "Keep looking" in str(outcome)
    assert ctx.ended is None
    assert ctx.candidate is None
    assert "oakville.ca" not in ctx.allowed_domains
    assert domain_status(db, "oakville.ca") is EntityStatus.REJECTED
    # The library's claim went with the domain and it looks again; the town's own search is
    # this assignment, so nothing new is queued for it.
    assert spawned_for(db, library.id) == [(FIND_HOMEPAGE, "held")]
    assert spawned_for(db, world.town.id) == []
    with pytest.raises(findings.FindingError, match="No candidate to decide on"):
        call(ctx, findings.reject_candidate, reason="nothing saved yet")

    # Another body's site: the claim is withdrawn, the domain stays a candidate.
    second = claimed_again(db, world, build, ctx)
    withdrawn = call(
        ctx, findings.reject_candidate, reason="it is the Township of Oakville's", another_body=True
    )
    assert "is not 'Town of Oakville''s site but another body's" in str(withdrawn)
    assert "stays a candidate" in str(withdrawn)
    assert domain_status(db, "oakville-township.ca") is EntityStatus.CANDIDATE

    async def check() -> tuple[EntityStatus, str | None]:
        async with db.session() as session:
            row = await session.get_one(Homepage, second.id)
            return row.status, row.rejected_reason

    assert db.run(check) == (
        EntityStatus.REJECTED,
        "another body's site: it is the Township of Oakville's",
    )
    assert claim.id != second.id


def claimed_again(db: Database, world: World, build: type[Build], ctx: SessionContext) -> Homepage:
    """A second candidate the session saves from a search result."""

    async def make() -> Homepage:
        async with db.session() as session:
            town = await session.get_one(Institution, world.town.id)
            claim = await build.claim(session, town, "https://www.oakville-township.ca/")
            domain = await graph.domain_by_name(session, "oakville-township.ca")
            assert domain is not None
            await session.commit()
            ctx.take_candidate(domain, claim)
            return claim

    return db.run(make)


def test_a_trusted_link_to_any_page_on_the_domain_vouches_for_the_root_claim(
    db: Database,
    world: World,
    build: type[Build],
    make_assignment: Callable[..., Assignment],
    context: Callable[[Assignment], SessionContext],
    capture: Capture,
    call: Callable[..., Any],
    in_session,
):
    """The county's site links to a deep page on the utility's domain, and the agent claims the
    root page it found there. The link to the deep page is the trusted link for the domain
    (spec section 6.3), so the root page is verified without a human."""
    deep = "https://www.oakvillehydro.ca/rates/residential"
    root = "https://www.oakvillehydro.ca/"
    _, snapshot = capture(
        "https://www.elmcounty.ca/hydro",
        '<html><body><p>Rates: <a href="https://www.oakvillehydro.ca/rates/residential">'
        "Oakville Hydro residential rates</a></p></body></html>",
        "Rates: Oakville Hydro residential rates",
    )

    async def claimed_deep(session) -> tuple[Institution, Homepage]:
        oakville = await session.get_one(Place, world.oakville.id)
        utility = await build.candidate_institution(
            session, oakville, "Oakville Hydro", "public_utility"
        )
        await status_changes.verify_institution(session, utility, entered_by=EnteredBy.SCRIPT)
        linking = await session.get_one(Webpage, snapshot.webpage_id)
        claim = await build.claim(session, utility, deep, found_on=linking)
        await evidence.add_evidence(
            session,
            entity_id=claim.id,
            snapshot=snapshot,
            kind=EvidenceKind.LINKS_TO,
            quote="Oakville Hydro residential rates",
            entered_by=EnteredBy.AGENT,
            link_url=deep,
        )
        return utility, claim

    utility, deep_claim = in_session(claimed_deep)
    ctx = context(make_assignment(FIND_HOMEPAGE, utility.id))
    assert ctx.candidate is not None
    assert ctx.candidate.homepage_id == deep_claim.id
    capture.page(root, "Oakville Hydro: powering the town since 1914", ctx.assignment_id)
    # The root page claimed from the candidate domain itself, as the goal text asks.
    saved = call(ctx, findings.record_homepage, url=root)
    assert saved.claim_status is EntityStatus.CANDIDATE
    assert ctx.candidate is not None
    assert ctx.candidate.homepage_id != deep_claim.id
    outcome = call(
        ctx,
        findings.confirm_candidate,
        quotes=[Quote(url=root, quote="Oakville Hydro: powering the town")],
    )
    assert str(outcome).startswith(
        "Verified oakvillehydro.ca as an official domain of 'Oakville Hydro'"
    )
    institution, claims = homepage_of(db, utility.id)
    verified = [claim for claim in claims if claim.status is EntityStatus.VERIFIED]
    assert len(verified) == 1
    assert institution.homepage_id == verified[0].id
    assert verified[0].id != deep_claim.id
    superseded = next(claim for claim in claims if claim.id == deep_claim.id)
    assert superseded.rejected_reason == status_changes.SUPERSEDED
