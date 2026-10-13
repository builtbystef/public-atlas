"""The agent's browser driven against a local site with a real Chromium, with the capture hook
storing what it lands on. Marked `browser`: needs `vp run browser:install`."""

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from public_atlas.integrations.browser import Browser, BrowserPolicy, Refusal
from public_atlas.integrations.browser import policy as policy_module
from public_atlas.modules.evidence.models import BlockedAttempt, Snapshot
from public_atlas.modules.evidence.quote_checks import html_text, link_in_html
from public_atlas.modules.evidence.service import PageCapture, snapshot_text
from public_atlas.modules.graph.models import Webpage

if TYPE_CHECKING:
    from tests.integration.conftest import Database, FixtureSite

    from public_atlas.integrations.storage.memory import MemoryObjectStore
    from public_atlas.modules.assignments.models import Assignment

pytestmark = pytest.mark.browser


def make_browser(capture: PageCapture) -> Browser:
    """A browser allowed only the fixture host, paced fast enough for a test."""
    policy = BrowserPolicy(["127.0.0.1"], block_private_addresses=False, min_interval=0.2)
    return Browser(policy, hook=capture, max_content_tokens=4000)


@pytest.fixture(autouse=True)
def _fresh_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty pacing table. It is process-wide: a host one test made rest would slow the next."""
    monkeypatch.setattr(policy_module, "_next_slot", {})


async def rows(db: Database, assignment: Assignment) -> tuple[list[str], list[Snapshot], list[str]]:
    """The page URLs, the snapshots and the assignment's blocked URLs, each in order."""
    async with db.session() as session:
        urls = list(await session.scalars(select(Webpage.url).order_by(Webpage.url)))
        snapshots = list(await session.scalars(select(Snapshot).order_by(Snapshot.fetched_at)))
        blocked = list(
            await session.scalars(
                select(BlockedAttempt.url)
                .where(BlockedAttempt.assignment_id == assignment.id)
                .order_by(BlockedAttempt.at)
            )
        )
        return urls, snapshots, blocked


def test_every_navigating_tool_produces_a_snapshot_and_a_refusal_a_blocked_attempt_only(
    db: Database, object_store: MemoryObjectStore, site: FixtureSite, assignment: Assignment
):
    capture = PageCapture(db.session, object_store, assignment_id=assignment.id)
    browser = make_browser(capture)

    async def drive() -> dict[str, str]:
        out: dict[str, str] = {}
        async with browser:
            out["index"] = str(await browser.navigate(f"{site.allowed}/"))
            out["click"] = str(await browser.click("#agency"))
            out["back"] = str(await browser.go_back())
            out["outside"] = str(await browser.navigate(f"{site.outside}/hospital"))
            out["outside_click"] = str(await browser.click("#outside"))
            out["robots"] = str(await browser.navigate(f"{site.allowed}/private"))
            # Last, because the 429 makes the host rest for every later navigation.
            out["busy"] = str(await browser.navigate(f"{site.allowed}/busy"))
        return out

    out = db.run(drive)
    assert "Regional Municipality of Fixture" in out["index"]
    assert "Fixture Transit Commission" in out["click"]
    assert out["back"].startswith("Went back.")
    assert out["outside"] == f"Error: {policy_module.NOT_ALLOWED}: {site.outside}/hospital"
    assert out["outside_click"].startswith("Error: click loaded no page")
    assert out["robots"].startswith(f"Error: {policy_module.ROBOTS_DISALLOWED}")
    assert out["busy"].startswith("Error: 127.0.0.1 answered 429 Too Many Requests")
    assert "next request waits 7s" in out["busy"]
    assert "higher volume" not in out["busy"]  # the throttle page's text is not shown as content
    assert "SECRET" not in "".join(out.values())
    # Images are never fetched: the agent reads text, not pixels.
    assert "/" in site.requested
    assert "/logo.png" not in site.requested

    urls, snapshots, blocked = db.run(rows, db, assignment)
    # Only the pages that opened have a row; a refused URL has none.
    assert urls == [f"{site.allowed}/", f"{site.allowed}/agency"]
    # The index seen again after go_back is the same bytes for the same assignment: one snapshot.
    assert [snapshot.filename for snapshot in snapshots] == ["page.html", "page.html"]
    assert capture.visited == [f"{site.allowed}/", f"{site.allowed}/agency", f"{site.allowed}/"]
    assert blocked == [
        f"{site.outside}/hospital",
        f"{site.outside}/hospital",
        f"{site.allowed}/private",
        f"{site.allowed}/busy",
    ]

    async def texts() -> list[str]:
        return [await snapshot_text(object_store, snapshot) for snapshot in snapshots]

    stored = db.run(texts)
    assert any(text.startswith("Fixture Transit Commission") for text in stored)
    assert all("SECRET" not in text for text in stored)
    assert all(b"SECRET" not in data for data, _ in object_store.objects.values())


def test_navigating_to_a_document_points_the_agent_at_read_file(
    db: Database, object_store: MemoryObjectStore, site: FixtureSite, assignment: Assignment
):
    browser = make_browser(PageCapture(db.session, object_store, assignment_id=assignment.id))

    async def drive() -> object:
        async with browser:
            return await browser.navigate(f"{site.allowed}/budget.pdf")

    out = db.run(drive)
    assert isinstance(out, Refusal)
    assert str(out) == (
        f"Error: {site.allowed}/budget.pdf is a file download (a PDF or other document), not a "
        "web page. Open it with read_file."
    )


def test_a_link_added_after_load_or_inside_a_frame_is_in_the_stored_copy(
    db: Database, object_store: MemoryObjectStore, site: FixtureSite, assignment: Assignment
):
    browser = make_browser(PageCapture(db.session, object_store, assignment_id=assignment.id))

    async def drive() -> None:
        async with browser:
            await browser.navigate(f"{site.allowed}/meetings")

    db.run(drive)

    async def stored() -> str:
        async with db.session() as session:
            snapshot = (
                await session.scalars(
                    select(Snapshot)
                    .join(Webpage, Webpage.id == Snapshot.webpage_id)
                    .where(Webpage.url == f"{site.allowed}/meetings")
                )
            ).one()
            return (await object_store.get(snapshot.bytes_key)).decode()

    page_html = db.run(stored)
    url = f"{site.allowed}/meetings"
    # A link a script adds after load is in the copy, which is taken once the page goes quiet.
    assert link_in_html(page_html, url, f"{site.allowed}/late")
    # A frame's links are in the copy too, resolved against the frame's own URL.
    assert link_in_html(page_html, url, f"{site.allowed}/portal")
    assert link_in_html(page_html, url, f"{site.allowed}/meeting?id=7")
    # The frame's content is kept for its links only; it must not become quotable page text.
    assert "Council 2026-09-30" not in html_text(page_html)


def test_a_frame_reached_by_redirect_resolves_its_links_against_where_it_ended(
    db: Database, object_store: MemoryObjectStore, site: FixtureSite, assignment: Assignment
):
    """The guard checks a frame's redirect chain itself, then sends Chromium to where it ended,
    so the frame's document has its real URL and a relative link in it resolves against that,
    not against the URL the page embedded."""
    browser = make_browser(PageCapture(db.session, object_store, assignment_id=assignment.id))

    async def drive() -> list[str]:
        async with browser:
            await browser.navigate(f"{site.allowed}/meetings-moved")
            page = await browser.session.ensure_page()
            return [frame.url for frame in page.frames[1:]]

    frame_urls = db.run(drive)
    assert frame_urls == [f"{site.allowed}/portal"]
    assert site.requested.count("/portal-moved") == 1
    # Once by the guard, to learn the chain ends there, and once by the frame for itself.
    assert site.requested.count("/portal") == 2

    async def stored() -> str:
        async with db.session() as session:
            snapshot = (
                await session.scalars(
                    select(Snapshot)
                    .join(Webpage, Webpage.id == Snapshot.webpage_id)
                    .where(Webpage.url == f"{site.allowed}/meetings-moved")
                )
            ).one()
            return (await object_store.get(snapshot.bytes_key)).decode()

    page_html = db.run(stored)
    url = f"{site.allowed}/meetings-moved"
    assert link_in_html(page_html, url, f"{site.allowed}/meeting?id=7")


def test_a_redirect_is_recorded_against_the_url_the_browser_asked_for(
    db: Database, object_store: MemoryObjectStore, site: FixtureSite, assignment: Assignment
):
    browser = make_browser(PageCapture(db.session, object_store, assignment_id=assignment.id))

    async def drive() -> dict[str, str]:
        out: dict[str, str] = {}
        async with browser:
            out["moved"] = str(await browser.navigate(f"{site.allowed}/moved"))
            out["gone"] = str(await browser.navigate(f"{site.allowed}/gone"))
        return out

    out = db.run(drive)
    assert "Fixture Transit Commission" in out["moved"]
    # The guard holds the hop back and the tool refuses it, so the page stays where it was.
    assert out["gone"] == (
        f"Error: navigate was redirected to {site.outside}/hospital: "
        f"{policy_module.NOT_ALLOWED}. The browser is still at {site.allowed}/agency."
    )

    async def check() -> tuple[dict[str, str | None], list[str]]:
        async with db.session() as session:
            pages = await session.execute(select(Webpage.url, Webpage.redirects_to_url))
            blocked = list(await session.scalars(select(BlockedAttempt.url)))
            return dict(pages.tuples().all()), blocked

    pages, blocked = db.run(check)
    assert pages == {
        f"{site.allowed}/moved": f"{site.allowed}/agency",
        f"{site.allowed}/agency": None,
        f"{site.allowed}/gone": f"{site.outside}/hospital",
    }
    assert blocked == [f"{site.outside}/hospital"]


def test_the_other_tools_read_the_page_the_agent_is_on(
    db: Database, object_store: MemoryObjectStore, site: FixtureSite, assignment: Assignment
):
    browser = make_browser(PageCapture(db.session, object_store, assignment_id=assignment.id))

    async def drive() -> dict[str, object]:
        out: dict[str, object] = {}
        async with browser:
            await browser.navigate(f"{site.allowed}/")
            out["snapshot"] = await browser.snapshot()
            out["text"] = await browser.get_text("h1")
            out["hover"] = await browser.hover("#agency")
            out["scroll"] = await browser.scroll("down")
            out["wait"] = await browser.wait_for(text="Agencies")
            out["missing"] = await browser.get_text("#nothing", timeout_ms=200)
            out["screenshot"] = await browser.screenshot()
            out["tabs"] = await browser.tabs("list")
            out["forward"] = await browser.go_forward()
        return out

    out = db.run(drive)
    assert "Regional Municipality of Fixture" in str(out["snapshot"])
    assert str(out["text"]) == "Regional Municipality of Fixture"
    assert str(out["hover"]).startswith("Hovered '#agency'.")
    assert str(out["scroll"]).startswith("Scrolled down. The page has nothing to scroll.")
    assert str(out["wait"]).startswith("Found 'Agencies'.")
    assert isinstance(out["missing"], Refusal)
    assert str(out["tabs"]).startswith(f"0 (active): Fixture Region -- {site.allowed}/")
    assert str(out["forward"]) == "No next page in browser history."
    screenshot = out["screenshot"]
    assert not isinstance(screenshot, Refusal)
    assert getattr(screenshot, "png", b"").startswith(b"\x89PNG")


def test_a_redirect_off_the_allowlist_is_never_requested(
    db: Database, object_store: MemoryObjectStore, site: FixtureSite, assignment: Assignment
):
    """Chromium follows a redirect without asking any route, so the guard reads each hop before
    the browser may make it: the off-list host sees no request, whether the hop is the first or
    the second, and whether a navigation, a click or a script's fetch led there. A hop that
    stays on the allowlist is made, and the page ends at its real URL."""
    capture = PageCapture(db.session, object_store, assignment_id=assignment.id)
    browser = make_browser(capture)

    async def drive() -> dict[str, str]:
        out: dict[str, str] = {}
        async with browser:
            out["gone"] = str(await browser.navigate(f"{site.allowed}/gone"))
            out["chain"] = str(await browser.navigate(f"{site.allowed}/chain"))
            out["twice"] = str(await browser.navigate(f"{site.allowed}/moved-twice"))
            out["leaky"] = str(await browser.navigate(f"{site.allowed}/leaky"))
            out["api"] = str(await browser.wait_for(text="api: failed"))
            out["click"] = str(await browser.click("#gone"))
        return out

    out = db.run(drive)
    hop = f"{site.outside}/hospital"
    refused = f"was redirected to {hop}: {policy_module.NOT_ALLOWED}. The browser is still at"
    assert out["gone"] == f"Error: navigate {refused} about:blank."
    assert out["chain"] == f"Error: navigate {refused} about:blank."
    assert out["twice"].startswith(f"URL: {site.allowed}/agency\nTitle: Fixture Transit Commission")
    assert out["api"].startswith("Found 'api: failed'.")
    assert out["click"] == f"Error: click {refused} {site.allowed}/leaky."
    assert "SECRET" not in "".join(out.values())
    # The host off the allowlist was never asked for anything.
    assert site.requested_outside == []
    assert site.requested.count("/gone") == 3
    assert site.requested.count("/api/old") == 1
    assert "/api/secret" not in site.requested
    assert "/hospital" not in site.requested
    assert all(b"SECRET" not in data for data, _ in object_store.objects.values())

    async def check() -> tuple[dict[str, str | None], list[str], list[str]]:
        async with db.session() as session:
            pages = await session.execute(select(Webpage.url, Webpage.redirects_to_url))
            blocked = list(
                await session.scalars(select(BlockedAttempt.url).order_by(BlockedAttempt.at))
            )
            stored = list(
                await session.scalars(
                    select(Webpage.url).join(Snapshot, Snapshot.webpage_id == Webpage.id)
                )
            )
            return dict(pages.tuples().all()), blocked, sorted(stored)

    pages, blocked, stored = db.run(check)
    # Every URL asked for is on record as leading where it led; neither the refused hop nor the
    # hop in the middle of a chain is a page of its own, since neither was opened.
    assert pages == {
        f"{site.allowed}/gone": hop,
        f"{site.allowed}/chain": hop,
        f"{site.allowed}/moved-twice": f"{site.allowed}/agency",
        f"{site.allowed}/agency": None,
        f"{site.allowed}/leaky": None,
    }
    assert blocked == [hop, hop, hop]
    assert stored == [f"{site.allowed}/agency", f"{site.allowed}/leaky"]
    assert capture.visited == [f"{site.allowed}/agency", f"{site.allowed}/leaky"]
