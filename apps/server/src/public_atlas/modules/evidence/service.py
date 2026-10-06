"""Storing a copy of a page or file with its text, and the quotes taken from it. The browser's
capture hook (phase 2) and the list loader both store through here. Bytes and text are keyed by
content hash in the object store, so identical bytes fetched twice share one copy of each."""

import hashlib
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.db.base import utcnow
from public_atlas.integrations.storage import ObjectStore
from public_atlas.modules.evidence.models import Evidence, EvidenceKind, Snapshot, TextStatus
from public_atlas.modules.graph.models import EnteredBy, Webpage

# The longest file name a snapshot keeps.
FILENAME_LENGTH = 200


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bytes_key(digest: str) -> str:
    return f"snapshots/{digest}/bytes"


def text_key(digest: str) -> str:
    return f"snapshots/{digest}/text"


async def store_snapshot(  # noqa: PLR0913
    session: AsyncSession,
    store: ObjectStore,
    webpage: Webpage,
    data: bytes,
    *,
    text: str,
    media_type: str,
    filename: str | None,
    assignment_id: uuid.UUID | None = None,
    fetched_at: datetime | None = None,
    write_store: bool = True,
) -> tuple[Snapshot, bool]:
    """The snapshot of `data` for `webpage`, with its text ready: the one an earlier fetch of
    the same bytes made, else a new one. Whether it was created. `write_store=False` writes the
    row and not the objects, for a dry run that rolls back."""
    digest = content_hash(data)
    existing = await session.scalar(
        select(Snapshot)
        .where(
            Snapshot.webpage_id == webpage.id,
            Snapshot.content_hash == digest,
            Snapshot.text_status == TextStatus.READY,
            Snapshot.pruned_at.is_(None),
        )
        .order_by(Snapshot.fetched_at.desc())
        .limit(1)
    )
    if existing is not None:
        return existing, False
    snapshot = Snapshot(
        webpage_id=webpage.id,
        assignment_id=assignment_id,
        fetched_at=fetched_at or utcnow(),
        content_hash=digest,
        media_type=media_type,
        size=len(data),
        filename=filename[:FILENAME_LENGTH] if filename else None,
        bytes_key=bytes_key(digest),
        text_key=text_key(digest),
        text_status=TextStatus.READY,
    )
    session.add(snapshot)
    await session.flush()
    if write_store:
        await store.put(snapshot.bytes_key, data, media_type)
        await store.put(text_key(digest), text.encode(), "text/plain; charset=utf-8")
    return snapshot, True


async def snapshot_text(store: ObjectStore, snapshot: Snapshot) -> str:
    """The extracted text; empty until it is ready."""
    if snapshot.text_key is None or snapshot.text_status is not TextStatus.READY:
        return ""
    return (await store.get(snapshot.text_key)).decode()


async def add_evidence(  # noqa: PLR0913
    session: AsyncSession,
    *,
    entity_id: uuid.UUID,
    snapshot: Snapshot,
    kind: EvidenceKind,
    quote: str,
    entered_by: EnteredBy,
    locator: int | None = None,
    link_url: str | None = None,
    assignment_id: uuid.UUID | None = None,
) -> bool:
    """Record the quote for the entity, once per snapshot and quote. Whether a row was added.
    The quote check (phase 2) runs before this for the agent's saves; a list's own line needs
    none."""
    found = await session.scalar(
        select(Evidence.id)
        .where(
            Evidence.entity_id == entity_id,
            Evidence.snapshot_id == snapshot.id,
            Evidence.kind == kind,
            Evidence.quote == quote,
        )
        .limit(1)
    )
    if found is not None:
        return False
    session.add(
        Evidence(
            entity_id=entity_id,
            snapshot_id=snapshot.id,
            kind=kind,
            quote=quote,
            locator=locator,
            link_url=link_url,
            assignment_id=assignment_id,
            entered_by=entered_by,
        )
    )
    await session.flush()
    return True
