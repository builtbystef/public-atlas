"""The country tables: seeding them (spec section 5.1), reading them as a `CountryRules` object
at the start of each assignment or load, and editing them from the console with every array
validated against the type tables (spec section 4.4).

Seeding adds what is missing and never deletes or rewrites, so an edit made in the console
survives a reseed.
"""

from dataclasses import dataclass, fields
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.countries.models import (
    AdministrativeLevel,
    CountryInstitutionType,
    CountrySettings,
    InstitutionType,
    SourceType,
)
from public_atlas.modules.countries.rules import CountryRules, build_rules
from public_atlas.modules.countries.schemas import (
    AdministrativeLevelInput,
    CountryInstitutionTypeInput,
    CountryOutput,
    CountrySeed,
    CountrySettingsInput,
    InstitutionTypeInput,
    PlaceSeed,
    SharedSeed,
    SourceTypeInput,
)
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
from public_atlas.shared.exceptions import ConflictError, NotFoundError, UnprocessableError

__all__ = [
    "CountryRules",
    "SeedReport",
    "delete_administrative_level",
    "delete_country_institution_type",
    "delete_institution_type",
    "delete_source_type",
    "list_countries",
    "list_institution_types",
    "list_source_types",
    "load_rules",
    "put_administrative_level",
    "put_country_institution_type",
    "put_country_settings",
    "put_institution_type",
    "put_source_type",
    "read_country",
    "rules_from_seed",
    "seed",
    "validate",
]


# --- Seeds ---


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


# --- Rules ---


async def load_rules(session: AsyncSession, country_code: str) -> CountryRules:
    """The country's rules as the tables hold them now. Read at the start of each assignment and
    each load, never cached across them."""
    settings = await session.get(CountrySettings, country_code)
    if settings is None:
        raise NotFoundError(f"no country {country_code!r}: run `public-atlas seed` first")
    levels = await session.scalars(
        select(AdministrativeLevel).where(AdministrativeLevel.country_code == country_code)
    )
    uses = await session.scalars(
        select(CountryInstitutionType).where(CountryInstitutionType.country_code == country_code)
    )
    institution_types = await session.scalars(select(InstitutionType))
    source_types = await session.scalars(select(SourceType))
    platforms = await session.scalars(
        select(Domain.name).where(Domain.domain_kind == DomainKind.PLATFORM)
    )
    return build_rules(
        settings=CountrySettingsInput.model_validate(settings, from_attributes=True),
        administrative_levels=[
            AdministrativeLevelInput.model_validate(row, from_attributes=True) for row in levels
        ],
        country_institution_types=[
            CountryInstitutionTypeInput.model_validate(row, from_attributes=True) for row in uses
        ],
        institution_types=[
            InstitutionTypeInput.model_validate(row, from_attributes=True)
            for row in institution_types
        ],
        source_types=[
            SourceTypeInput.model_validate(row, from_attributes=True) for row in source_types
        ],
        platforms=list(platforms),
    )


def rules_from_seed(country: dict[str, Any]) -> CountryRules:
    """The rules a seed module would give, with no database: for the list modules' tests."""
    shared, seed = validate(country)
    return build_rules(
        settings=seed.settings,
        administrative_levels=seed.administrative_levels,
        country_institution_types=seed.institution_types,
        institution_types=shared.institution_types,
        source_types=shared.source_types,
        platforms=seed.platforms,
    )


# --- Reading and editing (the countries API) ---


async def list_countries(session: AsyncSession) -> list[CountrySettingsInput]:
    rows = await session.scalars(select(CountrySettings).order_by(CountrySettings.country_code))
    return [CountrySettingsInput.model_validate(row, from_attributes=True) for row in rows]


async def read_country(session: AsyncSession, country_code: str) -> CountryOutput:
    settings = await _settings(session, country_code)
    levels = await session.scalars(
        select(AdministrativeLevel)
        .where(AdministrativeLevel.country_code == country_code)
        .order_by(AdministrativeLevel.rank, AdministrativeLevel.name)
    )
    uses = await session.scalars(
        select(CountryInstitutionType)
        .where(CountryInstitutionType.country_code == country_code)
        .order_by(CountryInstitutionType.institution_type)
    )
    return CountryOutput(
        settings=CountrySettingsInput.model_validate(settings, from_attributes=True),
        administrative_levels=[
            AdministrativeLevelInput.model_validate(row, from_attributes=True) for row in levels
        ],
        institution_types=[
            CountryInstitutionTypeInput.model_validate(row, from_attributes=True) for row in uses
        ],
    )


async def put_country_settings(
    session: AsyncSession, data: CountrySettingsInput
) -> CountrySettingsInput:
    """Create the country or change its name and naming rules. Flushed, not committed."""
    row = await session.get(CountrySettings, data.country_code)
    if row is None:
        row = CountrySettings(country_code=data.country_code)
        session.add(row)
    row.name = data.name
    row.naming_rules = data.naming_rules.model_dump()
    await session.flush()
    return CountrySettingsInput.model_validate(row, from_attributes=True)


async def put_administrative_level(
    session: AsyncSession, country_code: str, name: str, data: AdministrativeLevelInput
) -> AdministrativeLevelInput:
    """Create or change the level `name`; a body naming another level renames it, and the
    places at the level follow. Its types must be ones the country uses."""
    await _settings(session, country_code)
    await _check_types_used(
        session,
        country_code,
        [data.government_institution_type, *data.expected_institution_types],
    )
    row = await session.get(AdministrativeLevel, (country_code, name))
    if row is None:
        if data.name != name:
            raise NotFoundError(f"{country_code} has no administrative level {name!r}")
        row = AdministrativeLevel(country_code=country_code, name=name)
        session.add(row)
    elif data.name != name:
        if await session.get(AdministrativeLevel, (country_code, data.name)) is not None:
            raise ConflictError(f"{country_code} already has a level {data.name!r}")
        row.name = data.name
    row.rank = data.rank
    row.government_institution_type = data.government_institution_type
    row.expected_institution_types = list(data.expected_institution_types)
    await session.flush()
    return AdministrativeLevelInput.model_validate(row, from_attributes=True)


async def delete_administrative_level(session: AsyncSession, country_code: str, name: str) -> None:
    """Refused while a place sits at the level."""
    row = await session.get(AdministrativeLevel, (country_code, name))
    if row is None:
        raise NotFoundError(f"{country_code} has no administrative level {name!r}")
    in_use = await session.scalar(
        select(Place.id)
        .where(Place.country_code == country_code, Place.administrative_level == name)
        .limit(1)
    )
    if in_use is not None:
        raise ConflictError(f"places sit at level {name!r}")
    await session.delete(row)
    await session.flush()


async def list_institution_types(session: AsyncSession) -> list[InstitutionTypeInput]:
    rows = await session.scalars(select(InstitutionType).order_by(InstitutionType.name))
    return [InstitutionTypeInput.model_validate(row, from_attributes=True) for row in rows]


async def put_institution_type(
    session: AsyncSession, name: str, data: InstitutionTypeInput
) -> InstitutionTypeInput:
    """Create or change the type `name`. A body naming another type renames it: the foreign keys
    cascade, and the levels' checklists are rewritten in the same transaction."""
    row = await session.get(InstitutionType, name)
    if row is None:
        if data.name != name:
            raise NotFoundError(f"no institution type {name!r}")
        row = InstitutionType(name=name)
        session.add(row)
    elif data.name != name:
        if await session.get(InstitutionType, data.name) is not None:
            raise ConflictError(f"an institution type {data.name!r} exists already")
        row.name = data.name
        levels = await session.scalars(
            select(AdministrativeLevel).where(
                AdministrativeLevel.expected_institution_types.contains([name])
            )
        )
        for level in levels:
            level.expected_institution_types = [
                data.name if found == name else found for found in level.expected_institution_types
            ]
    row.description = data.description
    await session.flush()
    return InstitutionTypeInput.model_validate(row, from_attributes=True)


async def delete_institution_type(session: AsyncSession, name: str) -> None:
    """Refused while a country uses the type, a level expects it or an institution has it."""
    row = await session.get(InstitutionType, name)
    if row is None:
        raise NotFoundError(f"no institution type {name!r}")
    listed = await session.scalar(
        select(AdministrativeLevel.name)
        .where(AdministrativeLevel.expected_institution_types.contains([name]))
        .limit(1)
    )
    if listed is not None:
        raise ConflictError(f"level {listed!r} expects institution type {name!r}")
    await _delete_or_conflict(session, row, f"institution type {name!r} is in use")


async def list_source_types(session: AsyncSession) -> list[SourceTypeInput]:
    rows = await session.scalars(select(SourceType).order_by(SourceType.name))
    return [SourceTypeInput.model_validate(row, from_attributes=True) for row in rows]


async def put_source_type(
    session: AsyncSession, name: str, data: SourceTypeInput
) -> SourceTypeInput:
    """As `put_institution_type`; a rename rewrites the countries' expected sources."""
    row = await session.get(SourceType, name)
    if row is None:
        if data.name != name:
            raise NotFoundError(f"no source type {name!r}")
        row = SourceType(name=name)
        session.add(row)
    elif data.name != name:
        if await session.get(SourceType, data.name) is not None:
            raise ConflictError(f"a source type {data.name!r} exists already")
        row.name = data.name
        uses = await session.scalars(
            select(CountryInstitutionType).where(
                CountryInstitutionType.expected_source_types.contains([name])
            )
        )
        for use in uses:
            use.expected_source_types = [
                data.name if found == name else found for found in use.expected_source_types
            ]
    row.description = data.description
    await session.flush()
    return SourceTypeInput.model_validate(row, from_attributes=True)


async def delete_source_type(session: AsyncSession, name: str) -> None:
    """Refused while a country expects the source or a source has the type."""
    row = await session.get(SourceType, name)
    if row is None:
        raise NotFoundError(f"no source type {name!r}")
    listed = await session.scalar(
        select(CountryInstitutionType.institution_type)
        .where(CountryInstitutionType.expected_source_types.contains([name]))
        .limit(1)
    )
    if listed is not None:
        raise ConflictError(f"institution type {listed!r} expects source type {name!r}")
    await _delete_or_conflict(session, row, f"source type {name!r} is in use")


async def put_country_institution_type(
    session: AsyncSession, country_code: str, data: CountryInstitutionTypeInput
) -> CountryInstitutionTypeInput:
    """How the country uses a type: create or change the row. The type and every expected
    source must exist."""
    await _settings(session, country_code)
    if await session.get(InstitutionType, data.institution_type) is None:
        raise UnprocessableError(f"no institution type {data.institution_type!r}")
    await _check_source_types(session, data.expected_source_types)
    row = await session.get(CountryInstitutionType, (country_code, data.institution_type))
    if row is None:
        row = CountryInstitutionType(
            country_code=country_code, institution_type=data.institution_type
        )
        session.add(row)
    row.expected_source_types = list(data.expected_source_types)
    row.name_pattern = data.name_pattern
    await session.flush()
    return CountryInstitutionTypeInput.model_validate(row, from_attributes=True)


async def delete_country_institution_type(
    session: AsyncSession, country_code: str, institution_type: str
) -> None:
    """Refused while one of the country's levels expects the type."""
    row = await session.get(CountryInstitutionType, (country_code, institution_type))
    if row is None:
        raise NotFoundError(f"{country_code} does not use institution type {institution_type!r}")
    listed = await session.scalar(
        select(AdministrativeLevel.name)
        .where(
            AdministrativeLevel.country_code == country_code,
            (AdministrativeLevel.government_institution_type == institution_type)
            | AdministrativeLevel.expected_institution_types.contains([institution_type]),
        )
        .limit(1)
    )
    if listed is not None:
        raise ConflictError(f"level {listed!r} expects institution type {institution_type!r}")
    await session.delete(row)
    await session.flush()


async def _settings(session: AsyncSession, country_code: str) -> CountrySettings:
    settings = await session.get(CountrySettings, country_code)
    if settings is None:
        raise NotFoundError(f"no country {country_code!r}")
    return settings


async def _check_types_used(
    session: AsyncSession, country_code: str, institution_types: list[str]
) -> None:
    """Every name is a type the country uses (a row in `country_institution_types`), which also
    makes it a type that exists."""
    used = set(
        await session.scalars(
            select(CountryInstitutionType.institution_type).where(
                CountryInstitutionType.country_code == country_code,
                CountryInstitutionType.institution_type.in_(institution_types),
            )
        )
    )
    if unknown := sorted(set(institution_types) - used):
        raise UnprocessableError(f"{country_code} does not use institution types {unknown}")


async def _check_source_types(session: AsyncSession, source_types: list[str]) -> None:
    known = set(
        await session.scalars(select(SourceType.name).where(SourceType.name.in_(source_types)))
    )
    if unknown := sorted(set(source_types) - known):
        raise UnprocessableError(f"no source types {unknown}")


async def _delete_or_conflict(session: AsyncSession, row: object, message: str) -> None:
    """Delete a type row, or report the foreign key that holds it."""
    try:
        async with session.begin_nested():
            await session.delete(row)
            await session.flush()
    except IntegrityError:
        raise ConflictError(message) from None
