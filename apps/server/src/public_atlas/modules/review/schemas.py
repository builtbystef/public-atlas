"""The request and response bodies of the review routes."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from public_atlas.modules.assignments.models import AssignmentStatus, AssignmentType
from public_atlas.modules.assignments.schemas import SkipReason
from public_atlas.modules.graph.models import EntityKind, EntityStatus
from public_atlas.modules.graph.schemas import EvidenceOutput
from public_atlas.modules.review.models import ReviewStatus

# What the queue sorts by: how many items a row has, or when its first was raised.
RowSort = Literal["count", "raised_at"]
# The rows of one item, or of several.
Affects = Literal["one", "several"]

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


class ReviewMember(BaseModel):
    """An item of a queue row, with what to recognise its entity by."""

    id: uuid.UUID
    entity_id: uuid.UUID
    entity_kind: EntityKind
    label: str
    country_code: str | None
    reasons: list[str]
    raised_at: datetime
    raised_by_assignment_id: uuid.UUID | None


class ReviewRow(BaseModel):
    """A line of the queue: an item on its own, or every item of one `kind` and status, which
    ask the same question and are decided together."""

    id: uuid.UUID = Field(description="The row's first item's id.")
    kind: str | None
    rule: str
    status: ReviewStatus
    question: dict[str, Any] = Field(description="The facts every item has, reasons aside.")
    count: int = Field(description="The row's items that match the filters.")
    raised_at: datetime = Field(description="When the first item was raised.")
    decided_at: datetime | None = Field(description="When the last item was decided.")
    members: list[ReviewMember] = Field(description="The first items, oldest first.")
    item_ids: list[uuid.UUID] = Field(description="Every item of the row, to decide them by.")


class EntityRefOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_kind: EntityKind
    label: str


class EntitySummaryOutput(BaseModel):
    """What to compare an entity by; a field that does not apply to its kind is null or empty."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_kind: EntityKind
    status: EntityStatus
    label: str
    names: list[str]
    institution_type: str | None
    suggested_type: str | None = Field(description="The type a body saved as `other` would have.")
    administrative_level: str | None
    country_code: str | None
    place: EntityRefOutput | None = Field(
        description="An institution's place, or a place's parent."
    )
    parent: EntityRefOutput | None = Field(description="An institution's parent institution.")
    owner: EntityRefOutput | None = Field(
        description="The institution a homepage or source belongs to, or that a domain's "
        "question is about."
    )
    url: str | None = Field(description="A homepage's or a source's page.")
    homepage_url: str | None = Field(description="An institution's verified homepage.")
    evidence_count: int


class RelatedOutput(BaseModel):
    """An entity the question names, under the fact that names it, such as `duplicate_of`."""

    model_config = ConfigDict(from_attributes=True)

    fact: str
    entity: EntitySummaryOutput


class AssignmentRefOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: AssignmentType
    status: AssignmentStatus
    subject: EntityRefOutput
    created_at: datetime


class StatusChangeOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity: EntityRefOutput
    before: EntityStatus
    after: EntityStatus


class PlannedOutput(BaseModel):
    """Work a decision asks for. `skipped` says why it would not start; null when it would."""

    model_config = ConfigDict(from_attributes=True)

    type: AssignmentType
    subject: EntityRefOutput
    skipped: SkipReason | None


class RunRefOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class DecisionPreviewOutput(BaseModel):
    """What a decision would do, from the decision run and rolled back."""

    model_config = ConfigDict(from_attributes=True)

    changes: list[StatusChangeOutput] = Field(
        description="Each entity whose status would change, in the order the decision changes it."
    )
    spawn: list[PlannedOutput]
    run: RunRefOutput | None = Field(
        description="The run the work would start in; null when no run would take it."
    )


class ReviewItemDetail(ReviewItemOutput):
    entity_kind: EntityKind
    label: str
    subject: EntitySummaryOutput
    entity: dict[str, Any] = Field(description="The entity's own columns.")
    evidence: list[EvidenceOutput]
    related: list[RelatedOutput] = Field(description="Every entity the question names by id.")
    raised_at: datetime
    raised_by: AssignmentRefOutput | None
    same_kind_open: int = Field(description="The other open items that ask the same question.")
    started_since: list[AssignmentRefOutput] = Field(
        description="The assignments on the entity or its institution made since the decision."
    )
    next_open_id: uuid.UUID | None = Field(
        description="The open item to look at next: another of the same question first, else "
        "the one raised before this, as the queue lists them."
    )


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


class KindDecisionInput(DecisionInput):
    kind: str = Field(max_length=300)
    item_ids: list[uuid.UUID] | None = Field(
        default=None,
        min_length=1,
        description="Decide these open items of the kind, the ones the reviewer saw; else all.",
    )


class KindApproveInput(KindDecisionInput):
    institution_type: str | None = TypeName


class KindDecisionOutput(BaseModel):
    kind: str
    review_items: list[ReviewItemOutput]
    spawn: list[SpawnOutput]
    assignment_ids: list[uuid.UUID] = []
