"""Eval runs and their scores (spec section 10). They live in the main database so history
survives a reset of the eval database."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from public_atlas.db.base import Base, UUIDPrimaryKey
from public_atlas.db.checked_strings import checked_string
from public_atlas.modules.assignments.models import AssignmentType


class EvalRun(UUIDPrimaryKey, Base):
    __tablename__ = "eval_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"))
    dataset_version: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvalScore(UUIDPrimaryKey, Base):
    __tablename__ = "eval_scores"

    eval_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_runs.id"), index=True)
    subject: Mapped[str] = mapped_column(Text)
    assignment_type: Mapped[AssignmentType] = checked_string(AssignmentType, "assignment_type")
    recall: Mapped[float]
    precision: Mapped[float]
    # The bucket of every miss and every false positive.
    misses: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    false_positives: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
