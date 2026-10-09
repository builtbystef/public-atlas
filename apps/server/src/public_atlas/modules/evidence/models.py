"""Stored copies of pages and the quotes taken from them (spec section 4.3)."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from public_atlas.db.base import Base, UUIDPrimaryKey, utcnow
from public_atlas.db.checked_strings import checked_string
from public_atlas.modules.graph.models import EnteredBy


class TextStatus(StrEnum):
    # Every page's text is stored.
    READY = "ready"
    # Nothing is stored yet; the parse queue has the file.
    PARSING = "parsing"
    # The first pages' text is stored; the rest is parsed when the agent reads that far.
    PARTIAL = "partial"
    # No more text will be made; what was parsed before the failure, if anything, stays.
    FAILED = "failed"


class EvidenceKind(StrEnum):
    # The quote is on the page.
    APPEARS_ON = "appears_on"
    # The page links to `link_url`, and the quote is the link's text.
    LINKS_TO = "links_to"


class Snapshot(UUIDPrimaryKey, Base):
    """A stored copy of a page or file as fetched, plus its extracted text. Identical bytes
    fetched twice share one text, keyed by content hash."""

    __tablename__ = "snapshots"

    webpage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("webpages.id"), index=True)
    # Null when the loader wrote the row.
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assignments.id"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    content_hash: Mapped[str] = mapped_column(Text, index=True)
    media_type: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(BigInteger)
    filename: Mapped[str | None] = mapped_column(Text)
    # Keys in the object store.
    bytes_key: Mapped[str] = mapped_column(Text)
    text_key: Mapped[str | None] = mapped_column(Text)
    text_status: Mapped[TextStatus] = checked_string(TextStatus, "text_status")
    # Why extraction failed.
    text_error: Mapped[str | None] = mapped_column(Text)
    # How many pages the document has, and how many of them the stored text holds, from the
    # first: equal once the text is `ready`.
    page_count: Mapped[int | None]
    parsed_pages: Mapped[int | None]
    # Set when the bytes were dropped because no evidence cites them; the hash and metadata stay.
    pruned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Evidence(UUIDPrimaryKey, Base):
    """A quote from a snapshot that supports an entity."""

    __tablename__ = "evidence"

    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), index=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("snapshots.id"), index=True)
    kind: Mapped[EvidenceKind] = checked_string(EvidenceKind, "kind")
    quote: Mapped[str] = mapped_column(Text)
    # The page of a file, or the line of a list file, the quote is on.
    locator: Mapped[int | None]
    link_url: Mapped[str | None] = mapped_column(Text)
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assignments.id"))
    entered_by: Mapped[EnteredBy] = checked_string(EnteredBy, "entered_by")


class BlockedAttempt(UUIDPrimaryKey, Base):
    """A URL the fence refused."""

    __tablename__ = "blocked_attempts"

    url: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignments.id"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
