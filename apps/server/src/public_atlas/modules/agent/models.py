"""Everything the agent saw, said and did, in order (spec section 4.5)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from public_atlas.db.base import Base, UUIDPrimaryKey
from public_atlas.db.checked_strings import checked_string


class EventKind(StrEnum):
    PROMPT = "prompt"
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    VIDEO = "video"


class AgentRunEvent(UUIDPrimaryKey, Base):
    """Written from the session's message list when it ends."""

    __tablename__ = "agent_run_events"

    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignments.id"))
    session: Mapped[int]
    position: Mapped[int]
    kind: Mapped[EventKind] = checked_string(EventKind, "kind")
    tool: Mapped[str | None] = mapped_column(Text)
    # The prompt, the model's words, the arguments, the result, or a storage key.
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("assignment_id", "session", "position"),)
