"""Work (spec section 4.5): runs, the assignments inside them, and what each one spent."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from public_atlas.db.base import Base, UUIDPrimaryKey, utcnow
from public_atlas.db.checked_strings import checked_string


class RunMode(StrEnum):
    # Spawned assignments are created `held`; a person releases them.
    STEP = "step"
    # Spawned assignments are queued at once.
    AUTO = "auto"


class RunStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


class AssignmentType(StrEnum):
    FIND_HOMEPAGE = "find_homepage"
    FIND_INSTITUTIONS = "find_institutions"
    FIND_SOURCES = "find_sources"


class AssignmentStatus(StrEnum):
    """The lifecycle: is it still going."""

    HELD = "held"
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    CANCELLED = "cancelled"


# An assignment is unique per subject and type while in one of these.
OPEN_STATUSES = (AssignmentStatus.HELD, AssignmentStatus.QUEUED, AssignmentStatus.RUNNING)


class AssignmentResult(StrEnum):
    """How a finished assignment ended."""

    COMPLETE = "complete"
    COMPLETE_WITH_GAPS = "complete_with_gaps"
    OUT_OF_BUDGET = "out_of_budget"
    NEEDS_REVIEW = "needs_review"
    NO_HOMEPAGE = "no_homepage"
    FAILED = "failed"


class UsageKind(StrEnum):
    MODEL = "model"
    SEARCH = "search"


class Run(UUIDPrimaryKey, Base):
    """A batch of work with a filter and a mode: the unit a person starts, pauses and stops."""

    __tablename__ = "runs"

    name: Mapped[str] = mapped_column(Text)
    country_code: Mapped[str] = mapped_column(ForeignKey("country_settings.country_code"))
    mode: Mapped[RunMode] = checked_string(RunMode, "mode")
    status: Mapped[RunStatus] = checked_string(RunStatus, "status", default=RunStatus.ACTIVE)
    # Administrative levels, institution types, assignment types, subject ids.
    filter: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_eval: Mapped[bool] = mapped_column(default=False)
    record_video: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Assignment(UUIDPrimaryKey, Base):
    """One bounded piece of agent work on one subject, inside a run."""

    __tablename__ = "assignments"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"), index=True)
    type: Mapped[AssignmentType] = checked_string(AssignmentType, "type")
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"))
    status: Mapped[AssignmentStatus] = checked_string(AssignmentStatus, "status", index=True)
    result: Mapped[AssignmentResult | None] = checked_string(AssignmentResult, "result")
    budget_requests: Mapped[int]
    budget_tokens: Mapped[int]
    requests_used: Mapped[int] = mapped_column(default=0)
    tokens_used: Mapped[int] = mapped_column(default=0)
    sessions: Mapped[int] = mapped_column(default=0)
    # Written at half a context window, read by the next session.
    handoff_note: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    # The types the agent looked for and did not find.
    types_not_found: Mapped[list[str]] = mapped_column(JSONB, default=list)
    last_error: Mapped[str | None] = mapped_column(Text)
    parent_assignment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assignments.id"))

    __table_args__ = (
        # Concurrent workers cannot queue the same work twice.
        Index(
            "ix_assignments_open_subject_type",
            "subject_id",
            "type",
            unique=True,
            postgresql_where=text(
                "status IN ({})".format(", ".join(f"'{status.value}'" for status in OPEN_STATUSES))
            ),
        ),
    )


class Usage(UUIDPrimaryKey, Base):
    """One priced model or search call."""

    __tablename__ = "usage"

    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignments.id"), index=True)
    kind: Mapped[UsageKind] = checked_string(UsageKind, "kind")
    provider: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text)
    # Tokens or requests.
    units: Mapped[int]
    cached_units: Mapped[int] = mapped_column(default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
