"""Snapshots: a stored copy of a page or file as fetched, plus its extracted text. Bytes and
text are keyed by content hash in the object store, so identical bytes fetched twice, by
whoever and from whatever URL, share one copy of each; a snapshot row is one fetch. A
snapshot's text is `ready` at once for a page or a plain-text file, `parsing` until the parse
queue has done the first pages of a document, `partial` while the rest waits for the agent to
read that far, and `failed` with the reason when no more can be made."""

import hashlib
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.db.base import utcnow
from public_atlas.integrations.parse import PAGE_SEPARATOR
from public_atlas.integrations.storage import ObjectNotFoundError, ObjectStore
from public_atlas.modules.evidence.media import FILENAME_LENGTH
from public_atlas.modules.evidence.models import Snapshot, TextStatus
from public_atlas.modules.graph.models import Webpage

# How much of a failure's message the row keeps.
ERROR_LENGTH = 2000


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bytes_key(digest: str) -> str:
    return f"snapshots/{digest}/bytes"


def text_key(digest: str) -> str:
    return f"snapshots/{digest}/text"


def page_count_of(text: str) -> int:
    return text.count(PAGE_SEPARATOR) + 1


def has_text(snapshot: Snapshot) -> bool:
    """Whether the snapshot's text, whole or partial, is there to read and to share."""
    return snapshot.text_key is not None and snapshot.text_status in (
        TextStatus.READY,
        TextStatus.PARTIAL,
    )


def _copy_text(target: Snapshot, source: Snapshot) -> None:
    target.text_key = source.text_key
    target.text_status = source.text_status
    target.page_count = source.page_count
    target.parsed_pages = source.parsed_pages
    target.text_error = None


async def _same_bytes(session: AsyncSession, digest: str) -> list[Snapshot]:
    """Every snapshot of these bytes whose objects are still in the store, those with text
    first, the most complete of them before the rest."""
    rows = await session.scalars(
        select(Snapshot)
        .where(Snapshot.content_hash == digest, Snapshot.pruned_at.is_(None))
        .order_by(Snapshot.fetched_at.desc())
    )
    return sorted(rows, key=lambda row: (not has_text(row), -(row.parsed_pages or 0)))


async def store_snapshot(  # noqa: PLR0913
    session: AsyncSession,
    store: ObjectStore,
    webpage: Webpage,
    data: bytes,
    *,
    text: str | None,
    media_type: str,
    filename: str | None,
    assignment_id: uuid.UUID | None = None,
    fetched_at: datetime | None = None,
    write_store: bool = True,
) -> tuple[Snapshot, bool]:
    """The snapshot of `data` for `webpage` and `assignment_id`: the one an earlier fetch of
    the same bytes by the same assignment made, else a new one. Whether it was created.

    `text` is the extracted text when the caller has it (a page's rendered text, a list file's
    lines); None leaves the snapshot `parsing` for the parse queue, unless the same bytes were
    parsed before, whose text is then shared. `write_store=False` writes the row and not the
    objects, for a dry run that rolls back.
    """
    digest = content_hash(data)
    existing = await session.scalar(
        select(Snapshot)
        .where(
            Snapshot.webpage_id == webpage.id,
            Snapshot.content_hash == digest,
            Snapshot.assignment_id == assignment_id,
            Snapshot.pruned_at.is_(None),
        )
        .order_by(Snapshot.fetched_at.desc())
        .limit(1)
    )
    if existing is not None:
        return existing, False
    same = await _same_bytes(session, digest)
    shared = next((row for row in same if has_text(row)), None)
    snapshot = Snapshot(
        webpage_id=webpage.id,
        assignment_id=assignment_id,
        fetched_at=fetched_at or utcnow(),
        content_hash=digest,
        media_type=media_type,
        size=len(data),
        filename=filename[:FILENAME_LENGTH] if filename else None,
        bytes_key=bytes_key(digest),
        text_key=None,
        text_status=TextStatus.PARSING,
    )
    if text is not None:
        snapshot.text_key = text_key(digest)
        snapshot.text_status = TextStatus.READY
        snapshot.page_count = snapshot.parsed_pages = page_count_of(text)
    elif shared is not None:
        _copy_text(snapshot, shared)
    session.add(snapshot)
    await session.flush()
    if write_store:
        if not same:
            await store.put(snapshot.bytes_key, data, media_type)
        if text is not None and shared is None:
            await store.put(text_key(digest), text.encode(), "text/plain; charset=utf-8")
    return snapshot, True


async def share_text(session: AsyncSession, snapshot: Snapshot) -> bool:
    """Give `snapshot` the text an earlier parse of the same bytes made, if there is one: the
    whole text, or the most pages parsed so far."""
    for row in await _same_bytes(session, snapshot.content_hash):
        if row.id != snapshot.id and has_text(row):
            _copy_text(snapshot, row)
            await session.flush()
            return True
    return False


async def mark_text_ready(
    session: AsyncSession,
    store: ObjectStore,
    snapshot: Snapshot,
    text: str,
    *,
    page_count: int | None = None,
) -> None:
    """Store `text` as the snapshot's: the whole document, or its first pages when `page_count`
    says the document has more. Every other snapshot of the same bytes still waiting on its
    text, or holding fewer pages of it, gets this text too: they share the key."""
    parsed = page_count_of(text)
    total = parsed if page_count is None else max(page_count, parsed)
    await store.put(text_key(snapshot.content_hash), text.encode(), "text/plain; charset=utf-8")
    snapshot.text_key = text_key(snapshot.content_hash)
    snapshot.text_status = TextStatus.READY if parsed >= total else TextStatus.PARTIAL
    snapshot.page_count = total
    snapshot.parsed_pages = parsed
    snapshot.text_error = None
    for row in await _same_bytes(session, snapshot.content_hash):
        if row.id != snapshot.id and row.text_status in (TextStatus.PARSING, TextStatus.PARTIAL):
            _copy_text(row, snapshot)
    await session.flush()


async def mark_text_failed(session: AsyncSession, snapshot: Snapshot, error: str) -> None:
    """No more text will be made. Pages parsed before the failure stay readable."""
    if snapshot.text_status is not TextStatus.PARTIAL:
        snapshot.text_key = None
    snapshot.text_status = TextStatus.FAILED
    snapshot.text_error = error[:ERROR_LENGTH]
    await session.flush()


async def snapshot_text(store: ObjectStore, snapshot: Snapshot) -> str:
    """The extracted text, whole or partial; empty until there is some, and once the bytes
    were pruned."""
    if snapshot.text_key is None:
        return ""
    try:
        return (await store.get(snapshot.text_key)).decode()
    except ObjectNotFoundError:
        return ""


async def snapshot_bytes(store: ObjectStore, snapshot: Snapshot) -> bytes | None:
    if snapshot.pruned_at is not None:
        return None
    try:
        return await store.get(snapshot.bytes_key)
    except ObjectNotFoundError:
        return None


async def latest_snapshot(
    session: AsyncSession, webpage_id: uuid.UUID, *, assignment_id: uuid.UUID | None = None
) -> Snapshot | None:
    """The newest stored copy of the webpage with text to quote from (whole or partial), from
    this assignment when one is named."""
    query = (
        select(Snapshot)
        .where(
            Snapshot.webpage_id == webpage_id,
            Snapshot.text_key.is_not(None),
            Snapshot.pruned_at.is_(None),
        )
        .order_by(Snapshot.fetched_at.desc())
        .limit(1)
    )
    if assignment_id is not None:
        query = query.where(Snapshot.assignment_id == assignment_id)
    return await session.scalar(query)
