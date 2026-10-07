"""The shapes of runs and assignments as the API reads and writes them, and the run filter as
the `runs.filter` column stores it."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from public_atlas.modules.agent.models import EventKind
from public_atlas.modules.assignments.models import (
    AssignmentResult,
    AssignmentStatus,
    AssignmentType,
    RunMode,
    RunStatus,
)
from public_atlas.modules.graph.models import EntityKind, EntityStatus


class RunFilter(BaseModel):
    """What a run works on (spec section 7.1). An empty list is no restriction. The levels and
    types bound the subjects a run seeds itself with and every assignment it spawns; the subject
    ids name the places and institutions it starts from, and spawned work descends from them."""

    model_config = ConfigDict(extra="forbid")

    administrative_levels: list[str] = []
    institution_types: list[str] = []
    assignment_types: list[AssignmentType] = []
    subject_ids: list[uuid.UUID] = []


class RunInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    mode: RunMode
    filter: RunFilter = RunFilter()
    record_video: bool = False


class Progress(BaseModel):
    """How far a run has got and what it has spent."""

    by_status: dict[AssignmentStatus, int]
    by_result: dict[AssignmentResult, int]
    cost: Decimal


class RunOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    country_code: str
    mode: RunMode
    status: RunStatus
    filter: dict[str, Any]
    is_eval: bool
    record_video: bool
    created_at: datetime


class RunDetail(RunOutput):
    progress: Progress


class ReleaseInput(BaseModel):
    """Which held assignments to queue: a few at a time by default."""

    limit: int = Field(default=1, ge=1, le=1000)
    assignment_type: AssignmentType | None = None
    assignment_ids: list[uuid.UUID] = []


class SubjectOutput(BaseModel):
    """The place or institution an assignment works on, by name."""

    id: uuid.UUID
    kind: EntityKind
    name: str


class AssignmentOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    type: AssignmentType
    subject_id: uuid.UUID
    # None when the subject was merged away or deleted since.
    subject: SubjectOutput | None = None
    status: AssignmentStatus
    result: AssignmentResult | None
    budget_requests: int
    budget_tokens: int
    requests_used: int
    tokens_used: int
    sessions: int
    handoff_note: str | None
    summary: str | None
    types_not_found: list[str]
    last_error: str | None
    parent_assignment_id: uuid.UUID | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AssignmentDetail(AssignmentOutput):
    cost: Decimal


class EventOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session: int
    position: int
    kind: EventKind
    tool: str | None
    content: dict[str, Any]
    at: datetime
    # A short-lived link to play a recorded video; null for every other kind and once purged.
    video_url: str | None = None


class FindingOutput(BaseModel):
    """One thing the assignment saved, with the quote it gave for it."""

    evidence_id: uuid.UUID
    entity_id: uuid.UUID
    entity_kind: EntityKind
    entity_status: EntityStatus
    label: str
    # The institution a homepage or a source belongs to; the institution itself otherwise.
    institution_id: uuid.UUID | None
    quote: str
    kind: str
    page_url: str
    link_url: str | None
    snapshot_url: str | None
