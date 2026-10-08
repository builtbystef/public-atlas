"""The shapes of eval runs and their scores as the API reads them."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from public_atlas.modules.assignments.models import AssignmentType
from public_atlas.modules.evals.scorer import GATES


class EvalEntry(BaseModel):
    """One judged thing (`scorer.Entry`): a hit, a miss, a false positive, or `wrong` (saved,
    but not what the dataset expects: a miss and a false positive at once). The bucket says
    why it counts as it does; the group is what it is (an institution or source type, or
    `parent`, `homepage`, `domain`)."""

    kind: Literal["hit", "miss", "false_positive", "wrong"]
    line: str
    bucket: str
    group: str | None = None


class EvalScoreOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject: str
    assignment_type: AssignmentType
    recall: float | None
    precision: float | None
    # Null on scores recorded before hits were kept.
    hits: list[EvalEntry] | None
    misses: list[EvalEntry]
    false_positives: list[EvalEntry]


class TypeSummary(BaseModel):
    """One assignment type's scores over the subjects of a run: how many subjects were judged
    on it, the mean of their recall and precision (unweighted: each subject counts once), and
    the entries summed over them (hits null when no score kept them)."""

    subjects: int
    mean_recall: float | None
    mean_precision: float | None
    hits: int | None
    misses: int
    false_positives: int


class GateOutput(BaseModel):
    """A pilot target the run is judged on: a recall floor on one assignment type. Hits and
    misses are null when the run was not judged on it: still running, or recorded before
    gates were kept, in which case the floor is today's. The verdict is null when there was
    nothing to judge."""

    name: str
    assignment_type: AssignmentType
    what: str
    floor: float
    hits: int | None
    misses: int | None
    recall: float | None
    verdict: Literal["pass", "fail"] | None


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
    summary: dict[AssignmentType, TypeSummary] = {}
    gates: list[GateOutput] = []

    @field_validator("gates", mode="before")
    @classmethod
    def _recorded_or_today(cls, value: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """The gates as recorded (`scorer.GateResult.as_json`, whose verdict is `-` when there
        was nothing to judge), or today's floors, unjudged, when none were."""
        if value is None:
            return [
                {
                    "name": gate.name,
                    "assignment_type": gate.measure,
                    "what": gate.what(),
                    "floor": gate.floor,
                    "hits": None,
                    "misses": None,
                    "recall": None,
                    "verdict": None,
                }
                for gate in GATES
            ]
        return [{**gate, "verdict": None} if gate.get("verdict") == "-" else gate for gate in value]


class EvalRunDetail(EvalRunOutput):
    scores: list[EvalScoreOutput]
    # The finished eval run started last before this one, to compare against.
    previous_id: uuid.UUID | None
