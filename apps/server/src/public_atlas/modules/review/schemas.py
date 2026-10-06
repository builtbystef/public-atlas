"""The request and response bodies of the review routes."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from public_atlas.modules.assignments.models import AssignmentType
from public_atlas.modules.graph.models import EntityKind
from public_atlas.modules.review.models import ReviewStatus

# A type name as the countries API takes one.
TypeName = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")


class ReviewItemOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_id: uuid.UUID
    rule: str
    question: dict[str, Any]
    kind: str | None
    status: ReviewStatus
    raised_by_assignment_id: uuid.UUID | None
    decided_at: datetime | None
    note: str | None


class EvidenceOutput(BaseModel):
    quote: str
    kind: str
    locator: int | None
    link_url: str | None
    page_url: str
    snapshot_url: str | None = Field(
        description="A short-lived download link to the stored page or file; null once pruned."
    )


class ReviewItemDetail(ReviewItemOutput):
    entity_kind: EntityKind
    entity_status: str
    label: str
    names: list[str]
    entity: dict[str, Any]
    evidence: list[EvidenceOutput]


class SpawnOutput(BaseModel):
    """Work the decision asks for; the assignments module queues it."""

    type: AssignmentType
    subject_id: uuid.UUID


class DecisionInput(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class ApproveInput(DecisionInput):
    institution_type: str | None = TypeName


class MergeInput(DecisionInput):
    into_id: uuid.UUID


class DecisionOutput(BaseModel):
    review_item: ReviewItemOutput
    spawn: list[SpawnOutput]
    # The assignments the spawn became, in the run of the assignment that raised the question
    # or the newest run of the country; empty when no run is going.
    assignment_ids: list[uuid.UUID] = []


class KindOutput(BaseModel):
    kind: str
    rule: str
    count: int
    question: dict[str, Any]
    names: list[str] = Field(description="The first few entities of the kind, to recognise it by.")
    item_ids: list[uuid.UUID]


class KindDecisionInput(DecisionInput):
    kind: str = Field(max_length=300)


class KindApproveInput(KindDecisionInput):
    institution_type: str | None = TypeName


class KindDecisionOutput(BaseModel):
    kind: str
    review_items: list[ReviewItemOutput]
    spawn: list[SpawnOutput]
    assignment_ids: list[uuid.UUID] = []
