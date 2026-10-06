"""What the capture hook writes from the browser's plain values, and what pruning keeps."""

from typing import TYPE_CHECKING

from sqlalchemy import select

from public_atlas.integrations.browser import FrameLinks, SettledPage
from public_atlas.modules.evidence import capture
from public_atlas.modules.evidence.models import BlockedAttempt, EvidenceKind, Snapshot, TextStatus
from public_atlas.modules.evidence.service import add_evidence, snapshot_text, store_snapshot
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph.models import Domain, DomainKind, EnteredBy, EntityStatus, Webpage

if TYPE_CHECKING:
    from tests.integration.conftest import Database

    from public_atlas.integrations.storage.memory import MemoryObjectStore
    from public_atlas.modules.assignments.models import Assignment

URL = "https://www.toronto.ca/city-government/"
PAGE = SettledPage(
    url=URL,
    title="City government",
    html="<html><body><h1>City government</h1><p>Agencies</p></body></html>",
    text="City government\nAgencies",
    frames=(
        FrameLinks(
            "https://escribe.example/portal", (("https://escribe.example/m?id=1", "Council"),)
        ),
    ),
    action="navigate",
    requested_url="https://toronto.ca/city-government",
)


def test_a_webpage_gets_its_domain_once_the_domain_row_exists(db: Database):
    async def scenario() -> tuple[object, object]:
        async with db.session() as session:
            first = await graph.ensure_webpage(session, URL)
            before = first.domain_id
            session.add(
                Domain(
                    name="toronto.ca",
                    domain_kind=DomainKind.OFFICIAL,
                    status=EntityStatus.CANDIDATE,
                    entered_by=EnteredBy.AGENT,
                )
            )
            await session.flush()
            again = await graph.ensure_webpage(session, URL)
            domain = await graph.domain_of_host(session, "www.toronto.ca")
            assert domain is not None
            return before, again.domain_id == domain.id

    assert db.run(scenario) == (None, True)


def test_a_settled_page_is_stored_with_its_frames_links_and_rendered_text(
    db: Database, object_store: MemoryObjectStore, assignment: Assignment
):
    hook = capture.PageCapture(db.session, object_store, assignment_id=assignment.id)

    async def scenario() -> tuple[Snapshot, str, str, str | None]:
        await hook.settled(PAGE)
        async with db.session() as session:
            webpage = await graph.webpage_by_url(session, URL)
            assert webpage is not None
            snapshot = (
                await session.scalars(select(Snapshot).where(Snapshot.webpage_id == webpage.id))
            ).one()
            requested = await graph.webpage_by_url(session, PAGE.requested_url or "")
            assert requested is not None
            html = (await object_store.get(snapshot.bytes_key)).decode()
            return (
                snapshot,
                html,
                await snapshot_text(object_store, snapshot),
                requested.redirects_to_url,
            )

    snapshot, html, text, redirected_to = db.run(scenario)
    assert snapshot.assignment_id == assignment.id
    assert snapshot.text_status is TextStatus.READY
    assert snapshot.page_count == 1
    assert html.startswith(PAGE.html)
    assert 'data-atlas-frame="https://escribe.example/portal"' in html
    assert 'href="https://escribe.example/m?id=1"' in html
    assert text == "City government\n\nCity government\nAgencies"
    # The URL the agent typed is on record as having led here.
    assert redirected_to == URL
    assert hook.visited == [URL]


def test_a_refused_url_is_a_blocked_attempt_and_nothing_else(
    db: Database, object_store: MemoryObjectStore, assignment: Assignment
):
    hook = capture.PageCapture(db.session, object_store, assignment_id=assignment.id)

    async def scenario() -> tuple[list[tuple[str, str]], int, int]:
        await hook.blocked(
            "https://evil.example/", "domain not in allowed_domains", action="navigate"
        )
        async with db.session() as session:
            attempts = await session.execute(select(BlockedAttempt.url, BlockedAttempt.reason))
            webpages = len((await session.scalars(select(Webpage))).all())
            snapshots = len((await session.scalars(select(Snapshot))).all())
            return [tuple(row) for row in attempts.all()], webpages, snapshots

    assert db.run(scenario) == ([("https://evil.example/", "domain not in allowed_domains")], 0, 0)
    assert hook.blocked_urls == ["https://evil.example/"]


def test_pruning_drops_uncited_bytes_but_keeps_objects_another_snapshot_shares(
    db: Database,
    object_store: MemoryObjectStore,
    assignment: Assignment,
    another_assignment: Assignment,
):
    data = b"%PDF-1.4 the same budget book"

    async def scenario() -> tuple[list[str], list[str], Snapshot, Snapshot, Snapshot]:
        async with db.session() as session:
            webpage = await graph.ensure_webpage(session, "https://www.toronto.ca/budget.pdf")
            other = await graph.ensure_webpage(session, "https://www.toronto.ca/budget-copy.pdf")
            # Three snapshots: two of the same bytes by the two assignments, one of other bytes.
            mine, _ = await store_snapshot(
                session,
                object_store,
                webpage,
                data,
                text="budget",
                media_type="application/pdf",
                filename="budget.pdf",
                assignment_id=assignment.id,
            )
            theirs, _ = await store_snapshot(
                session,
                object_store,
                other,
                data,
                text=None,
                media_type="application/pdf",
                filename="budget.pdf",
                assignment_id=another_assignment.id,
            )
            alone, _ = await store_snapshot(
                session,
                object_store,
                webpage,
                b"<html>cited</html>",
                text="cited",
                media_type="text/html",
                filename="page.html",
                assignment_id=assignment.id,
            )
            uncited, _ = await store_snapshot(
                session,
                object_store,
                other,
                b"<html>uncited</html>",
                text="uncited",
                media_type="text/html",
                filename="page.html",
                assignment_id=assignment.id,
            )
            domain = await graph.domain_of_host(session, "ontario.ca")
            assert domain is not None  # the Ontario anchor
            await add_evidence(
                session,
                entity_id=domain.id,
                snapshot=alone,
                kind=EvidenceKind.APPEARS_ON,
                quote="cited",
                entered_by=EnteredBy.AGENT,
            )
            keys = await capture.prune_unreferenced(session, assignment.id)
            await capture.delete_objects(object_store, keys)
            await session.commit()
            return keys, sorted(object_store.objects), mine, theirs, uncited

    keys, remaining, mine, theirs, uncited = db.run(scenario)
    # The uncited page's bytes and text go; the budget book's stay, since the other assignment's
    # snapshot shares them; the cited page is untouched.
    assert uncited.text_key is not None
    assert sorted(keys) == sorted([uncited.bytes_key, uncited.text_key])
    assert mine.pruned_at is not None
    assert uncited.pruned_at is not None
    assert theirs.text_status is TextStatus.READY  # shared the text at store time
    assert mine.bytes_key in remaining
    assert theirs.text_key in remaining
    assert uncited.bytes_key not in remaining
