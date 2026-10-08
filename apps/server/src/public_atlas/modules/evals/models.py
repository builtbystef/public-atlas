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

    # The run (`is_eval`) whose assignments built the graph. The same row exists in the eval
    # database, where the assignments are; this one is the record.
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"))
    dataset_version: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The pilot's gates as the run was judged on them (`scorer.GateResult.as_json`); null until
    # the run is scored, and on runs recorded before gates were kept.
    gates: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB(none_as_null=True))


class EvalScore(UUIDPrimaryKey, Base):
    """One subject's score on one assignment type. Recall is null when the subject had nothing
    of the kind to find, precision when nothing of the kind was saved."""

    __tablename__ = "eval_scores"

    eval_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_runs.id"), index=True)
    subject: Mapped[str] = mapped_column(Text)
    assignment_type: Mapped[AssignmentType] = checked_string(AssignmentType, "assignment_type")
    recall: Mapped[float | None]
    precision: Mapped[float | None]
    # Every hit, miss and false positive, each with its kind and bucket (`scorer.Entry`). A
    # `wrong` entry is in both lists. Hits are null on scores recorded before they were kept.
    hits: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB(none_as_null=True))
    misses: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    false_positives: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
