"""Questions a human must answer about one entity (spec section 6.5)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from public_atlas.db.base import Base, UUIDPrimaryKey
from public_atlas.db.checked_strings import checked_string


class ReviewStatus(StrEnum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"
    MERGED = "merged"


class ReviewItem(UUIDPrimaryKey, Base):
    __tablename__ = "review_items"

    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), index=True)
    # The rule that raised it.
    rule: Mapped[str] = mapped_column(Text)
    # What the reviewer sees.
    question: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # The shared question, when there is one ("may a library sit under a region"): items with one
    # kind are decided together.
    kind: Mapped[str | None] = mapped_column(Text, index=True)
    status: Mapped[ReviewStatus] = checked_string(
        ReviewStatus, "status", default=ReviewStatus.OPEN, index=True
    )
    raised_by_assignment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assignments.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
