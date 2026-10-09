"""The graph as a picture (docs/graph-view.md): the places under a root, the institutions in
them, their homepages and sources and the domains those sit on, as nodes, and the foreign keys
between them as edges. Reads only, in a handful of queries: one per kind, each selecting from
the one before as a subquery, so a region never costs a round trip per row."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import CTE, ColumnElement, Select, and_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from public_atlas.modules.graph.models import (
    Domain,
    DomainKind,
    Entity,
    EntityKind,
    EntityStatus,
    Homepage,
    Institution,
    InstitutionServedPlace,
    Place,
    Source,
    Webpage,
)
from public_atlas.modules.graph.reading import get_place, population_figure
from public_atlas.modules.graph.schemas import GraphAncestor, GraphEdge, GraphNode, GraphRelation
from public_atlas.shared.exceptions import NotFoundError

__all__ = ["MAX_NODES", "GraphFilters", "Subgraph", "subgraph"]

# Over this many nodes the picture reads as a hairball: the places and their governments come
# back alone, and the user centres the graph lower down to see more.
MAX_NODES = 3000


@dataclass(frozen=True, slots=True)
class GraphFilters:
    """What the picture holds. The root is `place_id` and every place under it; else the
    country's top place, of `country_code` or the first country. `kinds` says which kinds are
    drawn. The other filters keep the matching places and institutions; the root is always
    kept. Without `status`, rejected entities are left out. Platform domains are left out
    unless asked for: one links to hundreds of homepages and pulls the layout toward it."""

    place_id: uuid.UUID | None = None
    country_code: str | None = None
    kinds: frozenset[EntityKind] = frozenset(EntityKind)
    administrative_level: str | None = None
    institution_type: str | None = None
    status: EntityStatus | None = None
    platforms: bool = False
    governments: bool = False


@dataclass(slots=True)
class Subgraph:
    root_id: uuid.UUID
    ancestors: list[GraphAncestor]
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    # Whether the cap cut the picture down to the places and their governments.
    truncated: bool


# Each kind extends `entities`, so a query over two kinds joins the second through a flat alias
# (see reading.py).
_source = aliased(Source, flat=True)
_homepage = aliased(Homepage, flat=True)
_child = aliased(Place, flat=True)
_institution = aliased(Institution, flat=True)


async def subgraph(session: AsyncSession, filters: GraphFilters) -> Subgraph:
    """The nodes and edges the filters admit, the walk cut short at the cap."""
    root = await _root(session, filters)
    ancestors = await _ancestors(session, root)
    tree = _place_tree(root.id)
    places = await _places(session, tree, filters)
    institutions = await _institutions(session, _institutions_in(tree, filters))
    governments = {place.place.government_institution_id for place in places}
    truncated = False
    homepages: list[_WebNode] = []
    sources: list[_WebNode] = []
    domains: list[Domain] = []
    if len(places) + len(institutions) > MAX_NODES:
        truncated = True
    elif filters.kinds & {EntityKind.HOMEPAGE, EntityKind.SOURCE, EntityKind.DOMAIN}:
        ids = [institution.institution.id for institution in institutions]
        homepages, sources = await _web(session, ids, filters)
        if EntityKind.DOMAIN in filters.kinds:
            domains = await _domains(session, homepages, sources, filters)
        if len(places) + len(institutions) + len(homepages) + len(sources) + len(domains) > (
            MAX_NODES
        ):
            truncated = True
    if truncated:
        institutions = [row for row in institutions if row.institution.id in governments]
        homepages, sources, domains = [], [], []
    nodes = _nodes(filters.kinds, places, institutions, homepages, sources, domains)
    served = await _served(session, institutions) if institutions and places else []
    edges = _edges({node.id for node in nodes}, places, institutions, homepages, sources, served)
    return Subgraph(
        root_id=root.id,
        ancestors=[GraphAncestor(id=place.id, label=place.name) for place in ancestors],
        nodes=nodes,
        edges=edges,
        truncated=truncated,
    )


# --- The walk ---


@dataclass(frozen=True, slots=True)
class _PlaceNode:
    place: Place
    population: int | None
    child_count: int
    institution_count: int
    governed: bool
    online: bool


@dataclass(frozen=True, slots=True)
class _InstitutionNode:
    institution: Institution
    source_count: int
    homepage_count: int


@dataclass(frozen=True, slots=True)
class _WebNode:
    """A homepage or a source, with the URL and the domain of its webpage."""

    id: uuid.UUID
    status: EntityStatus
    institution_id: uuid.UUID
    url: str
    domain_id: uuid.UUID | None
    # A source's type; None for a homepage.
    source_type: str | None = None


async def _root(session: AsyncSession, filters: GraphFilters) -> Place:
    if filters.place_id is not None:
        return await get_place(session, filters.place_id)
    query = select(Place).where(Place.parent_place_id.is_(None))
    if filters.country_code is not None:
        query = query.where(Place.country_code == filters.country_code)
    root = await session.scalar(query.order_by(Place.name, Place.id).limit(1))
    if root is None:
        raise NotFoundError("no places yet")
    return root


async def _ancestors(session: AsyncSession, place: Place) -> list[Place]:
    """The places above one, from the top down. A hierarchy is a few levels deep, so this walks
    up a step at a time."""
    chain: list[Place] = []
    parent_id = place.parent_place_id
    while parent_id is not None:
        parent = await session.get(Place, parent_id)
        if parent is None:
            break
        chain.append(parent)
        parent_id = parent.parent_place_id
    chain.reverse()
    return chain


def _place_tree(root_id: uuid.UUID) -> CTE:
    """The root and every place under it, with how far down each is."""
    tree = (
        select(Place.id, literal(0).label("depth"))
        .where(Place.id == root_id)
        .cte("place_tree", recursive=True)
    )
    child = aliased(Place)
    step = select(child.id, (tree.c.depth + 1).label("depth")).where(
        child.parent_place_id == tree.c.id
    )
    return tree.union_all(step)


def _status_clause(entity: type[Entity], status: EntityStatus | None) -> ColumnElement[bool]:
    """The status asked for, or anything but rejected."""
    if status is not None:
        return entity.status == status
    return entity.status != EntityStatus.REJECTED


async def _places(session: AsyncSession, tree: CTE, filters: GraphFilters) -> list[_PlaceNode]:
    """The places of the tree the filters keep, the root among them whatever they say."""
    kept = [_status_clause(Place, filters.status)]
    if filters.administrative_level is not None:
        kept.append(Place.administrative_level == filters.administrative_level)
    child_count = (
        select(func.count())
        .select_from(_child)
        .where(_child.parent_place_id == Place.id, _child.status != EntityStatus.REJECTED)
        .scalar_subquery()
    )
    institution_count = (
        select(func.count())
        .select_from(_institution)
        .where(_institution.place_id == Place.id, _institution.status != EntityStatus.REJECTED)
        .scalar_subquery()
    )
    governed = (
        select(_institution.id)
        .where(
            _institution.id == Place.government_institution_id,
            _institution.status != EntityStatus.REJECTED,
        )
        .exists()
    )
    online = (
        select(_institution.id)
        .where(
            _institution.id == Place.government_institution_id,
            _institution.homepage_id.is_not(None),
        )
        .exists()
    )
    rows = await session.execute(
        select(Place, population_figure(Place.id), child_count, institution_count, governed, online)
        .join(tree, tree.c.id == Place.id)
        .where(or_(tree.c.depth == 0, and_(*kept)))
        .order_by(tree.c.depth, func.lower(Place.name), Place.id)
    )
    return [
        _PlaceNode(
            place=place,
            population=_whole(population),
            child_count=int(children),
            institution_count=int(institutions),
            governed=bool(is_governed),
            online=bool(is_online),
        )
        for place, population, children, institutions, is_governed, is_online in rows.tuples()
    ]


def _institutions_in(tree: CTE, filters: GraphFilters) -> Select[tuple[uuid.UUID]]:
    """The ids of the institutions in the tree's places that the filters keep. The level filter
    is on the institution's own place, as the institutions table reads it."""
    places = select(tree.c.id)
    if filters.administrative_level is not None:
        places = (
            select(Place.id)
            .join(tree, tree.c.id == Place.id)
            .where(Place.administrative_level == filters.administrative_level)
        )
    query = select(Institution.id).where(
        Institution.place_id.in_(places), _status_clause(Institution, filters.status)
    )
    if filters.governments:
        query = query.where(
            Institution.id.in_(
                select(Place.government_institution_id).where(Place.id.in_(select(tree.c.id)))
            )
        )
    if filters.institution_type is not None:
        query = query.where(Institution.institution_type == filters.institution_type)
    return query


async def _institutions(
    session: AsyncSession, ids: Select[tuple[uuid.UUID]]
) -> list[_InstitutionNode]:
    """The institutions with those ids, each with its number of sources and of homepage claims."""
    source_count = (
        select(func.count())
        .select_from(_source)
        .where(_source.institution_id == Institution.id, _source.status != EntityStatus.REJECTED)
        .scalar_subquery()
    )
    homepage_count = (
        select(func.count())
        .select_from(_homepage)
        .where(
            _homepage.institution_id == Institution.id,
            _homepage.status != EntityStatus.REJECTED,
        )
        .scalar_subquery()
    )
    rows = await session.execute(
        select(Institution, source_count, homepage_count)
        .where(Institution.id.in_(ids))
        .order_by(func.lower(Institution.name), Institution.id)
    )
    return [
        _InstitutionNode(
            institution=institution, source_count=int(sources), homepage_count=int(homepages)
        )
        for institution, sources, homepages in rows.tuples()
    ]


async def _web(
    session: AsyncSession, institution_ids: list[uuid.UUID], filters: GraphFilters
) -> tuple[list[_WebNode], list[_WebNode]]:
    """The homepages and the sources of the institutions, each with its URL and domain."""
    homepages: list[_WebNode] = []
    sources: list[_WebNode] = []
    if not institution_ids:
        return homepages, sources
    if filters.kinds & {EntityKind.HOMEPAGE, EntityKind.DOMAIN}:
        rows = await session.execute(
            select(
                Homepage.id,
                Homepage.status,
                Homepage.institution_id,
                Webpage.url,
                Webpage.domain_id,
            )
            .join(Webpage, Webpage.id == Homepage.webpage_id)
            .where(
                Homepage.institution_id.in_(institution_ids),
                _status_clause(Homepage, filters.status),
            )
            .order_by(Webpage.url, Homepage.id)
        )
        homepages = [_WebNode(*row) for row in rows.tuples()]
    if filters.kinds & {EntityKind.SOURCE, EntityKind.DOMAIN}:
        rows = await session.execute(
            select(
                Source.id,
                Source.status,
                Source.institution_id,
                Webpage.url,
                Webpage.domain_id,
                Source.source_type,
            )
            .join(Webpage, Webpage.id == Source.webpage_id)
            .where(
                Source.institution_id.in_(institution_ids), _status_clause(Source, filters.status)
            )
            .order_by(Webpage.url, Source.id)
        )
        sources = [_WebNode(*row) for row in rows.tuples()]
    return homepages, sources


async def _domains(
    session: AsyncSession, homepages: list[_WebNode], sources: list[_WebNode], filters: GraphFilters
) -> list[Domain]:
    ids = {row.domain_id for row in [*homepages, *sources] if row.domain_id is not None}
    if not ids:
        return []
    query = select(Domain).where(Domain.id.in_(ids), _status_clause(Domain, filters.status))
    if not filters.platforms:
        query = query.where(Domain.domain_kind == DomainKind.OFFICIAL)
    return list(await session.scalars(query.order_by(Domain.name)))


async def _served(
    session: AsyncSession, institutions: list[_InstitutionNode]
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Which institutions serve which places, as id pairs."""
    rows = await session.execute(
        select(InstitutionServedPlace.institution_id, InstitutionServedPlace.place_id).where(
            InstitutionServedPlace.institution_id.in_([row.institution.id for row in institutions])
        )
    )
    return list(rows.tuples())


# --- Nodes and edges ---


def _whole(value: Decimal | None) -> int | None:
    return int(value) if value is not None else None


def _nodes(  # noqa: PLR0913, PLR0917 - one argument per kind
    kinds: frozenset[EntityKind],
    places: list[_PlaceNode],
    institutions: list[_InstitutionNode],
    homepages: list[_WebNode],
    sources: list[_WebNode],
    domains: list[Domain],
) -> list[GraphNode]:
    nodes: list[GraphNode] = []
    if EntityKind.PLACE in kinds:
        nodes += [
            GraphNode(
                id=row.place.id,
                kind=EntityKind.PLACE,
                label=row.place.name,
                status=row.place.status,
                population=row.population,
                administrative_level=row.place.administrative_level,
                child_count=row.child_count,
                institution_count=row.institution_count,
                governed=row.governed,
                online=row.online,
            )
            for row in places
        ]
    if EntityKind.INSTITUTION in kinds:
        nodes += [
            GraphNode(
                id=row.institution.id,
                kind=EntityKind.INSTITUTION,
                label=row.institution.name,
                status=row.institution.status,
                source_count=row.source_count,
                institution_type=row.institution.institution_type,
                has_homepage=row.institution.homepage_id is not None,
                homepage_count=row.homepage_count,
            )
            for row in institutions
        ]
    if EntityKind.HOMEPAGE in kinds:
        nodes += [
            GraphNode(id=row.id, kind=EntityKind.HOMEPAGE, label=row.url, status=row.status)
            for row in homepages
        ]
    if EntityKind.SOURCE in kinds:
        nodes += [
            GraphNode(
                id=row.id,
                kind=EntityKind.SOURCE,
                label=row.url,
                status=row.status,
                source_type=row.source_type,
            )
            for row in sources
        ]
    if EntityKind.DOMAIN in kinds:
        nodes += [
            GraphNode(
                id=domain.id,
                kind=EntityKind.DOMAIN,
                label=domain.name,
                status=domain.status,
                domain_kind=domain.domain_kind,
            )
            for domain in domains
        ]
    return nodes


def _edges(  # noqa: PLR0913, PLR0917 - one argument per kind
    drawn: set[uuid.UUID],
    places: list[_PlaceNode],
    institutions: list[_InstitutionNode],
    homepages: list[_WebNode],
    sources: list[_WebNode],
    served: Iterable[tuple[uuid.UUID, uuid.UUID]],
) -> list[GraphEdge]:
    """Every foreign key between two drawn nodes, once. A government's link to its place is the
    place's `government` edge; the institution's own `place` edge would double it."""
    governments = {row.place.government_institution_id for row in places}
    candidates: list[tuple[uuid.UUID, uuid.UUID | None, GraphRelation]] = []
    for row in places:
        candidates.append((row.place.id, row.place.parent_place_id, "parent"))
        candidates.append((row.place.id, row.place.government_institution_id, "government"))
    for row in institutions:
        institution = row.institution
        if institution.id not in governments:
            candidates.append((institution.id, institution.place_id, "place"))
        candidates.append((institution.id, institution.parent_institution_id, "parent"))
    for row in homepages:
        candidates.append((row.id, row.institution_id, "homepage"))
        candidates.append((row.id, row.domain_id, "domain"))
    for row in sources:
        candidates.append((row.id, row.institution_id, "source"))
        candidates.append((row.id, row.domain_id, "domain"))
    candidates += [(institution_id, place_id, "serves") for institution_id, place_id in served]
    edges: list[GraphEdge] = []
    seen: set[tuple[uuid.UUID, uuid.UUID, GraphRelation]] = set()
    for source, target, relation in candidates:
        if target is None or source not in drawn or target not in drawn:
            continue
        if (source, target, relation) in seen:
            continue
        seen.add((source, target, relation))
        edges.append(GraphEdge(source=source, target=target, relation=relation))
    return edges
