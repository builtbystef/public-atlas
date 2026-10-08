"""The graph as the console reads it (spec section 11, page 3): a page of institutions with
search and filters, one institution with everything attached to it, and the places a filter or
a picker needs. Reads only; the writes are in `service.py` and `status_changes.py`."""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, ScalarSelect, Select, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, aliased

from public_atlas.modules.graph.models import (
    Alias,
    Domain,
    EntityStatus,
    Homepage,
    Identifier,
    Institution,
    InstitutionServedPlace,
    Metric,
    MetricName,
    Place,
    Source,
    Webpage,
)
from public_atlas.modules.graph.schemas import InstitutionSort, PlaceSort, SortOrder
from public_atlas.shared.exceptions import NotFoundError

__all__ = [
    "HomepageRow",
    "InstitutionFilters",
    "InstitutionRow",
    "PlaceFilters",
    "PlaceRow",
    "count_institutions",
    "descendant_place_ids",
    "get_place",
    "homepage_rows",
    "identifiers_of",
    "institution_children",
    "list_institutions",
    "list_places",
    "metrics_of",
    "place_parents",
    "place_population",
    "served_places_of",
    "source_rows",
    "subject_of",
]


@dataclass(frozen=True, slots=True)
class InstitutionFilters:
    """What the table narrows by. `q` matches a name or an alias, case-folded, anywhere in the
    text. `place_id` admits the place and every place under it. The population bounds are on
    the institution's own place, inclusive, and leave out a place with no figure."""

    q: str | None = None
    country_code: str | None = None
    place_id: uuid.UUID | None = None
    administrative_level: str | None = None
    institution_type: str | None = None
    status: EntityStatus | None = None
    parent_institution_id: uuid.UUID | None = None
    min_population: int | None = None
    max_population: int | None = None


@dataclass(frozen=True, slots=True)
class InstitutionRow:
    institution: Institution
    place: Place
    homepage_url: str | None
    # The newest population figure of its place.
    place_population: int | None


def descendant_place_ids(place_id: uuid.UUID) -> Select[tuple[uuid.UUID]]:
    """The place and every place under it, as a subquery."""
    tree = select(Place.id).where(Place.id == place_id).cte("place_tree", recursive=True)
    child = aliased(Place)
    tree = tree.union_all(select(child.id).where(child.parent_place_id == tree.c.id))
    return select(tree.c.id)


def _population(
    place_id: ColumnElement[uuid.UUID] | InstrumentedAttribute[uuid.UUID] | uuid.UUID,
) -> ScalarSelect[Decimal]:
    """The newest population figure of the place, as a correlated subquery; null without one."""
    return (
        select(Metric.value)
        .where(Metric.place_id == place_id, Metric.name == MetricName.POPULATION)
        .order_by(Metric.year.desc())
        .limit(1)
        .scalar_subquery()
    )


def _within(
    population: ScalarSelect[Decimal], min_population: int | None, max_population: int | None
) -> list[ColumnElement[bool]]:
    bounds: list[ColumnElement[bool]] = []
    if min_population is not None:
        bounds.append(population >= min_population)
    if max_population is not None:
        bounds.append(population <= max_population)
    return bounds


def _whole(value: Decimal | None) -> int | None:
    return int(value) if value is not None else None


# Every entity extends `entities`, so a plain join of two kinds overlaps on it; a flat alias of
# the joined side keeps the join to its child table.
_place = aliased(Place, flat=True)
_homepage = aliased(Homepage, flat=True)
_domain = aliased(Domain, flat=True)


def _institutions_matching(filters: InstitutionFilters) -> Select[tuple[Institution, Place]]:
    query = select(Institution, _place).join(_place, _place.id == Institution.place_id)
    if filters.q:
        pattern = f"%{' '.join(filters.q.split())}%"
        named = exists().where(Alias.institution_id == Institution.id, Alias.text.ilike(pattern))
        query = query.where(Institution.name.ilike(pattern) | named)
    if filters.country_code is not None:
        query = query.where(_place.country_code == filters.country_code)
    if filters.place_id is not None:
        query = query.where(Institution.place_id.in_(descendant_place_ids(filters.place_id)))
    if filters.administrative_level is not None:
        query = query.where(_place.administrative_level == filters.administrative_level)
    if filters.institution_type is not None:
        query = query.where(Institution.institution_type == filters.institution_type)
    if filters.status is not None:
        query = query.where(Institution.status == filters.status)
    if filters.parent_institution_id is not None:
        query = query.where(Institution.parent_institution_id == filters.parent_institution_id)
    bounds = _within(_population(_place.id), filters.min_population, filters.max_population)
    return query.where(*bounds) if bounds else query


def _ordering(sort: InstitutionSort, order: SortOrder) -> list[ColumnElement[Any]]:
    """The columns a sort reads, each in `order`, with the id last so a page is stable."""
    columns: list[ColumnElement[Any] | InstrumentedAttribute[Any]]
    match sort:
        case "name":
            columns = [func.lower(Institution.name)]
        case "institution_type":
            columns = [Institution.institution_type, func.lower(Institution.name)]
        case "status":
            columns = [Institution.status, func.lower(Institution.name)]
        case "created_at":
            columns = [Institution.created_at]
        case "place":
            columns = [func.lower(_place.name), func.lower(Institution.name)]
        case "population":
            # A place with no figure comes last either way.
            figure = _population(_place.id)
            first = figure.desc() if order == "desc" else figure.asc()
            rest = _directed([func.lower(Institution.name), Institution.id], order)
            return [first.nulls_last(), *rest]
    columns.append(Institution.id)
    return _directed(columns, order)


def _directed(
    columns: list[ColumnElement[Any] | InstrumentedAttribute[Any]], order: SortOrder
) -> list[ColumnElement[Any]]:
    return [column.desc() if order == "desc" else column.asc() for column in columns]


async def list_institutions(  # noqa: PLR0913
    session: AsyncSession,
    filters: InstitutionFilters,
    *,
    sort: InstitutionSort = "name",
    order: SortOrder = "asc",
    limit: int = 50,
    offset: int = 0,
) -> list[InstitutionRow]:
    """A page of institutions with their places and the URL of their verified homepage."""
    rows = await session.execute(
        _institutions_matching(filters)
        .outerjoin(_homepage, _homepage.id == Institution.homepage_id)
        .outerjoin(Webpage, Webpage.id == _homepage.webpage_id)
        .add_columns(Webpage.url, _population(_place.id))
        .order_by(*_ordering(sort, order))
        .limit(limit)
        .offset(offset)
    )
    return [
        InstitutionRow(
            institution=institution,
            place=place,
            homepage_url=url,
            place_population=_whole(population),
        )
        for institution, place, url, population in rows.tuples()
    ]


async def count_institutions(session: AsyncSession, filters: InstitutionFilters) -> int:
    total = await session.scalar(
        select(func.count()).select_from(_institutions_matching(filters).subquery())
    )
    return int(total or 0)


async def institution_children(
    session: AsyncSession, institution: Institution
) -> list[Institution]:
    """The bodies that sit under the institution, rejected ones aside."""
    rows = await session.scalars(
        select(Institution)
        .where(
            Institution.parent_institution_id == institution.id,
            Institution.status != EntityStatus.REJECTED,
        )
        .order_by(func.lower(Institution.name))
    )
    return list(rows)


async def served_places_of(session: AsyncSession, institution: Institution) -> list[Place]:
    rows = await session.scalars(
        select(Place)
        .join(InstitutionServedPlace, InstitutionServedPlace.place_id == Place.id)
        .where(InstitutionServedPlace.institution_id == institution.id)
        .order_by(func.lower(Place.name))
    )
    return list(rows)


async def identifiers_of(session: AsyncSession, institution: Institution) -> list[Identifier]:
    rows = await session.scalars(
        select(Identifier)
        .where(Identifier.institution_id == institution.id)
        .order_by(Identifier.scheme)
    )
    return list(rows)


async def metrics_of(session: AsyncSession, institution: Institution) -> list[Metric]:
    rows = await session.scalars(
        select(Metric)
        .where(Metric.institution_id == institution.id)
        .order_by(Metric.name, Metric.year.desc())
    )
    return list(rows)


@dataclass(frozen=True, slots=True)
class HomepageRow:
    homepage: Homepage
    url: str
    found_on_url: str | None
    domain: Domain | None


async def homepage_rows(session: AsyncSession, institution: Institution) -> list[HomepageRow]:
    """Every homepage claim of the institution with its URL, the page that linked to it and
    its domain, oldest first."""
    found_on = aliased(Webpage)
    rows = await session.execute(
        select(Homepage, Webpage.url, found_on.url, _domain)
        .join(Webpage, Webpage.id == Homepage.webpage_id)
        .outerjoin(found_on, found_on.id == Homepage.found_on_webpage_id)
        .outerjoin(_domain, _domain.id == Webpage.domain_id)
        .where(Homepage.institution_id == institution.id)
        .order_by(Homepage.id)
    )
    return [
        HomepageRow(homepage=homepage, url=url, found_on_url=linked_from, domain=domain)
        for homepage, url, linked_from, domain in rows.tuples()
    ]


async def source_rows(session: AsyncSession, institution: Institution) -> list[tuple[Source, str]]:
    """The institution's sources with their URLs, by type then URL."""
    rows = await session.execute(
        select(Source, Webpage.url)
        .join(Webpage, Webpage.id == Source.webpage_id)
        .where(Source.institution_id == institution.id)
        .order_by(Source.source_type, Webpage.url)
    )
    return list(rows.tuples())


# --- Places ---


@dataclass(frozen=True, slots=True)
class PlaceFilters:
    """What a list of places narrows by. `q` matches a name or an alias; `parent_place_id`
    admits the places directly under it. The population bounds are inclusive and leave out a
    place with no figure."""

    q: str | None = None
    country_code: str | None = None
    administrative_level: str | None = None
    parent_place_id: uuid.UUID | None = None
    min_population: int | None = None
    max_population: int | None = None


@dataclass(frozen=True, slots=True)
class PlaceRow:
    place: Place
    # The newest population figure.
    population: int | None


async def list_places(  # noqa: PLR0913
    session: AsyncSession,
    filters: PlaceFilters,
    *,
    sort: PlaceSort = "name",
    order: SortOrder = "asc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[PlaceRow], int]:
    """A page of places with their population, and how many match. Rejected places are left
    out."""
    query = _places_matching(filters)
    figure = _population(Place.id)
    rows = await session.execute(
        query.add_columns(figure)
        .order_by(*_place_ordering(figure, sort, order))
        .limit(limit)
        .offset(offset)
    )
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    places = [
        PlaceRow(place=place, population=_whole(population)) for place, population in rows.tuples()
    ]
    return places, int(total or 0)


def _place_ordering(
    figure: ScalarSelect[Decimal], sort: PlaceSort, order: SortOrder
) -> list[ColumnElement[Any]]:
    """The columns a sort reads, with the id last so a page is stable."""
    name = [func.lower(Place.name), Place.id]
    match sort:
        case "name":
            return _directed(name, order)
        case "administrative_level":
            return _directed([Place.administrative_level, *name], order)
        case "population":
            # A place with no figure comes last either way.
            first = figure.desc() if order == "desc" else figure.asc()
            return [first.nulls_last(), *_directed(name, order)]


def _places_matching(filters: PlaceFilters) -> Select[tuple[Place]]:
    query = select(Place).where(Place.status != EntityStatus.REJECTED)
    if filters.q:
        pattern = f"%{' '.join(filters.q.split())}%"
        named = exists().where(Alias.place_id == Place.id, Alias.text.ilike(pattern))
        query = query.where(Place.name.ilike(pattern) | named)
    if filters.country_code is not None:
        query = query.where(Place.country_code == filters.country_code)
    if filters.administrative_level is not None:
        query = query.where(Place.administrative_level == filters.administrative_level)
    if filters.parent_place_id is not None:
        query = query.where(Place.parent_place_id == filters.parent_place_id)
    bounds = _within(_population(Place.id), filters.min_population, filters.max_population)
    return query.where(*bounds) if bounds else query


async def get_place(session: AsyncSession, place_id: uuid.UUID) -> Place:
    place = await session.get(Place, place_id)
    if place is None:
        raise NotFoundError("no such place")
    return place


async def place_population(session: AsyncSession, place_id: uuid.UUID) -> int | None:
    """The place's newest population figure, if it has one."""
    return _whole(await session.scalar(select(_population(place_id))))


async def place_parents(session: AsyncSession, place: Place) -> list[Place]:
    """The places above `place`, nearest first."""
    parents: list[Place] = []
    seen = {place.id}
    current = place
    while current.parent_place_id is not None and current.parent_place_id not in seen:
        current = await session.get_one(Place, current.parent_place_id)
        seen.add(current.id)
        parents.append(current)
    return parents


async def subject_of(session: AsyncSession, subject_id: uuid.UUID) -> Place | Institution | None:
    """The place or institution with this id, if either."""
    place = await session.get(Place, subject_id)
    if place is not None:
        return place
    return await session.get(Institution, subject_id)
