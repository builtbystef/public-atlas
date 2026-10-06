"""Snapshots: a stored copy of a page or file as fetched, plus its extracted text. Bytes and
text are keyed by content hash in the object store, so identical bytes fetched twice, by
whoever and from whatever URL, share one copy of each; a snapshot row is one fetch. A
snapshot's text is `ready` at once for a page or a plain-text file, `parsing` until the parse
queue has done a document, and `failed` with the reason when it cannot be made."""

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


async def _same_bytes(session: AsyncSession, digest: str) -> list[Snapshot]:
    """Every snapshot of these bytes whose objects are still in the store, text ready first."""
    rows = await session.scalars(
        select(Snapshot)
        .where(Snapshot.content_hash == digest, Snapshot.pruned_at.is_(None))
        .order_by(Snapshot.fetched_at.desc())
    )
    return sorted(rows, key=lambda row: row.text_status is not TextStatus.READY)


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
    shared = next((row for row in same if row.text_status is TextStatus.READY), None)
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
        snapshot.page_count = page_count_of(text)
    elif shared is not None:
        snapshot.text_key = shared.text_key
        snapshot.text_status = TextStatus.READY
        snapshot.page_count = shared.page_count
    session.add(snapshot)
    await session.flush()
    if write_store:
        if not same:
            await store.put(snapshot.bytes_key, data, media_type)
        if text is not None and shared is None:
            await store.put(text_key(digest), text.encode(), "text/plain; charset=utf-8")
    return snapshot, True


async def share_text(session: AsyncSession, snapshot: Snapshot) -> bool:
    """Give `snapshot` the text an earlier parse of the same bytes made, if there is one."""
    for row in await _same_bytes(session, snapshot.content_hash):
        if row.id != snapshot.id and row.text_status is TextStatus.READY:
            snapshot.text_key = row.text_key
            snapshot.text_status = TextStatus.READY
            snapshot.page_count = row.page_count
            snapshot.text_error = None
            await session.flush()
            return True
    return False


async def mark_text_ready(
    session: AsyncSession, store: ObjectStore, snapshot: Snapshot, text: str
) -> None:
    await store.put(text_key(snapshot.content_hash), text.encode(), "text/plain; charset=utf-8")
    snapshot.text_key = text_key(snapshot.content_hash)
    snapshot.text_status = TextStatus.READY
    snapshot.page_count = page_count_of(text)
    snapshot.text_error = None
    await session.flush()


async def mark_text_failed(session: AsyncSession, snapshot: Snapshot, error: str) -> None:
    snapshot.text_key = None
    snapshot.text_status = TextStatus.FAILED
    snapshot.text_error = error[:ERROR_LENGTH]
    await session.flush()


async def snapshot_text(store: ObjectStore, snapshot: Snapshot) -> str:
    """The extracted text; empty until it is ready, and once the bytes were pruned."""
    if snapshot.text_key is None or snapshot.text_status is not TextStatus.READY:
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
    """The newest stored copy of the webpage with its text ready, from this assignment when one
    is named."""
    query = (
        select(Snapshot)
        .where(
            Snapshot.webpage_id == webpage_id,
            Snapshot.text_status == TextStatus.READY,
            Snapshot.pruned_at.is_(None),
        )
        .order_by(Snapshot.fetched_at.desc())
        .limit(1)
    )
    if assignment_id is not None:
        query = query.where(Snapshot.assignment_id == assignment_id)
    return await session.scalar(query)
