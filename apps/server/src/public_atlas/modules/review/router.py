"""The review API (spec section 11, page 4): the open items with their snapshot and quotes,
and the decisions. Each decision commits with what it set in motion."""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Query

from public_atlas.dependencies import ObjectStoreDep, ResourcesDep, SessionDep, SettingsDep
from public_atlas.modules.assignments import service as assignments
from public_atlas.modules.assignments.service import Spawn
from public_atlas.modules.review import service
from public_atlas.modules.review.models import ReviewStatus
from public_atlas.modules.review.schemas import (
    ApproveInput,
    DecisionInput,
    DecisionOutput,
    EvidenceOutput,
    KindApproveInput,
    KindDecisionInput,
    KindDecisionOutput,
    KindOutput,
    MergeInput,
    ReviewItemDetail,
    ReviewItemOutput,
    SpawnOutput,
)

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


@router.get("")
async def list_review_items(
    session: SessionDep,
    status: Annotated[ReviewStatus | None, Query()] = ReviewStatus.OPEN,
    kind: Annotated[str | None, Query(max_length=300)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ReviewItemOutput]:
    """The items, open ones by default, oldest first."""
    items = await service.list_items(session, status=status, kind=kind, limit=limit, offset=offset)
    return [ReviewItemOutput.model_validate(item) for item in items]


# Declared before `/{review_item_id}`, or "kinds" would be read as an id.
@router.get("/kinds")
async def list_review_kinds(session: SessionDep) -> list[KindOutput]:
    """The open items grouped by the question they share; one call on a kind decides them all."""
    return [
        KindOutput(
            kind=kind.kind,
            rule=kind.rule,
            count=kind.count,
            question=kind.question,
            names=kind.names,
            item_ids=kind.item_ids,
        )
        for kind in await service.open_kinds(session)
    ]


@router.post("/kinds/approve")
async def approve_review_kind(
    body: KindApproveInput, session: SessionDep, resources: ResourcesDep
) -> KindDecisionOutput:
    """Approve every open item of the kind. A `new_type` kind gives its bodies the type named,
    by default the suggested type as a type name; the type must exist."""
    decision = await service.decide_kind(
        session, body.kind, approved=True, note=body.note, institution_type=body.institution_type
    )
    return await _kind_decision(session, resources, decision)


@router.post("/kinds/reject")
async def reject_review_kind(
    body: KindDecisionInput, session: SessionDep, resources: ResourcesDep
) -> KindDecisionOutput:
    """Reject every open item of the kind."""
    decision = await service.decide_kind(session, body.kind, approved=False, note=body.note)
    return await _kind_decision(session, resources, decision)


@router.get("/{review_item_id}")
async def read_review_item(
    review_item_id: uuid.UUID, session: SessionDep, store: ObjectStoreDep, settings: SettingsDep
) -> ReviewItemDetail:
    """The item with its entity, the entity's names and status, and every quote for it with a
    link to the stored copy it was found on."""
    item = await service.get_item(session, review_item_id)
    detail = await service.read_item(session, store, item, url_ttl=settings.storage_url_ttl)
    return ReviewItemDetail(
        **ReviewItemOutput.model_validate(item).model_dump(),
        entity_kind=detail.entity_kind,
        entity_status=detail.entity_status,
        label=detail.label,
        names=detail.names,
        entity=detail.entity,
        evidence=[
            EvidenceOutput(
                quote=row.quote,
                kind=row.kind,
                locator=row.locator,
                link_url=row.link_url,
                page_url=row.page_url,
                snapshot_url=row.snapshot_url,
            )
            for row in detail.evidence
        ],
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
