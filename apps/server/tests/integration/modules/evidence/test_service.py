"""Snapshots sharing by hash, and the quote and link checks against a stored copy."""

from typing import TYPE_CHECKING

from sqlalchemy import select

from public_atlas.modules.evidence import service
from public_atlas.modules.evidence.models import EvidenceKind, Snapshot, TextStatus
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph.models import EnteredBy

if TYPE_CHECKING:
    from tests.integration.conftest import Database

    from public_atlas.integrations.storage.memory import MemoryObjectStore
    from public_atlas.modules.assignments.models import Assignment

PAGE_URL = "https://www.whitby.ca/en/town-hall/"
HTML = (
    "<html><head><title>Town Hall</title></head><body><p>Welcome to the Town of Whitby</p>"
    '<a href="/en/town-hall/budget">Budget 2026</a>'
    '<footer style="visibility:hidden">&copy; 2026 The Corporation of the Town of Whitby</footer>'
    "</body></html>"
)
RENDERED = "Town Hall\n\nWelcome to the Town of Whitby\nBudget 2026"


def test_identical_bytes_share_one_text_and_one_copy_whatever_the_url(
    db: Database,
    object_store: MemoryObjectStore,
    assignment: Assignment,
    another_assignment: Assignment,
):
    data = b"%PDF-1.4 Operating budget 2026"

    async def scenario() -> tuple[Snapshot, Snapshot, Snapshot, bool, int]:
        async with db.session() as session:
            first_page = await graph.ensure_webpage(session, "https://a.example/budget.pdf")
            second_page = await graph.ensure_webpage(session, "https://b.example/budget.pdf")
            first, created = await service.store_snapshot(
                session,
                object_store,
                first_page,
                data,
                text=None,
                media_type="application/pdf",
                filename="budget.pdf",
                assignment_id=assignment.id,
            )
            assert created
            await service.mark_text_ready(session, object_store, first, "Operating\fbudget")
            second, _ = await service.store_snapshot(
                session,
                object_store,
                second_page,
                data,
                text=None,
                media_type="application/pdf",
                filename="budget.pdf",
                assignment_id=another_assignment.id,
            )
            again, created_again = await service.store_snapshot(
                session,
                object_store,
                first_page,
                data,
                text=None,
                media_type="application/pdf",
                filename="budget.pdf",
                assignment_id=assignment.id,
            )
            await session.commit()
            return first, second, again, created_again, len(object_store.objects)

    first, second, again, created_again, objects = db.run(scenario)
    assert second.text_status is TextStatus.READY
    assert (second.text_key, second.page_count) == (first.text_key, 2)
    assert second.bytes_key == first.bytes_key
    # The same assignment fetching the same bytes again gets its own row back.
    assert (again.id, created_again) == (first.id, False)
    # One copy of the bytes and one of the text, for the three rows.
    assert objects == 2


def test_a_quote_is_checked_in_the_rendered_text_then_in_the_stored_html(
    db: Database, object_store: MemoryObjectStore, assignment: Assignment
):
    async def scenario() -> dict[str, object]:
        async with db.session() as session:
            webpage = await graph.ensure_webpage(session, PAGE_URL)
            missing = await service.check_quote(
                session, object_store, webpage, "Welcome to the Town"
            )
            snapshot, _ = await service.store_snapshot(
                session,
                object_store,
                webpage,
                HTML.encode(),
                text=RENDERED,
                media_type=service.HTML,
                filename="page.html",
                assignment_id=assignment.id,
            )
            rendered = await service.check_quote(
                session, object_store, webpage, "welcome to the town of whitby"
            )
            hidden = await service.check_quote(
                session, object_store, webpage, "© 2026 The Corporation of the Town of Whitby"
            )
            nowhere = await service.check_quote(
                session, object_store, webpage, "Town of Ajax welcomes you"
            )
            nearest = await service.nearest_text(
                session, object_store, webpage, "© 2026 The Corporation of Whitby"
            )
            link = await service.check_link(
                object_store, snapshot, PAGE_URL, "https://www.whitby.ca/en/town-hall/budget"
            )
            no_link = await service.check_link(
                object_store, snapshot, PAGE_URL, "https://www.whitby.ca/en/other"
            )
            written = await service.check_link(
                object_store,
                snapshot,
                PAGE_URL,
                "https://www.elmwood.ca/",
                quote="Township of Elmwood www.elmwood.ca",
            )
            return {
                "missing": missing,
                "rendered": rendered,
                "hidden": hidden,
                "nowhere": nowhere,
                "nearest": nearest,
                "link": link,
                "no_link": no_link,
                "written": written,
                "snapshot": snapshot,
            }

    out = db.run(scenario)
    # A page never opened cannot vouch for anything.
    assert out["missing"] is None
    rendered, snapshot = out["rendered"], out["snapshot"]
    assert isinstance(rendered, service.QuoteMatch)
    assert isinstance(snapshot, Snapshot)
    assert (rendered.snapshot.id, rendered.locator) == (snapshot.id, None)
    assert isinstance(out["hidden"], service.QuoteMatch)
    assert out["nowhere"] is None
    assert "corporation of the town of whitby" in str(out["nearest"])
    assert out["link"] == "Budget 2026"
    assert out["no_link"] is None
    assert out["written"] == "https://www.elmwood.ca/"


def test_a_quote_in_a_file_carries_its_page_and_evidence_is_recorded_once(
    db: Database, object_store: MemoryObjectStore, assignment: Assignment
):
    async def scenario() -> tuple[int | None, bool, bool, int]:
        async with db.session() as session:
            webpage = await graph.ensure_webpage(session, "https://www.whitby.ca/budget.pdf")
            snapshot, _ = await service.store_snapshot(
                session,
                object_store,
                webpage,
                b"%PDF-1.4 x",
                text="Cover\fContents\fTotal budget $1,200,000",
                media_type="application/pdf",
                filename="budget.pdf",
                assignment_id=assignment.id,
            )
            match = await service.check_quote(
                session, object_store, webpage, "Total budget $1,200,000"
            )
            assert match is not None
            domain = await graph.domain_of_host(session, "ontario.ca")
            assert domain is not None
            first = await service.add_evidence(
                session,
                entity_id=domain.id,
                snapshot=snapshot,
                kind=EvidenceKind.APPEARS_ON,
                quote=" Total budget $1,200,000 ",
                locator=match.locator,
                entered_by=EnteredBy.AGENT,
                assignment_id=assignment.id,
            )
            second = await service.add_evidence(
                session,
                entity_id=domain.id,
                snapshot=snapshot,
                kind=EvidenceKind.APPEARS_ON,
                quote="Total budget $1,200,000",
                locator=match.locator,
                entered_by=EnteredBy.AGENT,
            )
            rows = await service.evidence_for(session, domain.id)
            return match.locator, first, second, len(rows)

    assert db.run(scenario) == (3, True, False, 1)


def test_the_latest_snapshot_is_the_newest_ready_one_of_the_assignment_asked_for(
    db: Database,
    object_store: MemoryObjectStore,
    assignment: Assignment,
    another_assignment: Assignment,
):
    async def scenario() -> tuple[bool, bool, bool]:
        async with db.session() as session:
            webpage = await graph.ensure_webpage(session, "https://www.whitby.ca/")
            older, _ = await service.store_snapshot(
                session,
                object_store,
                webpage,
                b"<html>v1</html>",
                text="v1",
                media_type=service.HTML,
                filename="page.html",
                assignment_id=assignment.id,
            )
            await service.store_snapshot(
                session,
                object_store,
                webpage,
                b"%PDF v2",
                text=None,
                media_type="application/pdf",
                filename="x.pdf",
                assignment_id=another_assignment.id,
            )
            newest = await service.latest_snapshot(session, webpage.id)
            mine = await service.latest_snapshot(session, webpage.id, assignment_id=assignment.id)
            theirs = await service.latest_snapshot(
                session, webpage.id, assignment_id=another_assignment.id
            )
            rows = len((await session.scalars(select(Snapshot))).all())
            assert rows == 2
            return (
                newest is not None and newest.id == older.id,
                mine is not None and mine.id == older.id,
                theirs is None,
            )

    assert db.run(scenario) == (True, True, True)
