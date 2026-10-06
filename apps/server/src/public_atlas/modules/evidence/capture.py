"""The capture hook: stores every page the browser settles on and logs every refused attempt,
from the plain values the browser hands over (spec section 8.2). It never touches the browser.
When an assignment finishes, `prune_unreferenced` drops the stored bytes of the snapshots
nothing cites; the rows stay with their hash and metadata."""

import html
import logging
import uuid
from collections.abc import Callable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.db.base import utcnow
from public_atlas.integrations.browser import FrameLinks, SettledPage
from public_atlas.integrations.storage import ObjectStore
from public_atlas.modules.evidence import snapshots
from public_atlas.modules.evidence.models import BlockedAttempt, Evidence, Snapshot, TextStatus
from public_atlas.modules.evidence.quote_checks import HTML
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph.models import Webpage

logger = logging.getLogger(__name__)

PAGE_FILENAME = "page.html"
REASON_LENGTH = 2000


def frame_blocks(frames: Sequence[FrameLinks]) -> str:
    """The links inside a page's child frames, as HTML to append to its stored copy: one
    `<template>` per frame with the frame's address and its links. A meetings page that embeds
    its eSCRIBE portal links to it only through the frame; the link check reads these, and the
    page's text, which skips `<template>`, is unchanged."""
    blocks = []
    for frame in frames:
        anchors = "".join(
            f'<a href="{html.escape(href)}">{html.escape(text)}</a>'
            for href, text in [(frame.url, ""), *frame.links]
            if href.startswith(("http://", "https://"))
        )
        blocks.append(f'<template data-atlas-frame="{html.escape(frame.url)}">{anchors}</template>')
    return "\n".join(blocks)


def stored_html(page: SettledPage) -> str:
    blocks = frame_blocks(page.frames)
    return f"{page.html}\n{blocks}" if blocks else page.html


def rendered_text(page: SettledPage) -> str:
    """The page as the agent saw it: the title first."""
    return f"{page.title}\n\n{page.text}" if page.title else page.text


async def record_visit(
    session: AsyncSession,
    store: ObjectStore,
    page: SettledPage,
    *,
    assignment_id: uuid.UUID | None,
) -> tuple[Webpage, Snapshot]:
    """A page the browser settled on: the HTML with its frames' links is the stored copy, the
    rendered text its text."""
    webpage = await graph.ensure_webpage(session, page.url, assignment_id=assignment_id)
    snapshot, _ = await snapshots.store_snapshot(
        session,
        store,
        webpage,
        stored_html(page).encode(),
        text=rendered_text(page),
        media_type=HTML,
        filename=PAGE_FILENAME,
        assignment_id=assignment_id,
    )
    return webpage, snapshot


async def record_redirect(
    session: AsyncSession, *, requested: str, landed: str, assignment_id: uuid.UUID | None
) -> Webpage | None:
    """Record on `requested`'s row that the browser was sent on to `landed`, so a finding that
    cites the URL the agent typed is read on the page that answered, and a candidate homepage
    that moved to another domain is on record as having done so."""
    try:
        source, target = graph.normalize_url(requested), graph.normalize_url(landed)
    except ValueError:
        return None
    if not graph.host_of(source) or not graph.host_of(target) or source == target:
        return None
    webpage = await graph.ensure_webpage(session, source, assignment_id=assignment_id)
    webpage.redirects_to_url = target
    await session.flush()
    return webpage


async def record_blocked(
    session: AsyncSession, *, url: str, reason: str, assignment_id: uuid.UUID | None
) -> BlockedAttempt | None:
    """A URL the fence refused, as this assignment's attempt. No webpage row and no snapshot:
    nothing was opened. Outside an assignment (a test driving the browser) it is only logged."""
    logger.info("Blocked %s: %s", url, reason)
    if assignment_id is None:
        return None
    attempt = BlockedAttempt(url=url, reason=reason[:REASON_LENGTH], assignment_id=assignment_id)
    session.add(attempt)
    await session.flush()
    return attempt


async def prune_unreferenced(session: AsyncSession, assignment_id: uuid.UUID) -> list[str]:
    """Mark every snapshot of this assignment that no evidence cites as pruned, and return the
    object keys to delete once the session is committed. Bytes and text are keyed by hash and
    shared, so an object goes only when no other unpruned snapshot still holds its bytes."""
    cited = select(Evidence.snapshot_id)
    snapshots = list(
        await session.scalars(
            select(Snapshot).where(
                Snapshot.assignment_id == assignment_id,
                Snapshot.pruned_at.is_(None),
                Snapshot.id.not_in(cited),
            )
        )
    )
    now = utcnow()
    for snapshot in snapshots:
        snapshot.pruned_at = now
    await session.flush()
    keys: list[str] = []
    for snapshot in snapshots:
        others = await session.scalar(
            select(Snapshot.id)
            .where(
                Snapshot.content_hash == snapshot.content_hash,
                Snapshot.pruned_at.is_(None),
            )
            .limit(1)
        )
        if others is not None:
            continue
        keys.append(snapshot.bytes_key)
        if snapshot.text_status is TextStatus.READY and snapshot.text_key is not None:
            keys.append(snapshot.text_key)
    return list(dict.fromkeys(keys))


async def delete_objects(store: ObjectStore, keys: Sequence[str]) -> None:
    """The rows are pruned already, so a store that fails here leaks bytes, never a row."""
    for key in keys:
        try:
            await store.delete(key)
        except Exception:
            logger.exception("Could not delete pruned object %s", key)


class PageCapture:
    """The capture hook of an assignment's browser session. Each event gets a session of its
    own and commits, so a stored page survives whatever the agent does next."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        store: ObjectStore,
        *,
        assignment_id: uuid.UUID | None,
    ) -> None:
        self._session_factory = session_factory
        self._store = store
        self._assignment_id = assignment_id
        self.visited: list[str] = []
        self.blocked_urls: list[str] = []

    async def settled(self, page: SettledPage) -> None:
        async with self._session_factory() as session:
            await record_visit(session, self._store, page, assignment_id=self._assignment_id)
            if page.requested_url is not None:
                await record_redirect(
                    session,
                    requested=page.requested_url,
                    landed=page.url,
                    assignment_id=self._assignment_id,
                )
            await session.commit()
        self.visited.append(graph.normalize_url(page.url))
        logger.debug("Captured %s after %s", page.url, page.action)

    async def blocked(
        self, url: str, reason: str, *, action: str, requested_url: str | None = None
    ) -> None:
        async with self._session_factory() as session:
            await record_blocked(session, url=url, reason=reason, assignment_id=self._assignment_id)
            if requested_url is not None:
                # A redirect off the allowlist: the URL asked for is on record as leading
                # there, which `domain_moved` checks.
                await record_redirect(
                    session, requested=requested_url, landed=url, assignment_id=self._assignment_id
                )
            await session.commit()
        self.blocked_urls.append(url)
        logger.info("Blocked %s on %s: %s", action, url, reason)
