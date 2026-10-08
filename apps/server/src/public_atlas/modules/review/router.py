"""The review API (spec section 11, page 4): the open items with their snapshot and quotes,
and the decisions. Each decision commits with what it set in motion."""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Query

from public_atlas.dependencies import ObjectStoreDep, ResourcesDep, SessionDep, SettingsDep
from public_atlas.modules.assignments import service as assignments
from public_atlas.modules.assignments.service import Spawn
from public_atlas.modules.graph.models import EntityKind
from public_atlas.modules.graph.schemas import SortOrder
from public_atlas.modules.review import preview, reading, service
from public_atlas.modules.review.models import ReviewStatus
from public_atlas.modules.review.schemas import (
    Affects,
    ApproveInput,
    AssignmentRefOutput,
    DecisionInput,
    DecisionOutput,
    DecisionPreviewOutput,
    EntitySummaryOutput,
    EvidenceOutput,
    KindApproveInput,
    KindDecisionInput,
    KindDecisionOutput,
    MergeInput,
    RelatedOutput,
    ReviewItemDetail,
    ReviewItemOutput,
    ReviewMember,
    ReviewRow,
    RowSort,
    SpawnOutput,
)
from public_atlas.shared.pagination import Page

router = APIRouter(prefix="/review-items", tags=["review"])


def _spawn(spawn: Sequence[Spawn]) -> list[SpawnOutput]:
    return [SpawnOutput(type=item.type, subject_id=item.subject_id) for item in spawn]


async def _spawned(
    session: SessionDep,
    resources: ResourcesDep,
    items: Sequence[service.ReviewItem],
    spawn: Sequence[Spawn],
) -> list[uuid.UUID]:
    """The work a decision asked for, as assignments of the run it belongs to (spec section
    7.3): the run of the assignment that raised the first item, else the newest run of the
    country still going. With no such run the work waits for the next run to seed itself."""
    if not spawn or not items:
        return []
    first = items[0]
    run = await assignments.run_for_decision(
        session,
        assignment_id=first.raised_by_assignment_id,
        country_code=await service.country_of(session, first),
    )
    if run is None:
        return []
    created = await assignments.spawn(session, resources.jobs, run, spawn)
    return [assignment.id for assignment in created]


async def _decision(
    session: SessionDep, resources: ResourcesDep, decision: service.Decision
) -> DecisionOutput:
    spawned = await _spawned(session, resources, [decision.item], decision.spawn)
    await session.commit()
    return DecisionOutput(
        review_item=ReviewItemOutput.model_validate(decision.item),
        spawn=_spawn(decision.spawn),
        assignment_ids=spawned,
    )


async def _kind_decision(
    session: SessionDep, resources: ResourcesDep, decision: service.KindDecision
) -> KindDecisionOutput:
    spawned = await _spawned(session, resources, decision.items, decision.spawn)
    await session.commit()
    return KindDecisionOutput(
        kind=decision.kind,
        review_items=[ReviewItemOutput.model_validate(item) for item in decision.items],
        spawn=_spawn(decision.spawn),
        assignment_ids=spawned,
    )


def _row(row: service.Row) -> ReviewRow:
    first = row.members[0].item
    return ReviewRow(
        id=first.id,
        kind=row.kind,
        rule=row.rule,
        status=row.status,
        question=row.question,
        count=row.count,
        raised_at=service.raised_at(first.id),
        decided_at=row.decided_at,
        members=[
            ReviewMember(
                id=member.item.id,
                entity_id=member.item.entity_id,
                entity_kind=member.entity_kind,
                label=member.label,
                country_code=member.country_code,
                reasons=[str(reason) for reason in member.item.question.get("reasons", [])],
                raised_at=service.raised_at(member.item.id),
                raised_by_assignment_id=member.item.raised_by_assignment_id,
            )
            for member in row.members
        ],
        item_ids=row.item_ids,
    )


@router.get("")
async def list_review_items(  # noqa: PLR0913, PLR0917 - one argument per filter
    session: SessionDep,
    status: Annotated[ReviewStatus | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    rule: Annotated[str | None, Query(max_length=100)] = None,
    kind: Annotated[str | None, Query(max_length=200)] = None,
    entity_kind: Annotated[EntityKind | None, Query()] = None,
    country_code: Annotated[str | None, Query(pattern=r"^[A-Z]{2}$")] = None,
    affects: Annotated[Affects | None, Query()] = None,
    sort: RowSort = "count",
    order: SortOrder = "desc",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ReviewRow]:
    """A page of the queue, any status unless one is asked for. The items of one kind and
    status are one row, decided together; every other item is a row of its own. `q` matches the
    entity's name or URL, or the question's text; `kind` keeps one shared question. A row counts
    the items the filters admit."""
    filters = service.RowFilters(
        status=status,
        q=q,
        rule=rule,
        kind=kind,
        entity_kind=entity_kind,
        country_code=country_code,
        affects=affects,
    )
    rows, total = await service.list_rows(
        session, filters, sort=sort, order=order, limit=limit, offset=offset
    )
    return Page(items=[_row(row) for row in rows], total=total, limit=limit, offset=offset)


# Declared before `/{review_item_id}`, or "kinds" would be read as an id.
@router.post("/kinds/approve")
async def approve_review_kind(
    body: KindApproveInput, session: SessionDep, resources: ResourcesDep
) -> KindDecisionOutput:
    """Approve every open item of the kind, or the `item_ids` among them. A `new_type` kind
    gives its bodies the type named, by default the suggested type as a type name; the type must
    exist."""
    decision = await service.decide_kind(
        session,
        body.kind,
        approved=True,
        note=body.note,
        institution_type=body.institution_type,
        item_ids=body.item_ids,
    )
    return await _kind_decision(session, resources, decision)


@router.post("/kinds/reject")
async def reject_review_kind(
    body: KindDecisionInput, session: SessionDep, resources: ResourcesDep
) -> KindDecisionOutput:
    """Reject every open item of the kind, or the `item_ids` among them."""
    decision = await service.decide_kind(
        session, body.kind, approved=False, note=body.note, item_ids=body.item_ids
    )
    return await _kind_decision(session, resources, decision)


@router.post("/kinds/approve/preview")
async def preview_review_kind_approval(
    body: KindApproveInput, session: SessionDep
) -> DecisionPreviewOutput:
    """What approving the kind would do, without doing it."""
    return _preview(
        await preview.preview(
            session,
            lambda: service.decide_kind(
                session,
                body.kind,
                approved=True,
                note=body.note,
                institution_type=body.institution_type,
                item_ids=body.item_ids,
            ),
        )
    )


@router.post("/kinds/reject/preview")
async def preview_review_kind_rejection(
    body: KindDecisionInput, session: SessionDep
) -> DecisionPreviewOutput:
    """What rejecting the kind would do, without doing it."""
    return _preview(
        await preview.preview(
            session,
            lambda: service.decide_kind(
                session, body.kind, approved=False, note=body.note, item_ids=body.item_ids
            ),
        )
    )


@router.get("/{review_item_id}")
async def read_review_item(
    review_item_id: uuid.UUID, session: SessionDep, store: ObjectStoreDep, settings: SettingsDep
) -> ReviewItemDetail:
    """The item with a summary of its entity and of each entity its question names, every
    quote for the entity with a link to the stored copy it was found on, the assignment that
    raised it, how many other open items ask the same question, what was started since the
    decision, and the next open item."""
    item = await service.get_item(session, review_item_id)
    detail = await reading.read_item(session, store, item, url_ttl=settings.storage_url_ttl)
    return ReviewItemDetail(
        **ReviewItemOutput.model_validate(item).model_dump(),
        entity_kind=detail.subject.entity_kind,
        label=detail.subject.label,
        subject=EntitySummaryOutput.model_validate(detail.subject, from_attributes=True),
        entity=detail.entity,
        evidence=[
            EvidenceOutput.model_validate(row, from_attributes=True) for row in detail.evidence
        ],
        related=[
            RelatedOutput.model_validate(related, from_attributes=True)
            for related in detail.related
        ],
        raised_at=detail.raised_at,
        raised_by=(
            AssignmentRefOutput.model_validate(detail.raised_by, from_attributes=True)
            if detail.raised_by
            else None
        ),
        same_kind_open=detail.same_kind_open,
        started_since=[
            AssignmentRefOutput.model_validate(row, from_attributes=True)
            for row in detail.started_since
        ],
        next_open_id=detail.next_open_id,
    )


@router.post("/{review_item_id}/approve")
async def approve_review_item(
    review_item_id: uuid.UUID, body: ApproveInput, session: SessionDep, resources: ResourcesDep
) -> DecisionOutput:
    """The entity is what the agent said. An institution saved as `other` may be given its type.
    The work the approval asks for is created in the run it belongs to."""
    item = await service.get_item(session, review_item_id)
    decision = await service.approve(
        session, item, note=body.note, institution_type=body.institution_type
    )
    return await _decision(session, resources, decision)


@router.post("/{review_item_id}/reject")
async def reject_review_item(
    review_item_id: uuid.UUID, body: DecisionInput, session: SessionDep, resources: ResourcesDep
) -> DecisionOutput:
    item = await service.get_item(session, review_item_id)
    decision = await service.reject(session, item, note=body.note)
    return await _decision(session, resources, decision)


@router.post("/{review_item_id}/merge")
async def merge_review_item(
    review_item_id: uuid.UUID, body: MergeInput, session: SessionDep, resources: ResourcesDep
) -> DecisionOutput:
    """The entity is a duplicate of `into_id`: what it holds moves over and it is rejected."""
    item = await service.get_item(session, review_item_id)
    decision = await service.merge(session, item, into_id=body.into_id, note=body.note)
    return await _decision(session, resources, decision)


def _preview(found: preview.Preview) -> DecisionPreviewOutput:
    return DecisionPreviewOutput.model_validate(found, from_attributes=True)


@router.post("/{review_item_id}/approve/preview")
async def preview_review_item_approval(
    review_item_id: uuid.UUID, body: ApproveInput, session: SessionDep
) -> DecisionPreviewOutput:
    """What approving the item would do: the statuses it would change and the work it would
    start, from the approval itself, rolled back. Refused as the approval would be."""
    item = await service.get_item(session, review_item_id)
    return _preview(
        await preview.preview(
            session,
            lambda: service.approve(
                session, item, note=body.note, institution_type=body.institution_type
            ),
        )
    )


@router.post("/{review_item_id}/reject/preview")
async def preview_review_item_rejection(
    review_item_id: uuid.UUID, body: DecisionInput, session: SessionDep
) -> DecisionPreviewOutput:
    """What rejecting the item would do, without doing it."""
    item = await service.get_item(session, review_item_id)
    return _preview(
        await preview.preview(session, lambda: service.reject(session, item, note=body.note))
    )


@router.post("/{review_item_id}/merge/preview")
async def preview_review_item_merge(
    review_item_id: uuid.UUID, body: MergeInput, session: SessionDep
) -> DecisionPreviewOutput:
    """What merging the item's entity into `into_id` would do, without doing it."""
    item = await service.get_item(session, review_item_id)
    return _preview(
        await preview.preview(
            session,
            lambda: service.merge(session, item, into_id=body.into_id, note=body.note),
        )
    )
