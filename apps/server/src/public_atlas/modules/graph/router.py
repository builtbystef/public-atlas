"""The graph API (spec section 11, page 3): institutions as a table with search and filters,
one institution with its aliases, parent, homepage, sources by type and every quote linked to
its stored copy; and the places a filter or a picker needs. Reads only: the graph is written by
the loader, the agent's findings and the reviewer's decisions."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from public_atlas.dependencies import ObjectStoreDep, SessionDep, SettingsDep
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.graph import service
from public_atlas.modules.graph.models import EntityStatus, Institution, Place
from public_atlas.modules.graph.schemas import (
    AliasOutput,
    EvidenceOutput,
    HomepageOutput,
    IdentifierOutput,
    InstitutionDetail,
    InstitutionOutput,
    InstitutionRef,
    InstitutionSort,
    MetricOutput,
    PlaceDetail,
    PlaceOutput,
    PlaceRef,
    PlaceSort,
    SortOrder,
    SourceOutput,
)
from public_atlas.shared.exceptions import NotFoundError
from public_atlas.shared.pagination import Page

router = APIRouter(tags=["graph"])


def _place_ref(place: Place) -> PlaceRef:
    return PlaceRef(id=place.id, name=place.name, administrative_level=place.administrative_level)


def _institution_ref(institution: Institution) -> InstitutionRef:
    return InstitutionRef(
        id=institution.id,
        name=institution.name,
        institution_type=institution.institution_type,
        status=institution.status,
    )


def _place_output(place: Place, population: int | None) -> PlaceOutput:
    return PlaceOutput(
        id=place.id,
        name=place.name,
        country_code=place.country_code,
        administrative_level=place.administrative_level,
        parent_place_id=place.parent_place_id,
        government_institution_id=place.government_institution_id,
        status=place.status,
        entered_by=place.entered_by,
        created_at=place.created_at,
        population=population,
    )


def _output(row: service.InstitutionRow) -> InstitutionOutput:
    institution = row.institution
    return InstitutionOutput(
        id=institution.id,
        name=institution.name,
        institution_type=institution.institution_type,
        suggested_type=institution.suggested_type,
        status=institution.status,
        entered_by=institution.entered_by,
        place=_place_ref(row.place),
        place_population=row.place_population,
        parent_institution_id=institution.parent_institution_id,
        procurement_handled_by=institution.procurement_handled_by,
        homepage_id=institution.homepage_id,
        homepage_url=row.homepage_url,
        created_at=institution.created_at,
    )


@router.get("/institutions")
async def list_institutions(  # noqa: PLR0913, PLR0917 - one argument per filter
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    country_code: Annotated[str | None, Query(pattern=r"^[A-Z]{2}$")] = None,
    place_id: Annotated[uuid.UUID | None, Query()] = None,
    administrative_level: Annotated[str | None, Query(max_length=64)] = None,
    institution_type: Annotated[str | None, Query(max_length=64)] = None,
    status: Annotated[EntityStatus | None, Query()] = None,
    parent_institution_id: Annotated[uuid.UUID | None, Query()] = None,
    min_population: Annotated[int | None, Query(ge=0)] = None,
    max_population: Annotated[int | None, Query(ge=0)] = None,
    sort: InstitutionSort = "name",
    order: SortOrder = "asc",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[InstitutionOutput]:
    """A page of institutions. `q` matches a name or an alias; `place_id` admits the place and
    every place under it; the population bounds are on the institution's own place."""
    filters = service.InstitutionFilters(
        q=q,
        country_code=country_code,
        place_id=place_id,
        administrative_level=administrative_level,
        institution_type=institution_type,
        status=status,
        parent_institution_id=parent_institution_id,
        min_population=min_population,
        max_population=max_population,
    )
    rows = await service.list_institutions(
        session, filters, sort=sort, order=order, limit=limit, offset=offset
    )
    return Page(
        items=[_output(row) for row in rows],
        total=await service.count_institutions(session, filters),
        limit=limit,
        offset=offset,
    )


@router.get("/institutions/{institution_id}")
async def read_institution(
    institution_id: uuid.UUID, session: SessionDep, store: ObjectStoreDep, settings: SettingsDep
) -> InstitutionDetail:
    """The institution with its aliases, its place and the places above, its parent and the
    bodies under it, every homepage claim, its sources, and every quote for any of them with a
    link to the stored copy it was found on."""
    institution = await session.get(Institution, institution_id)
    if institution is None:
        raise NotFoundError("no such institution")
    place = await session.get_one(Place, institution.place_id)
    parent = (
        await session.get(Institution, institution.parent_institution_id)
        if institution.parent_institution_id is not None
        else None
    )
    homepages = await service.homepage_rows(session, institution)
    sources = await service.source_rows(session, institution)
    verified = next((row for row in homepages if row.homepage.id == institution.homepage_id), None)
    base = _output(
        service.InstitutionRow(
            institution=institution,
            place=place,
            homepage_url=verified.url if verified is not None else None,
            place_population=await service.place_population(session, place.id),
        )
    )
    quoted = [institution.id, *(row.homepage.id for row in homepages), *(s.id for s, _ in sources)]
    details = await evidence.evidence_details(
        session, store, quoted, url_ttl=settings.storage_url_ttl
    )
    return InstitutionDetail(
        **base.model_dump(),
        aliases=[
            AliasOutput(
                text=alias.text,
                language=alias.language,
                is_acronym=alias.is_acronym,
                entered_by=alias.entered_by,
            )
            for alias in await service.names_of(session, institution)
        ],
        identifiers=[
            IdentifierOutput(scheme=row.scheme.value, value=row.value)
            for row in await service.identifiers_of(session, institution)
        ],
        metrics=[
            MetricOutput(name=row.name.value, year=row.year, value=row.value)
            for row in await service.metrics_of(session, institution)
        ],
        places=[_place_ref(row) for row in await service.place_chain(session, place)],
        parent=_institution_ref(parent) if parent is not None else None,
        children=[
            _institution_ref(child)
            for child in await service.institution_children(session, institution)
        ],
        served_places=[
            _place_ref(row) for row in await service.served_places_of(session, institution)
        ],
        homepages=[
            HomepageOutput(
                id=row.homepage.id,
                url=row.url,
                status=row.homepage.status,
                entered_by=row.homepage.entered_by,
                found_on_url=row.found_on_url,
                rejected_reason=row.homepage.rejected_reason,
                trusted_path=row.homepage.trusted_path,
                domain=row.domain.name if row.domain is not None else None,
                domain_status=row.domain.status if row.domain is not None else None,
                created_at=row.homepage.created_at,
            )
            for row in homepages
        ],
        sources=[
            SourceOutput(
                id=source.id,
                url=url,
                source_type=source.source_type,
                access=source.access,
                status=source.status,
                entered_by=source.entered_by,
                created_at=source.created_at,
            )
            for source, url in sources
        ],
        evidence=[EvidenceOutput.model_validate(row, from_attributes=True) for row in details],
    )


@router.get("/places")
async def list_places(  # noqa: PLR0913, PLR0917 - one argument per filter
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    country_code: Annotated[str | None, Query(pattern=r"^[A-Z]{2}$")] = None,
    administrative_level: Annotated[str | None, Query(max_length=64)] = None,
    parent_place_id: Annotated[uuid.UUID | None, Query()] = None,
    min_population: Annotated[int | None, Query(ge=0)] = None,
    max_population: Annotated[int | None, Query(ge=0)] = None,
    sort: PlaceSort = "name",
    order: SortOrder = "asc",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[PlaceOutput]:
    """A page of places, by name unless sorted otherwise, each with its newest population
    figure; `q` matches a name or an alias."""
    filters = service.PlaceFilters(
        q=q,
        country_code=country_code,
        administrative_level=administrative_level,
        parent_place_id=parent_place_id,
        min_population=min_population,
        max_population=max_population,
    )
    rows, total = await service.list_places(
        session, filters, sort=sort, order=order, limit=limit, offset=offset
    )
    return Page(
        items=[_place_output(row.place, row.population) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/places/{place_id}")
async def read_place(place_id: uuid.UUID, session: SessionDep) -> PlaceDetail:
    """The place with its population, the places above it and its government."""
    place = await service.get_place(session, place_id)
    government = (
        await session.get(Institution, place.government_institution_id)
        if place.government_institution_id is not None
        else None
    )
    return PlaceDetail(
        **_place_output(place, await service.place_population(session, place.id)).model_dump(),
        parents=[_place_ref(row) for row in await service.place_parents(session, place)],
        government=_institution_ref(government) if government is not None else None,
    )
