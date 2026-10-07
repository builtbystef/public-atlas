"""The shapes of eval runs and their scores as the API reads them."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from public_atlas.modules.assignments.models import AssignmentType


class EvalScoreOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject: str
    assignment_type: AssignmentType
    recall: float | None
    precision: float | None
    misses: list[dict[str, Any]]
    false_positives: list[dict[str, Any]]


class EvalRunOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    dataset_version: str
    model: str
    settings: dict[str, Any]
    cost: Decimal
    started_at: datetime
    finished_at: datetime | None


class EvalRunDetail(EvalRunOutput):
    scores: list[EvalScoreOutput]
