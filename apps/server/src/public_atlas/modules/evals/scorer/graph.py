"""What the scorer reads: one row type per table, loaded in a few queries. Everything after
`load_graph` is pure, so the match rules are tested without a database and a live database and
an eval database are scored the same way."""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.assignments.models import Assignment, AssignmentType
from public_atlas.modules.evals.dataset.schema import OFFICIAL_CODE_SCHEMES
from public_atlas.modules.graph.models import (
    Alias,
    Domain,
    DomainKind,
    EntityStatus,
    Homepage,
    Identifier,
    Institution,
    Place,
    Source,
    Webpage,
)


@dataclass(frozen=True, slots=True)
class PlaceRow:
    id: uuid.UUID
    level: str
    parent_id: uuid.UUID | None
    government_id: uuid.UUID | None
    # The place's code in its country's official scheme (`OFFICIAL_CODE_SCHEMES`), when a list
    # gave it one.
    code: str | None
    status: str
    names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InstitutionRow:
    id: uuid.UUID
    place_id: uuid.UUID
    type: str
    status: str
    # The verified homepage, once one is; the claims are in `Graph.homepages`.
    homepage_url: str | None
    # The body it sits under (spec section 9).
    parent_id: uuid.UUID | None
    names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HomepageRow:
    """One homepage claim of an institution, whatever became of it."""

    institution_id: uuid.UUID
    url: str
    status: str


@dataclass(frozen=True, slots=True)
class SourceRow:
    institution_id: uuid.UUID
    source_type: str
    url: str
    status: str


@dataclass(frozen=True, slots=True)
class DomainRow:
    name: str
    status: str
    # Official, as opposed to a platform: trusted once verified.
    official: bool


@dataclass(frozen=True, slots=True)
class AssignmentRow:
    type: str
    subject_id: uuid.UUID
    status: str
    result: str | None
    summary: str | None
    # The types the agent listed as looked for and not found when it finished.
    types_not_found: tuple[str, ...] = ()


@dataclass(slots=True)
class Graph:
    """One database, as far as the eval dataset can judge it."""

    places: dict[uuid.UUID, PlaceRow] = field(default_factory=dict)
    institutions: dict[uuid.UUID, InstitutionRow] = field(default_factory=dict)
    # Every homepage claimed for an institution, verified or not, oldest first.
    homepages: dict[uuid.UUID, tuple[HomepageRow, ...]] = field(default_factory=dict)
    sources: list[SourceRow] = field(default_factory=list)
    domains: dict[str, DomainRow] = field(default_factory=dict)
    assignments: list[AssignmentRow] = field(default_factory=list)

    def sources_of(self, institution_id: uuid.UUID) -> list[SourceRow]:
        return [s for s in self.sources if s.institution_id == institution_id]

    def claimed_urls(self, institution_id: uuid.UUID) -> tuple[str, ...]:
        return tuple(row.url for row in self.homepages.get(institution_id, ()))

    def summary_of(self, type_: AssignmentType, subject_id: uuid.UUID) -> str | None:
        """The summary of the latest assignment of `type_` on the subject that left one."""
        for row in reversed(self.assignments):
            if row.type == type_ and row.subject_id == subject_id and row.summary:
                return row.summary
        return None

    def not_found_of(self, type_: AssignmentType, subject_id: uuid.UUID) -> frozenset[str]:
        """The types the latest assignment of `type_` on the subject listed as not found."""
        for row in reversed(self.assignments):
            if row.type == type_ and row.subject_id == subject_id and row.types_not_found:
                return frozenset(row.types_not_found)
        return frozenset()


async def load_graph(session: AsyncSession) -> Graph:
    graph = Graph()
    names: dict[uuid.UUID, list[str]] = {}
    for place_id, institution_id, text in (
        await session.execute(
            select(Alias.place_id, Alias.institution_id, Alias.text).order_by(
                Alias.is_acronym, Alias.text
            )
        )
    ).tuples():
        owner = place_id if place_id is not None else institution_id
        if owner is not None:
            names.setdefault(owner, []).append(text)
    codes = dict(
        (
            await session.execute(
                select(Identifier.place_id, Identifier.value).where(
                    Identifier.scheme.in_(list(OFFICIAL_CODE_SCHEMES.values())),
                    Identifier.place_id.is_not(None),
                )
            )
        )
        .tuples()
        .all()
    )
    for place in await session.scalars(select(Place)):
        graph.places[place.id] = PlaceRow(
            id=place.id,
            level=place.administrative_level,
            parent_id=place.parent_place_id,
            government_id=place.government_institution_id,
            code=codes.get(place.id),
            status=str(place.status),
            names=_names(names, place.id, place.name),
        )
    claims: dict[uuid.UUID, list[HomepageRow]] = {}
    verified: dict[uuid.UUID, str] = {}
    rows = await session.execute(
        select(Homepage, Webpage.url)
        .join(Webpage, Webpage.id == Homepage.webpage_id)
        .order_by(Homepage.id)
    )
    for homepage, url in rows.all():
        claims.setdefault(homepage.institution_id, []).append(
            HomepageRow(
                institution_id=homepage.institution_id, url=url, status=str(homepage.status)
            )
        )
        verified[homepage.id] = url
    graph.homepages = {key: tuple(value) for key, value in claims.items()}
    for institution in await session.scalars(select(Institution)):
        graph.institutions[institution.id] = InstitutionRow(
            id=institution.id,
            place_id=institution.place_id,
            type=institution.institution_type,
            status=str(institution.status),
            homepage_url=(
                verified.get(institution.homepage_id)
                if institution.homepage_id is not None
                else None
            ),
            parent_id=institution.parent_institution_id,
            names=_names(names, institution.id, institution.name),
        )
    sources = await session.execute(
        select(Source, Webpage.url).join(Webpage, Webpage.id == Source.webpage_id)
    )
    graph.sources = [
        SourceRow(
            institution_id=source.institution_id,
            source_type=source.source_type,
            url=url,
            status=str(source.status),
        )
        for source, url in sources.all()
    ]
    graph.domains = {
        row.name: DomainRow(
            name=row.name,
            status=str(row.status),
            official=row.domain_kind is DomainKind.OFFICIAL,
        )
        for row in await session.scalars(select(Domain))
    }
    graph.assignments = [
        AssignmentRow(
            type=str(row.type),
            subject_id=row.subject_id,
            status=str(row.status),
            result=str(row.result) if row.result is not None else None,
            summary=row.summary,
            types_not_found=tuple(row.types_not_found or ()),
        )
        for row in await session.scalars(
            select(Assignment).order_by(Assignment.created_at, Assignment.id)
        )
    ]
    return graph


def _names(names: dict[uuid.UUID, list[str]], owner_id: uuid.UUID, name: str) -> tuple[str, ...]:
    """The owner's name first, then its other aliases."""
    return tuple(dict.fromkeys([name, *names.get(owner_id, [])]))


REJECTED = str(EntityStatus.REJECTED)
VERIFIED = str(EntityStatus.VERIFIED)
NEEDS_REVIEW = str(EntityStatus.NEEDS_REVIEW)
