"""Seeding Canada fills the country tables and creates the anchors (the federal government and
each province's and territory's); a second run adds nothing and leaves an edit alone, except
that the seed's naming rules replace the row's when they differ."""

import copy
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from public_atlas.modules.countries import service
from public_atlas.modules.countries.models import (
    AdministrativeLevel,
    CountryInstitutionType,
    CountrySettings,
    InstitutionType,
    SourceType,
)
from public_atlas.modules.countries.seeds import canada, shared, united_states
from public_atlas.modules.graph.models import (
    Alias,
    Domain,
    DomainKind,
    EnteredBy,
    Entity,
    EntityStatus,
    Institution,
    Place,
)

if TYPE_CHECKING:
    from tests.integration.conftest import Database


async def seed_canada(db: Database) -> service.SeedReport:
    async with db.session() as session:
        report = await service.seed(session, canada.SEED)
        await session.commit()
    return report


async def count(db: Database, model: type) -> int:
    async with db.session() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


def test_seeding_fills_the_country_tables(db: Database):
    report = db.run(seed_canada, db)

    assert report.institution_types == len(shared.INSTITUTION_TYPES)
    assert report.source_types == len(shared.SOURCE_TYPES)
    assert report.country_settings == 1
    assert report.administrative_levels == len(canada.ADMINISTRATIVE_LEVELS)
    assert report.country_institution_types == len(canada.INSTITUTION_TYPES)
    anchors = [place for place in canada.PLACES if place.get("government")]
    assert report.domains == len(canada.PLATFORMS) + sum(len(p["domains"]) for p in anchors)
    assert report.places == len(canada.PLACES) == 14
    assert report.institutions == len(anchors) == 14
    # Each place's name and each government's.
    assert report.aliases == len(canada.PLACES) + len(anchors)
    assert db.run(count, db, InstitutionType) == len(shared.INSTITUTION_TYPES)
    assert db.run(count, db, SourceType) == len(shared.SOURCE_TYPES)
    assert db.run(count, db, AdministrativeLevel) == len(canada.ADMINISTRATIVE_LEVELS)
    assert db.run(count, db, CountryInstitutionType) == len(canada.INSTITUTION_TYPES)


async def read_ontario(db: Database) -> tuple[Place, Place, Institution, list[Domain]]:
    async with db.session() as session:
        canada_place = (
            await session.execute(select(Place).where(Place.name == "Canada"))
        ).scalar_one()
        ontario = (await session.execute(select(Place).where(Place.name == "Ontario"))).scalar_one()
        assert ontario.government_institution_id is not None
        government = await session.get_one(Institution, ontario.government_institution_id)
        domains = list(
            (
                await session.execute(
                    select(Domain).where(Domain.name.in_(["ontario.ca", "gov.on.ca"]))
                )
            ).scalars()
        )
        return canada_place, ontario, government, domains


def test_seeding_creates_the_ontario_anchor_verified_by_hand(db: Database):
    db.run(seed_canada, db)
    canada_place, ontario, government, domains = db.run(read_ontario, db)

    assert canada_place.administrative_level == "country"
    assert canada_place.parent_place_id is None
    assert canada_place.government_institution_id is not None
    assert ontario.parent_place_id == canada_place.id
    assert ontario.administrative_level == "province_territory"
    assert (ontario.status, ontario.entered_by) == (EntityStatus.VERIFIED, EnteredBy.MANUAL)
    assert government.name == "Government of Ontario"
    assert government.institution_type == "provincial_government"
    assert government.place_id == ontario.id
    assert (government.status, government.entered_by) == (
        EntityStatus.VERIFIED,
        EnteredBy.MANUAL,
    )
    assert len(domains) == 2
    for domain in domains:
        assert domain.domain_kind == DomainKind.OFFICIAL
        assert domain.status == EntityStatus.VERIFIED


async def read_platform_and_aliases(db: Database) -> tuple[Domain, list[str], list[str]]:
    async with db.session() as session:
        youtube = (
            await session.execute(select(Domain).where(Domain.name == "youtube.com"))
        ).scalar_one()
        ontario = (await session.execute(select(Place).where(Place.name == "Ontario"))).scalar_one()
        place_aliases = list(
            (
                await session.execute(select(Alias.text).where(Alias.place_id == ontario.id))
            ).scalars()
        )
        government_aliases = list(
            (
                await session.execute(
                    select(Alias.text).where(
                        Alias.institution_id == ontario.government_institution_id
                    )
                )
            ).scalars()
        )
        return youtube, place_aliases, government_aliases


def test_platforms_are_never_trusted_and_names_become_aliases(db: Database):
    db.run(seed_canada, db)
    youtube, place_aliases, government_aliases = db.run(read_platform_and_aliases, db)

    assert youtube.domain_kind == DomainKind.PLATFORM
    assert youtube.entered_by == EnteredBy.MANUAL
    assert place_aliases == ["Ontario"]
    assert government_aliases == ["Government of Ontario"]


async def edit_a_description_and_a_setting(db: Database) -> None:
    async with db.session() as session:
        hospital = await session.get_one(InstitutionType, "hospital")
        hospital.description = "Edited in the console"
        settings = await session.get_one(CountrySettings, "CA")
        settings.name = "Canada (edited)"
        await session.commit()


async def read_the_edits(db: Database) -> tuple[str, str]:
    async with db.session() as session:
        hospital = await session.get_one(InstitutionType, "hospital")
        settings = await session.get_one(CountrySettings, "CA")
        return hospital.description, settings.name


def test_a_second_run_adds_nothing_and_keeps_edits(db: Database):
    db.run(seed_canada, db)
    db.run(edit_a_description_and_a_setting, db)
    entities_before = db.run(count, db, Entity)

    report = db.run(seed_canada, db)

    assert report.added == 0
    assert report.naming_rules_changed is False
    assert db.run(count, db, Entity) == entities_before
    assert db.run(read_the_edits, db) == ("Edited in the console", "Canada (edited)")


async def seed_with_a_designator(db: Database) -> service.SeedReport:
    seed = copy.deepcopy(canada.SEED)
    seed["settings"]["naming_rules"]["designators"].append(["Hamlet"])
    async with db.session() as session:
        report = await service.seed(session, seed)
        await session.commit()
    return report


async def read_the_rules(db: Database) -> tuple[str, dict]:
    async with db.session() as session:
        settings = await session.get_one(CountrySettings, "CA")
        return settings.name, settings.naming_rules


def test_a_changed_seed_rewrites_the_naming_rules_and_nothing_else(db: Database):
    db.run(seed_canada, db)
    db.run(edit_a_description_and_a_setting, db)

    report = db.run(seed_with_a_designator, db)

    assert report.added == 0
    assert report.naming_rules_changed is True
    name, rules = db.run(read_the_rules, db)
    assert name == "Canada (edited)"
    assert ["Hamlet"] in rules["designators"]
    assert db.run(seed_with_a_designator, db).naming_rules_changed is False


async def seed_united_states(db: Database) -> service.SeedReport:
    async with db.session() as session:
        report = await service.seed(session, united_states.SEED)
        await session.commit()
    return report


async def read_ohio(db: Database) -> tuple[Place, Institution, list[Domain]]:
    async with db.session() as session:
        ohio = (
            await session.execute(
                select(Place).where(Place.name == "Ohio", Place.country_code == "US")
            )
        ).scalar_one()
        assert ohio.government_institution_id is not None
        government = await session.get_one(Institution, ohio.government_institution_id)
        domains = list(
            (
                await session.execute(select(Domain).where(Domain.name.in_(["ohio.gov", "oh.gov"])))
            ).scalars()
        )
        return ohio, government, domains


def test_seeding_the_united_states_beside_canada_adds_its_tables_and_anchors(db: Database):
    db.run(seed_canada, db)
    report = db.run(seed_united_states, db)

    # The global types are there already; the country's tables and anchors are new.
    assert report.institution_types == 0
    assert report.source_types == 0
    assert report.country_settings == 1
    assert report.administrative_levels == len(united_states.ADMINISTRATIVE_LEVELS)
    assert report.country_institution_types == len(united_states.INSTITUTION_TYPES)
    assert report.places == len(united_states.PLACES) == 53
    assert report.institutions == 53
    # Platforms Canada seeded too (youtube.com, jaggaer.com...) are not added twice.
    shared_platforms = set(united_states.PLATFORMS) & set(canada.PLATFORMS)
    assert report.domains == (
        len(united_states.PLATFORMS)
        - len(shared_platforms)
        + sum(len(place["domains"]) for place in united_states.PLACES)
    )
    ohio, government, domains = db.run(read_ohio, db)
    assert ohio.administrative_level == "state"
    assert (ohio.status, ohio.entered_by) == (EntityStatus.VERIFIED, EnteredBy.MANUAL)
    assert (government.name, government.institution_type) == (
        "State of Ohio",
        "provincial_government",
    )
    assert {domain.name for domain in domains} == {"ohio.gov", "oh.gov"}
    assert all(domain.status == EntityStatus.VERIFIED for domain in domains)

    again = db.run(seed_united_states, db)
    assert again.added == 0
