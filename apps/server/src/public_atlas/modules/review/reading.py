"""A review item as its page shows it (spec section 11, page 4): the item, its entity and every
entity its question names, each summarised alike so a duplicate can be set beside its match;
the evidence; the assignment that raised it; the other open items that ask the same question;
the assignments started since the decision; and the next open item to look at. Reads only."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.integrations.storage import ObjectStore
from public_atlas.modules.assignments.models import Assignment, AssignmentStatus, AssignmentType
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.evidence.models import Evidence
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph.models import (
    Domain,
    Entity,
    EntityKind,
    EntityStatus,
    Homepage,
    Institution,
    Place,
    Source,
    Webpage,
)
from public_atlas.modules.review.models import ReviewItem, ReviewStatus
from public_atlas.modules.review.service import raised_at
from public_atlas.shared.exceptions import NotFoundError

__all__ = [
    "AssignmentRef",
    "EntityRef",
    "EntitySummary",
    "ItemDetail",
    "Related",
    "entity_ref",
    "read_item",
]

# The assignments the page lists as started since the decision.
STARTED_SHOWN = 20


@dataclass(frozen=True, slots=True)
class EntityRef:
    id: uuid.UUID
    entity_kind: EntityKind
    label: str


@dataclass(frozen=True, slots=True)
class EntitySummary:
    """What to compare an entity by. A field that does not apply to its kind is None or empty:
    `place` is an institution's place or a place's parent, `owner` the institution a homepage or
    source belongs to, or that a domain's question names the claim of."""

    id: uuid.UUID
    entity_kind: EntityKind
    status: EntityStatus
    label: str
    names: list[str]
    institution_type: str | None
    # The type an institution saved as `other` would have.
    suggested_type: str | None
    administrative_level: str | None
    country_code: str | None
    place: EntityRef | None
    parent: EntityRef | None
    owner: EntityRef | None
    # A homepage's or a source's page.
    url: str | None
    # An institution's verified homepage.
    homepage_url: str | None
    evidence_count: int


@dataclass(frozen=True, slots=True)
class Related:
    """An entity the question names, under the fact that names it (`duplicate_of`,
    `homepage_id`, `institution_id`)."""

    fact: str
    entity: EntitySummary


@dataclass(frozen=True, slots=True)
class AssignmentRef:
    id: uuid.UUID
    type: AssignmentType
    status: AssignmentStatus
    subject: EntityRef
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ItemDetail:
    item: ReviewItem
    subject: EntitySummary
    # The entity's own columns, for a reader who needs more than the summary.
    entity: dict[str, Any]
    evidence: list[evidence.EvidenceDetail]
    related: list[Related]
    raised_at: datetime
    raised_by: AssignmentRef | None
    # The other open items of the item's kind; 0 for an item without one.
    same_kind_open: int
    # The assignments on the entity or its owner created since the decision.
    started_since: list[AssignmentRef]
    next_open_id: uuid.UUID | None


async def read_item(
    session: AsyncSession, store: ObjectStore, item: ReviewItem, *, url_ttl: timedelta
) -> ItemDetail:
    """The item with everything its page shows."""
    entity = await _entity(session, item.entity_id)
    named = await _named(session, item)
    counts = await _evidence_counts(session, [entity.id, *(found.id for _, found in named)])
    subject = await _summary(session, entity, item.question, counts)
    return ItemDetail(
        item=item,
        subject=subject,
        entity=await _columns(session, entity),
        evidence=await evidence.evidence_details(session, store, [entity.id], url_ttl=url_ttl),
        related=[
            Related(fact, await _summary(session, found, {}, counts)) for fact, found in named
        ],
        raised_at=raised_at(item.id),
        raised_by=await _assignment(session, item.raised_by_assignment_id),
        same_kind_open=await _same_kind_open(session, item),
        started_since=await _started_since(session, item, subject),
        next_open_id=await _next_open(session, item),
    )


async def _entity(session: AsyncSession, entity_id: uuid.UUID) -> Entity:
    entity = await graph.entity_by_id(session, entity_id)
    if entity is None:  # pragma: no cover - the foreign key keeps the item's entity
        raise NotFoundError("the review item's entity is gone")
    return entity


def _ids_in(value: object) -> list[uuid.UUID]:
    """The ids a fact holds: one id, or a list of them; nothing for any other value."""
    values = value if isinstance(value, list) else [value]
    found = []
    for one in values:
        if not isinstance(one, str):
            continue
        try:
            found.append(uuid.UUID(one))
        except ValueError:
            continue
    return found


async def _named(session: AsyncSession, item: ReviewItem) -> list[tuple[str, Entity]]:
    """Every entity the question names by id, under its fact, in the question's order."""
    named: list[tuple[str, Entity]] = []
    seen = {item.entity_id}
    for fact, value in item.question.items():
        for entity_id in _ids_in(value):
            if entity_id in seen:
                continue
            seen.add(entity_id)
            entity = await graph.entity_by_id(session, entity_id)
            if entity is not None:
                named.append((fact, entity))
    return named


async def _evidence_counts(
    session: AsyncSession, entity_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, int]:
    rows = await session.execute(
        select(Evidence.entity_id, func.count())
        .where(Evidence.entity_id.in_(list(entity_ids)))
        .group_by(Evidence.entity_id)
    )
    return dict(rows.tuples().all())


async def entity_ref(session: AsyncSession, entity_id: uuid.UUID | None) -> EntityRef | None:
    """The entity's kind and label; None for no id or no entity."""
    if entity_id is None:
        return None
    entity = await graph.entity_by_id(session, entity_id)
    if entity is None:
        return None
    return EntityRef(entity.id, entity.kind, await graph.label_of(session, entity))


async def _url(session: AsyncSession, webpage_id: uuid.UUID | None) -> str | None:
    webpage = await session.get(Webpage, webpage_id) if webpage_id is not None else None
    return webpage.url if webpage is not None else None


async def _owner_id(
    session: AsyncSession, entity: Entity, question: dict[str, Any]
) -> uuid.UUID | None:
    """The institution a homepage or source belongs to; for a domain, the one its question
    names, or the owner of the homepage claim it names."""
    match entity:
        case Homepage() | Source():
            return entity.institution_id
        case Domain():
            [institution_id, *_] = _ids_in(question.get("institution_id")) or [None]
            if institution_id is not None:
                return institution_id
            [homepage_id, *_] = _ids_in(question.get("homepage_id")) or [None]
            claim = await session.get(Homepage, homepage_id) if homepage_id else None
            return claim.institution_id if claim is not None else None
        case _:
            return None


async def _country(session: AsyncSession, place_id: uuid.UUID | None) -> str | None:
    place = await session.get(Place, place_id) if place_id is not None else None
    return place.country_code if place is not None else None


async def _summary(
    session: AsyncSession, entity: Entity, question: dict[str, Any], counts: dict[uuid.UUID, int]
) -> EntitySummary:
    names: list[str] = []
    institution_type = suggested_type = level = country = url = homepage_url = None
    place = parent = None
    owner = await entity_ref(session, await _owner_id(session, entity, question))
    match entity:
        case Place():
            names = [alias.text for alias in await graph.names_of(session, entity)]
            level, country = entity.administrative_level, entity.country_code
            place = await entity_ref(session, entity.parent_place_id)
        case Institution():
            names = [alias.text for alias in await graph.names_of(session, entity)]
            institution_type, suggested_type = entity.institution_type, entity.suggested_type
            place = await entity_ref(session, entity.place_id)
            parent = await entity_ref(session, entity.parent_institution_id)
            country = await _country(session, entity.place_id)
            homepage = (
                await session.get(Homepage, entity.homepage_id) if entity.homepage_id else None
            )
            homepage_url = await _url(session, homepage.webpage_id) if homepage else None
        case Homepage() | Source():
            url = await _url(session, entity.webpage_id)
    if country is None and owner is not None:
        institution = await session.get(Institution, owner.id)
        country = await _country(session, institution.place_id) if institution else None
    return EntitySummary(
        id=entity.id,
        entity_kind=entity.kind,
        status=entity.status,
        label=await graph.label_of(session, entity),
        names=names,
        institution_type=institution_type,
        suggested_type=suggested_type,
        administrative_level=level,
        country_code=country,
        place=place,
        parent=parent,
        owner=owner,
        url=url,
        homepage_url=homepage_url,
        evidence_count=counts.get(entity.id, 0),
    )


async def _columns(session: AsyncSession, entity: Entity) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for table in type(entity).__table__.columns, Entity.__table__.columns:
        for column in table:
            value = getattr(entity, column.key, None)
            found[column.key] = str(value) if isinstance(value, uuid.UUID) else value
    if isinstance(entity, Homepage | Source):
        found["url"] = await _url(session, entity.webpage_id)
    return found


async def _assignment_ref(session: AsyncSession, assignment: Assignment) -> AssignmentRef:
    subject = await graph.entity_by_id(session, assignment.subject_id)
    if subject is None:  # pragma: no cover - the foreign key keeps the subject
        raise NotFoundError("the assignment's subject is gone")
    return AssignmentRef(
        id=assignment.id,
        type=assignment.type,
        status=assignment.status,
        subject=EntityRef(subject.id, subject.kind, await graph.label_of(session, subject)),
        created_at=assignment.created_at,
    )


async def _assignment(
    session: AsyncSession, assignment_id: uuid.UUID | None
) -> AssignmentRef | None:
    assignment = await session.get(Assignment, assignment_id) if assignment_id else None
    return await _assignment_ref(session, assignment) if assignment is not None else None


async def _same_kind_open(session: AsyncSession, item: ReviewItem) -> int:
    if item.kind is None:
        return 0
    count = await session.scalar(
        select(func.count()).where(
            ReviewItem.kind == item.kind,
            ReviewItem.status == ReviewStatus.OPEN,
            ReviewItem.id != item.id,
        )
    )
    return int(count or 0)


async def _started_since(
    session: AsyncSession, item: ReviewItem, subject: EntitySummary
) -> list[AssignmentRef]:
    """The assignments on the entity, or on the institution it belongs to, made since the
    decision: the work the decision spawned, and anything after it."""
    if item.decided_at is None:
        return []
    subjects = [subject.id] + ([subject.owner.id] if subject.owner else [])
    rows = await session.scalars(
        select(Assignment)
        .where(Assignment.subject_id.in_(subjects), Assignment.created_at >= item.decided_at)
        .order_by(Assignment.created_at)
        .limit(STARTED_SHOWN)
    )
    return [await _assignment_ref(session, assignment) for assignment in rows]


async def _next_open(session: AsyncSession, item: ReviewItem) -> uuid.UUID | None:
    """The open item to look at after this one: the oldest other of its kind, else the one
    raised before it, as the queue lists them newest first, else the newest."""
    others = select(ReviewItem.id).where(
        ReviewItem.status == ReviewStatus.OPEN, ReviewItem.id != item.id
    )
    if item.kind is not None:
        same = await session.scalar(
            others.where(ReviewItem.kind == item.kind).order_by(ReviewItem.id).limit(1)
        )
        if same is not None:
            return same
    older = await session.scalar(
        others.where(ReviewItem.id < item.id).order_by(ReviewItem.id.desc()).limit(1)
    )
    if older is not None:
        return older
    return await session.scalar(others.order_by(ReviewItem.id.desc()).limit(1))
