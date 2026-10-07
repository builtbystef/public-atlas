"""The review queue (spec section 6.5): raising a question about one entity, and the decisions
a reviewer makes. Raising an item sets the entity to `needs_review`; approving, rejecting and
merging run the same `status_changes` functions the rules run, so nothing bypasses them. Items
that ask one shared question carry a `kind` and are decided together; the type questions among
them settle themselves when the country tables come to answer them.

The question is a JSON document the reviewer sees: `reasons`, one per time the rule fired, and
the facts the rule wants decided (`institution_type` and `level`, `suggested_type`, the
`homepage_id` a domain decision is about, the `duplicate_of` ids a save was unsure between).
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.db.base import utcnow
from public_atlas.integrations.storage import ObjectStore
from public_atlas.modules.assignments.service import Spawn
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.models import InstitutionType
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import (
    Domain,
    EnteredBy,
    Entity,
    EntityKind,
    Homepage,
    Institution,
    Place,
    Source,
    Webpage,
)
from public_atlas.modules.review.models import ReviewItem, ReviewStatus
from public_atlas.shared.exceptions import ConflictError, NotFoundError, UnprocessableError

__all__ = [
    "Decision",
    "ItemDetail",
    "Kind",
    "KindDecision",
    "Rule",
    "approve",
    "country_of",
    "decide_kind",
    "entity_kind_of",
    "kind_of",
    "labels_of",
    "list_items",
    "merge",
    "open_kinds",
    "raise_review",
    "read_item",
    "reject",
    "settle_type_items",
    "type_slug",
]


class Rule(StrEnum):
    """What raised the item. Two rules ask a shared question and get a kind."""

    # A known type at a level the country's tables do not expect it under.
    TYPE_LEVEL = "type_level"
    # A body saved as `other`, with the type the agent would have given it.
    NEW_TYPE = "new_type"
    # A name that misses its type's pattern.
    NAME_PATTERN = "name_pattern"
    # A save the duplicate search left the agent unsure about.
    DUPLICATE = "duplicate"
    # The domain checks of spec section 6.3 failed in a way the agent cannot fix.
    DOMAIN_CHECKS = "domain_checks"
    # A candidate homepage redirected somewhere the rules cannot follow.
    DOMAIN_MOVED = "domain_moved"
    # The searches found nothing.
    NO_HOMEPAGE = "no_homepage"
    # A discovery assignment closed with types still missing.
    GAPS = "gaps"
    # A page on a platform no trusted page links to.
    PLATFORM_SOURCE = "platform_source"
    # A homepage claim on a platform no trusted page links to.
    PLATFORM_HOMEPAGE = "platform_homepage"
    # The agent asked.
    AGENT = "agent"


# Names a kind's summary shows, enough to recognise it by.
SAMPLE_NAMES = 5
MAX_TYPE_NAME = 64
_NOT_A_WORD = re.compile(r"[^a-z0-9]+")


def type_slug(text: str) -> str:
    """A suggested type as a type name: "Housing Corporation" is `housing_corporation`."""
    slug = _NOT_A_WORD.sub("_", text.lower()).strip("_")[:MAX_TYPE_NAME]
    return slug if slug[:1].isalpha() else f"type_{slug}".strip("_")


def kind_of(rule: str, question: dict[str, Any]) -> str | None:
    """The shared question an item of `rule` asks, or None when the item stands alone or the
    question lacks the facts the kind is made of."""
    match rule:
        case Rule.TYPE_LEVEL if question.get("institution_type") and question.get("level"):
            return f"{Rule.TYPE_LEVEL}:{question['institution_type']}@{question['level']}"
        case Rule.NEW_TYPE if question.get("suggested_type"):
            return f"{Rule.NEW_TYPE}:{type_slug(question['suggested_type'])}"
        case _:
            return None


# --- Raising ---


async def raise_review(  # noqa: PLR0913
    session: AsyncSession,
    entity: Entity,
    *,
    rule: str,
    reason: str,
    question: dict[str, Any] | None = None,
    assignment_id: uuid.UUID | None = None,
) -> ReviewItem:
    """Open a review item and send the entity to review. One open item per entity: a second
    raise adds its reason to the first, and gives it the rule's kind when the first had none."""
    facts = dict(question or {})
    existing = await session.scalar(
        select(ReviewItem).where(
            ReviewItem.entity_id == entity.id, ReviewItem.status == ReviewStatus.OPEN
        )
    )
    if existing is not None:
        merged = dict(existing.question)
        reasons = list(merged.get("reasons", []))
        if reason not in reasons:
            reasons.append(reason)
        merged["reasons"] = reasons
        for key, value in facts.items():
            merged.setdefault(key, value)
        existing.question = merged
        kind = kind_of(rule, merged)
        if existing.kind is None and kind is not None:
            existing.kind = kind
            existing.rule = rule
        await session.flush()
        return existing
    item = ReviewItem(
        entity_id=entity.id,
        rule=rule,
        question={"reasons": [reason], **facts},
        kind=kind_of(rule, facts),
        raised_by_assignment_id=assignment_id,
    )
    session.add(item)
    await status_changes.send_to_review(session, entity)
    await session.flush()
    return item


async def _entity(session: AsyncSession, entity_id: uuid.UUID) -> Entity:
    entity = await graph.entity_by_id(session, entity_id)
    if entity is None:  # pragma: no cover - the foreign key keeps the item's entity
        raise NotFoundError("the review item's entity is gone")
    return entity


# --- Reading ---


async def list_items(  # noqa: PLR0913
    session: AsyncSession,
    *,
    status: ReviewStatus | None = ReviewStatus.OPEN,
    kind: str | None = None,
    rule: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[ReviewItem], int]:
    """A page of items, oldest first, and how many match."""
    query = select(ReviewItem)
    if status is not None:
        query = query.where(ReviewItem.status == status)
    if kind is not None:
        query = query.where(ReviewItem.kind == kind)
    if rule is not None:
        query = query.where(ReviewItem.rule == rule)
    rows = await session.scalars(query.order_by(ReviewItem.id).limit(limit).offset(offset))
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    return list(rows), int(total or 0)


async def entity_kind_of(session: AsyncSession, item: ReviewItem) -> EntityKind:
    return (await _entity(session, item.entity_id)).kind


async def labels_of(session: AsyncSession, items: Sequence[ReviewItem]) -> dict[uuid.UUID, str]:
    """What to recognise each item's entity by, by item id."""
    found: dict[uuid.UUID, str] = {}
    for item in items:
        found[item.id] = await graph.label_of(session, await _entity(session, item.entity_id))
    return found


async def get_item(session: AsyncSession, item_id: uuid.UUID) -> ReviewItem:
    item = await session.get(ReviewItem, item_id)
    if item is None:
        raise NotFoundError("no such review item")
    return item


@dataclass(frozen=True, slots=True)
class ItemDetail:
    item: ReviewItem
    entity_kind: EntityKind
    entity_status: str
    label: str
    names: list[str]
    # The entity's own columns, as the reviewer sees them.
    entity: dict[str, Any]
    evidence: list[evidence.EvidenceDetail]


async def read_item(
    session: AsyncSession, store: ObjectStore, item: ReviewItem, *, url_ttl: timedelta
) -> ItemDetail:
    """The item with its entity and every quote for it, each linked to the stored page."""
    entity = await _entity(session, item.entity_id)
    details = await evidence.evidence_details(session, store, [entity.id], url_ttl=url_ttl)
    names = (
        [alias.text for alias in await graph.names_of(session, entity)]
        if isinstance(entity, Place | Institution)
        else []
    )
    return ItemDetail(
        item=item,
        entity_kind=entity.kind,
        entity_status=entity.status.value,
        label=await graph.label_of(session, entity),
        names=names,
        entity=await _columns(session, entity),
        evidence=details,
    )


async def _columns(session: AsyncSession, entity: Entity) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for table in type(entity).__table__.columns, Entity.__table__.columns:
        for column in table:
            value = getattr(entity, column.key, None)
            found[column.key] = str(value) if isinstance(value, uuid.UUID) else value
    if isinstance(entity, Homepage | Source):
        found["url"] = (await session.get_one(Webpage, entity.webpage_id)).url
    return found


async def country_of(session: AsyncSession, item: ReviewItem) -> str | None:
    """The country the item's entity belongs to, for the run a decision spawns into: a place's
    own, an institution's place's, a homepage's or source's institution's, and for a domain the
    institution of the homepage claim the question names. None when nothing says."""
    entity = await _entity(session, item.entity_id)
    institution_id: uuid.UUID | None = None
    match entity:
        case Place():
            return entity.country_code
        case Institution():
            institution_id = entity.id
        case Homepage() | Source():
            institution_id = entity.institution_id
        case Domain():
            homepage_id = item.question.get("homepage_id")
            homepage = await session.get(Homepage, uuid.UUID(homepage_id)) if homepage_id else None
            institution_id = homepage.institution_id if homepage is not None else None
        case _:  # pragma: no cover - every kind is listed above
            return None
    if institution_id is None:
        return None
    institution = await session.get_one(Institution, institution_id)
    return (await session.get_one(Place, institution.place_id)).country_code


# --- Deciding ---


@dataclass(slots=True)
class Decision:
    item: ReviewItem
    spawn: list[Spawn] = field(default_factory=list)


def _close(item: ReviewItem, status: ReviewStatus, note: str | None) -> None:
    if item.status is not ReviewStatus.OPEN:
        raise ConflictError("the review item is decided already")
    item.status = status
    item.decided_at = utcnow()
    item.note = note


async def approve(
    session: AsyncSession,
    item: ReviewItem,
    *,
    note: str | None = None,
    institution_type: str | None = None,
) -> Decision:
    """The entity is what the agent said. A domain is verified and the homepage claim the
    question names is verified with it; an institution saved as `other` may be given its type
    here. Runs the function the rules run, and returns what it would spawn."""
    _close(item, ReviewStatus.APPROVED, note)
    entity = await _entity(session, item.entity_id)
    spawn = await _approve_entity(session, entity, item.question, institution_type=institution_type)
    await session.flush()
    return Decision(item=item, spawn=spawn)


async def _approve_entity(
    session: AsyncSession,
    entity: Entity,
    question: dict[str, Any],
    *,
    institution_type: str | None,
) -> list[Spawn]:
    by = EnteredBy.MANUAL
    if institution_type is not None and not isinstance(entity, Institution):
        raise UnprocessableError("institution_type is for an institution")
    match entity:
        case Domain():
            spawn = await status_changes.verify_domain(session, entity, entered_by=by)
            homepage_id = question.get("homepage_id")
            homepage = await session.get(Homepage, uuid.UUID(homepage_id)) if homepage_id else None
            if homepage is not None and homepage.status in status_changes.OPEN:
                spawn.extend(await status_changes.verify_homepage(session, homepage, entered_by=by))
            return spawn
        case Homepage():
            return await status_changes.verify_homepage(session, entity, entered_by=by)
        case Institution():
            if institution_type is not None:
                if await session.get(InstitutionType, institution_type) is None:
                    raise UnprocessableError(
                        f"no institution type {institution_type!r}: add it on the countries page"
                    )
                entity.institution_type = institution_type
                entity.suggested_type = None
            return await status_changes.verify_institution(session, entity, entered_by=by)
        case Place():
            return await status_changes.verify_place(session, entity, entered_by=by)
        case Source():
            return await status_changes.verify_source(session, entity, entered_by=by)
        case _:  # pragma: no cover - every kind is listed above
            raise UnprocessableError(f"cannot approve a {entity.kind}")


async def reject(session: AsyncSession, item: ReviewItem, *, note: str | None = None) -> Decision:
    """The entity is not what the agent said. A rejected domain sends every institution that
    claimed a homepage on it looking again."""
    _close(item, ReviewStatus.REJECTED, note)
    entity = await _entity(session, item.entity_id)
    reason = note or "rejected by a reviewer"
    by = EnteredBy.MANUAL
    match entity:
        case Domain():
            spawn = await status_changes.reject_domain(
                session, entity, entered_by=by, reason=reason
            )
        case Homepage():
            spawn = await status_changes.reject_homepage(
                session, entity, entered_by=by, reason=reason
            )
        case Institution():
            spawn = await status_changes.reject_institution(session, entity, entered_by=by)
        case Place():
            spawn = await status_changes.reject_place(session, entity, entered_by=by)
        case Source():
            spawn = await status_changes.reject_source(session, entity, entered_by=by)
        case _:  # pragma: no cover - every kind is listed above
            raise UnprocessableError(f"cannot reject a {entity.kind}")
    await session.flush()
    return Decision(item=item, spawn=spawn)


async def merge(
    session: AsyncSession, item: ReviewItem, *, into_id: uuid.UUID, note: str | None = None
) -> Decision:
    """The entity is a duplicate of `into_id`. The item and every other open item on the
    duplicate are closed as merged, each remembering where the entity went."""
    entity = await _entity(session, item.entity_id)
    if not isinstance(entity, Place | Institution):
        raise UnprocessableError("only places and institutions can be merged")
    into = await session.get(type(entity), into_id)
    if into is None:
        raise NotFoundError(f"no {entity.kind} to merge into")
    _close(item, ReviewStatus.MERGED, note)
    spawn = await status_changes.merge_entities(session, entity, into, entered_by=EnteredBy.MANUAL)
    others = await session.scalars(
        select(ReviewItem).where(
            ReviewItem.entity_id == entity.id, ReviewItem.status == ReviewStatus.OPEN
        )
    )
    for other in [item, *others]:
        if other.status is ReviewStatus.OPEN:
            _close(other, ReviewStatus.MERGED, note)
        other.question = {**other.question, "merged_into_id": str(into_id)}
    await session.flush()
    return Decision(item=item, spawn=spawn)


# --- Kinds ---


@dataclass(slots=True)
class Kind:
    """The open items of one kind, as the queue lists them."""

    kind: str
    rule: str
    count: int
    # The facts the items share, reasons aside.
    question: dict[str, Any]
    # The first few entities, to recognise the kind by.
    names: list[str]
    item_ids: list[uuid.UUID]


@dataclass(slots=True)
class KindDecision:
    kind: str
    items: list[ReviewItem]
    spawn: list[Spawn] = field(default_factory=list)


async def open_kinds(session: AsyncSession) -> list[Kind]:
    """Every kind with open items, the largest first."""
    rows = await session.scalars(
        select(ReviewItem)
        .where(ReviewItem.status == ReviewStatus.OPEN, ReviewItem.kind.is_not(None))
        .order_by(ReviewItem.kind, ReviewItem.id)
    )
    kinds: dict[str, Kind] = {}
    for item in rows:
        assert item.kind is not None  # noqa: S101 - filtered by the query
        kind = kinds.get(item.kind)
        if kind is None:
            kind = kinds[item.kind] = Kind(
                kind=item.kind,
                rule=item.rule,
                count=0,
                question={k: v for k, v in item.question.items() if k != "reasons"},
                names=[],
                item_ids=[],
            )
        kind.count += 1
        kind.item_ids.append(item.id)
        if len(kind.names) < SAMPLE_NAMES:
            entity = await _entity(session, item.entity_id)
            kind.names.append(await graph.label_of(session, entity))
    return sorted(kinds.values(), key=lambda kind: (-kind.count, kind.kind))


async def decide_kind(
    session: AsyncSession,
    kind: str,
    *,
    approved: bool,
    note: str | None = None,
    institution_type: str | None = None,
) -> KindDecision:
    """Every open item of `kind` as one decision. Approving a `new_type` kind gives the bodies
    `institution_type`, by default the suggested type as a type name, which must exist."""
    items = list(
        await session.scalars(
            select(ReviewItem)
            .where(ReviewItem.kind == kind, ReviewItem.status == ReviewStatus.OPEN)
            .order_by(ReviewItem.id)
        )
    )
    if not items:
        raise NotFoundError(f"no open review items of kind {kind!r}")
    rule = items[0].rule
    if institution_type is not None and rule != Rule.NEW_TYPE:
        raise UnprocessableError("institution_type is for a new_type kind")
    if approved and rule == Rule.NEW_TYPE and institution_type is None:
        institution_type = type_slug(items[0].question.get("suggested_type", ""))
    decision = KindDecision(kind=kind, items=items)
    for item in items:
        if approved:
            made = await approve(session, item, note=note, institution_type=institution_type)
        else:
            made = await reject(session, item, note=note)
        decision.spawn.extend(made.spawn)
    return decision


async def settle_type_items(session: AsyncSession, country_code: str) -> list[Decision]:
    """After the country's tables changed, approve the open type items they now answer: a
    `type_level` item whose level now expects the type, and a `new_type` item whose suggested
    type the country now uses, which gives the body that type. Called by the countries API."""
    rules = await countries.load_rules(session, country_code)
    # Institutions and places both extend `entities`, so the country is a subquery, not a join.
    in_country = select(Place.id).where(Place.country_code == country_code)
    rows = await session.execute(
        select(ReviewItem, Institution)
        .join(Institution, Institution.id == ReviewItem.entity_id)
        .where(
            ReviewItem.status == ReviewStatus.OPEN,
            ReviewItem.rule.in_([Rule.TYPE_LEVEL, Rule.NEW_TYPE]),
            Institution.place_id.in_(in_country),
        )
        .order_by(ReviewItem.id)
    )
    decisions: list[Decision] = []
    for item, institution in rows.all():
        question = item.question
        if item.rule == Rule.TYPE_LEVEL:
            level, institution_type = question.get("level"), question.get("institution_type")
            if level not in rules.levels:
                continue
            if institution_type not in rules.expected_institution_types(level):
                continue
            note = f"settled: level {level} now expects {institution_type}"
            decisions.append(await approve(session, item, note=note))
        else:
            slug = type_slug(question.get("suggested_type", ""))
            if slug not in rules.uses or institution.institution_type != "other":
                continue
            note = f"settled: {rules.name} now uses {slug}"
            decisions.append(await approve(session, item, note=note, institution_type=slug))
    return decisions


def spawned(decisions: Sequence[Decision]) -> list[Spawn]:
    return [spawn for decision in decisions for spawn in decision.spawn]
