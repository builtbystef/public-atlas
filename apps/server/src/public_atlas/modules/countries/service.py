"""Seeding a country (spec section 5.1): the global types, the country's five tables, its
platforms and its anchors, from a seed module. Adds what is missing and never deletes or
rewrites, so an edit made in the console survives a reseed."""

from dataclasses import dataclass, fields
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.countries.models import (
    AdministrativeLevel,
    CountryInstitutionType,
    CountrySettings,
    InstitutionType,
    SourceType,
)
from public_atlas.modules.countries.schemas import CountrySeed, PlaceSeed, SharedSeed
from public_atlas.modules.countries.seeds import shared as shared_seed
from public_atlas.modules.graph.models import (
    Alias,
    Domain,
    DomainKind,
    EnteredBy,
    EntityStatus,
    Institution,
    Place,
    ProcurementHandledBy,
)


@dataclass
class SeedReport:
    """Rows added per table."""

    institution_types: int = 0
    source_types: int = 0
    country_settings: int = 0
    administrative_levels: int = 0
    country_institution_types: int = 0
    domains: int = 0
    places: int = 0
    institutions: int = 0
    aliases: int = 0

    @property
    def added(self) -> int:
        return sum(getattr(self, item.name) for item in fields(self))


def validate(country: dict[str, Any]) -> tuple[SharedSeed, CountrySeed]:
    """The seeds as the API's models read them, checked against each other."""
    shared = SharedSeed.model_validate(shared_seed.SEED)
    seed = CountrySeed.model_validate(country)
    seed.check_against(shared)
    return shared, seed


async def seed(session: AsyncSession, country: dict[str, Any]) -> SeedReport:
    """Write what `country` seeds and the database lacks. The caller commits."""
    shared, seed = validate(country)
    report = SeedReport()
    await _seed_types(session, shared, report)
    await _seed_country_tables(session, seed, report)
    for name in seed.platforms:
        if await _add_domain(session, name, DomainKind.PLATFORM):
            report.domains += 1
    seeded: dict[str, Place] = {}
    for place_seed in seed.places:
        parent = seeded[place_seed.parent] if place_seed.parent is not None else None
        seeded[place_seed.name] = await _seed_place(
            session, seed.settings.country_code, place_seed, parent, report
        )
    await session.flush()
    return report


async def _seed_types(session: AsyncSession, shared: SharedSeed, report: SeedReport) -> None:
    for institution_type in shared.institution_types:
        if await session.get(InstitutionType, institution_type.name) is None:
            session.add(InstitutionType(**institution_type.model_dump()))
            report.institution_types += 1
    for source_type in shared.source_types:
        if await session.get(SourceType, source_type.name) is None:
            session.add(SourceType(**source_type.model_dump()))
            report.source_types += 1
    await session.flush()


async def _seed_country_tables(
    session: AsyncSession, seed: CountrySeed, report: SeedReport
) -> None:
    code = seed.settings.country_code
    if await session.get(CountrySettings, code) is None:
        session.add(
            CountrySettings(
                country_code=code,
                name=seed.settings.name,
                naming_rules=seed.settings.naming_rules.model_dump(),
            )
        )
        report.country_settings += 1
    await session.flush()
    for level in seed.administrative_levels:
        if await session.get(AdministrativeLevel, (code, level.name)) is None:
            session.add(AdministrativeLevel(country_code=code, **level.model_dump()))
            report.administrative_levels += 1
    for row in seed.institution_types:
        if await session.get(CountryInstitutionType, (code, row.institution_type)) is None:
            session.add(CountryInstitutionType(country_code=code, **row.model_dump()))
            report.country_institution_types += 1
    await session.flush()


async def _seed_place(
    session: AsyncSession, code: str, seed: PlaceSeed, parent: Place | None, report: SeedReport
) -> Place:
    """The place, its government and their domains, each created verified by hand when it is
    not there yet."""
    place = await session.scalar(
        select(Place).where(
            Place.country_code == code,
            Place.administrative_level == seed.level,
            Place.name == seed.name,
        )
    )
    if place is None:
        place = Place(
            name=seed.name,
            country_code=code,
            administrative_level=seed.level,
            parent_place_id=parent.id if parent is not None else None,
            status=EntityStatus.VERIFIED,
            entered_by=EnteredBy.MANUAL,
        )
        session.add(place)
        await session.flush()
        report.places += 1
    if await _add_alias(session, place, seed.name, seed.language):
        report.aliases += 1
    if seed.government is not None and place.government_institution_id is None:
        level = await session.get_one(AdministrativeLevel, (code, seed.level))
        government = Institution(
            name=seed.government,
            institution_type=level.government_institution_type,
            place_id=place.id,
            procurement_handled_by=ProcurementHandledBy.SELF,
            status=EntityStatus.VERIFIED,
            entered_by=EnteredBy.MANUAL,
        )
        session.add(government)
        await session.flush()
        place.government_institution_id = government.id
        report.institutions += 1
    if place.government_institution_id is not None and seed.government is not None:
        government = await session.get_one(Institution, place.government_institution_id)
        if await _add_alias(session, government, seed.government, seed.language):
            report.aliases += 1
    for name in seed.domains:
        if await _add_domain(session, name, DomainKind.OFFICIAL):
            report.domains += 1
    return place


async def _add_domain(session: AsyncSession, name: str, kind: DomainKind) -> bool:
    """Whether a domain was added. One that is there already is left as it is, whatever its kind
    or status: a reviewer may have changed either."""
    if await session.scalar(select(Domain.id).where(Domain.name == name)) is not None:
        return False
    session.add(
        Domain(
            name=name,
            domain_kind=kind,
            status=EntityStatus.VERIFIED,
            entered_by=EnteredBy.MANUAL,
        )
    )
    await session.flush()
    return True


async def _add_alias(
    session: AsyncSession, owner: Place | Institution, text: str, language: str
) -> bool:
    owner_column = Alias.place_id if isinstance(owner, Place) else Alias.institution_id
    found = await session.scalar(
        select(Alias.id).where(owner_column == owner.id, Alias.text == text)
    )
    if found is not None:
        return False
    alias = Alias(text=text, language=language, entered_by=EnteredBy.MANUAL)
    if isinstance(owner, Place):
        alias.place_id = owner.id
    else:
        alias.institution_id = owner.id
    session.add(alias)
    await session.flush()
    return True
