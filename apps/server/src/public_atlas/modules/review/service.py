"""The review queue (spec section 6.5): raising a question about one entity, and the decisions
a reviewer makes. Raising an item sets the entity to `needs_review`; approving, rejecting and
merging run the same `status_changes` functions the rules run, so nothing bypasses them. Items
that ask one shared question carry a `kind`: the queue lists them as one row and they are decided
together; the type questions among them settle themselves when the country tables come to answer
them.

The question is a JSON document the reviewer sees: `reasons`, one per time the rule fired, and
the facts the rule wants decided (`institution_type` and `level`, `suggested_type`, the
`homepage_id` a domain decision is about, the `duplicate_of` ids a save was unsure between).
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ColumnElement, FromClause, Select, Text, Uuid, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.db.base import utcnow
from public_atlas.modules.assignments.service import Spawn
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.models import InstitutionType
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
from public_atlas.modules.graph.schemas import SortOrder
from public_atlas.modules.review.models import ReviewItem, ReviewStatus
from public_atlas.modules.review.schemas import Affects, RowSort
from public_atlas.shared.exceptions import ConflictError, NotFoundError, UnprocessableError

__all__ = [
    "Decision",
    "KindDecision",
    "Member",
    "Row",
    "RowFilters",
    "Rule",
    "approve",
    "country_of",
    "decide_kind",
    "kind_of",
    "list_rows",
    "merge",
    "raise_review",
    "raised_at",
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


# The items a row carries, enough to recognise it by; it counts every one.
MEMBERS_SHOWN = 50
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


@dataclass(frozen=True, slots=True)
class RowFilters:
    """What the queue narrows by, item by item; a row keeps the items that match. `q` matches
    the entity's name or URL, or the question's text, case-folded, anywhere in it. `kind` keeps
    the items of one shared question. `affects` keeps the rows of one item or of several."""

    status: ReviewStatus | None = ReviewStatus.OPEN
    q: str | None = None
    rule: str | None = None
    kind: str | None = None
    entity_kind: EntityKind | None = None
    country_code: str | None = None
    affects: Affects | None = None


@dataclass(frozen=True, slots=True)
class Member:
    """An item of a row, with what to recognise its entity by."""

    item: ReviewItem
    entity_kind: EntityKind
    label: str
    country_code: str | None


@dataclass(slots=True)
class Row:
    """A line of the queue: an item on its own, or every item of one kind and status, which
    are decided together."""

    kind: str | None
    rule: str
    status: ReviewStatus
    # The first few items, oldest first, to recognise the row by.
    members: list[Member]
    # Every item of the row.
    item_ids: list[uuid.UUID]
    # The facts every item of the row has, reasons aside.
    question: dict[str, Any]
    decided_at: datetime | None

    @property
    def count(self) -> int:
        return len(self.item_ids)


def raised_at(item_id: uuid.UUID) -> datetime:
    """When the item was raised: its id is a UUIDv7, which starts with the time it was made."""
    return datetime.fromtimestamp(item_id.time / 1000, UTC)


# One row per kind, and each item without one a row of its own.
_row_key = func.coalesce(ReviewItem.kind, cast(ReviewItem.id, Text))


@dataclass(frozen=True, slots=True)
class _Facts:
    """The item's entity as SQL: its kind, `graph.label_of`, and `country_of`."""

    joined: FromClause
    entity_kind: ColumnElement[EntityKind]
    label: ColumnElement[str]
    country_code: ColumnElement[str | None]


def _facts() -> _Facts:
    entity = Entity.__table__
    place = Place.__table__.alias("place")
    institution = Institution.__table__.alias("institution")
    domain = Domain.__table__.alias("domain")
    homepage = Homepage.__table__.alias("homepage")
    source = Source.__table__.alias("source")
    homepage_page = Webpage.__table__.alias("homepage_page")
    source_page = Webpage.__table__.alias("source_page")
    # The homepage claim a domain's question names.
    claim = Homepage.__table__.alias("claim")
    owner = Institution.__table__.alias("owner")
    owner_place = Place.__table__.alias("owner_place")
    owner_id = func.coalesce(
        institution.c.id,
        homepage.c.institution_id,
        source.c.institution_id,
        claim.c.institution_id,
    )
    joined = (
        ReviewItem.__table__.join(entity, entity.c.id == ReviewItem.entity_id)
        .outerjoin(place, place.c.id == ReviewItem.entity_id)
        .outerjoin(institution, institution.c.id == ReviewItem.entity_id)
        .outerjoin(domain, domain.c.id == ReviewItem.entity_id)
        .outerjoin(homepage, homepage.c.id == ReviewItem.entity_id)
        .outerjoin(source, source.c.id == ReviewItem.entity_id)
        .outerjoin(homepage_page, homepage_page.c.id == homepage.c.webpage_id)
        .outerjoin(source_page, source_page.c.id == source.c.webpage_id)
        .outerjoin(
            claim,
            domain.c.id.is_not(None)
            & (claim.c.id == cast(ReviewItem.question["homepage_id"].astext, Uuid)),
        )
        .outerjoin(owner, owner.c.id == owner_id)
        .outerjoin(owner_place, owner_place.c.id == owner.c.place_id)
    )
    return _Facts(
        joined=joined,
        entity_kind=entity.c.kind,
        label=func.coalesce(
            place.c.name,
            institution.c.name,
            domain.c.name,
            homepage_page.c.url,
            source.c.source_type + " " + source_page.c.url,
        ),
        country_code=func.coalesce(place.c.country_code, owner_place.c.country_code),
    )


def _matching[T: tuple[Any, ...]](
    query: Select[T], facts: _Facts, filters: RowFilters
) -> Select[T]:
    query = query.select_from(facts.joined)
    if filters.status is not None:
        query = query.where(ReviewItem.status == filters.status)
    if filters.q:
        pattern = f"%{' '.join(filters.q.split())}%"
        query = query.where(
            facts.label.ilike(pattern) | cast(ReviewItem.question, Text).ilike(pattern)
        )
    if filters.rule is not None:
        query = query.where(ReviewItem.rule == filters.rule)
    if filters.kind is not None:
        query = query.where(ReviewItem.kind == filters.kind)
    if filters.entity_kind is not None:
        query = query.where(facts.entity_kind == filters.entity_kind)
    if filters.country_code is not None:
        query = query.where(facts.country_code == filters.country_code)
    return query


def _shared(questions: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The facts every question has with the same value, reasons aside."""
    first, *others = questions
    return {
        key: value
        for key, value in first.items()
        if key != "reasons" and all(other.get(key) == value for other in others)
    }


async def list_rows(  # noqa: PLR0913
    session: AsyncSession,
    filters: RowFilters,
    *,
    sort: RowSort = "count",
    order: SortOrder = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Row], int]:
    """A page of the queue and how many rows match. The items of one kind and status are one
    row; the rest are a row each. A row counts the items that match, so a filter narrows a kind
    to the items it admits. Rows of equal sort value come newest first."""
    facts = _facts()
    matching = _matching(
        select(ReviewItem.id, _row_key.label("key"), ReviewItem.rule, ReviewItem.status),
        facts,
        filters,
    ).subquery("matching")
    count = func.count().label("count")
    # PostgreSQL has no `min` of a uuid; the text of a UUIDv7 sorts as its time does.
    first = func.min(cast(matching.c.id, Text)).label("first")
    grouping = (matching.c.key, matching.c.rule, matching.c.status)
    groups = select(*grouping, count, first).group_by(*grouping)
    match filters.affects:
        case "one":
            groups = groups.having(func.count() == 1)
        case "several":
            groups = groups.having(func.count() > 1)
        case None:
            pass
    total = await session.scalar(select(func.count()).select_from(groups.subquery()))
    by = {"count": count, "raised_at": first}[sort]
    page = (
        await session.execute(
            groups.order_by(by.desc() if order == "desc" else by.asc(), first.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    if not page:
        return [], int(total or 0)

    found = await session.execute(
        _matching(
            select(ReviewItem, facts.entity_kind, facts.label, facts.country_code, _row_key).where(
                _row_key.in_({row.key for row in page})
            ),
            facts,
            filters,
        ).order_by(ReviewItem.id)
    )
    members: dict[tuple[str, str, ReviewStatus], list[Member]] = {}
    for item, entity_kind, label, country_code, key in found:
        members.setdefault((key, item.rule, item.status), []).append(
            Member(item=item, entity_kind=entity_kind, label=label, country_code=country_code)
        )
    rows = []
    for row in page:
        items = members[row.key, row.rule, row.status]
        decided = [member.item.decided_at for member in items if member.item.decided_at]
        rows.append(
            Row(
                kind=items[0].item.kind,
                rule=row.rule,
                status=row.status,
                members=items[:MEMBERS_SHOWN],
                item_ids=[member.item.id for member in items],
                question=_shared([member.item.question for member in items]),
                decided_at=max(decided, default=None),
            )
        )
    return rows, int(total or 0)


async def get_item(session: AsyncSession, item_id: uuid.UUID) -> ReviewItem:
    item = await session.get(ReviewItem, item_id)
    if item is None:
        raise NotFoundError("no such review item")
    return item


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
class KindDecision:
    kind: str
    items: list[ReviewItem]
    spawn: list[Spawn] = field(default_factory=list)


async def decide_kind(  # noqa: PLR0913
    session: AsyncSession,
    kind: str,
    *,
    approved: bool,
    note: str | None = None,
    institution_type: str | None = None,
    item_ids: Sequence[uuid.UUID] | None = None,
) -> KindDecision:
    """Every open item of `kind` as one decision, or with `item_ids` those items, each of which
    must be an open item of the kind: the reviewer decides what the queue showed them. Approving
    a `new_type` kind gives the bodies `institution_type`, by default the suggested type as a
    type name, which must exist."""
    query = select(ReviewItem).where(
        ReviewItem.kind == kind, ReviewItem.status == ReviewStatus.OPEN
    )
    if item_ids is not None:
        query = query.where(ReviewItem.id.in_(item_ids))
    items = list(await session.scalars(query.order_by(ReviewItem.id)))
    if item_ids is not None and len(items) != len(set(item_ids)):
        raise ConflictError("some of the items are decided already or ask another question")
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
