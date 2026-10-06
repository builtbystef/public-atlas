"""`load_rules` reads the country tables as they are now: an edit shows on the next load."""

from typing import TYPE_CHECKING

import pytest

from public_atlas.modules.countries import service
from public_atlas.modules.countries.models import AdministrativeLevel, CountryInstitutionType
from public_atlas.modules.countries.seeds import canada
from public_atlas.modules.graph.models import Domain, DomainKind, EnteredBy, EntityStatus
from public_atlas.shared.exceptions import NotFoundError

if TYPE_CHECKING:
    from tests.integration.conftest import Database


async def seed_and_load(db: Database) -> service.CountryRules:
    async with db.session() as session:
        await service.seed(session, canada.SEED)
        await session.commit()
        return await service.load_rules(session, "CA")


async def load(db: Database, code: str) -> service.CountryRules:
    async with db.session() as session:
        return await service.load_rules(session, code)


async def edit_tables(db: Database) -> None:
    async with db.session() as session:
        level = await session.get_one(AdministrativeLevel, ("CA", "municipality"))
        level.expected_institution_types = [*level.expected_institution_types, "hospital"]
        use = await session.get_one(CountryInstitutionType, ("CA", "library"))
        use.expected_source_types = ["procurement"]
        session.add(
            Domain(
                name="newplatform.example",
                domain_kind=DomainKind.PLATFORM,
                status=EntityStatus.VERIFIED,
                entered_by=EnteredBy.MANUAL,
            )
        )
        await session.commit()


def test_the_rules_come_from_the_tables(db: Database):
    rules = db.run(seed_and_load, db)
    seeded = service.rules_from_seed(canada.SEED)

    assert rules.country_code == "CA"
    assert [level.name for level in rules.levels_by_rank] == [
        level.name for level in seeded.levels_by_rank
    ]
    assert rules.expected_institution_types("municipality") == seeded.expected_institution_types(
        "municipality"
    )
    assert rules.expected_source_types("library") == seeded.expected_source_types("library")
    assert rules.institution_types == seeded.institution_types
    assert rules.source_types == seeded.source_types
    assert set(rules.platforms) == set(canada.PLATFORMS)
    assert rules.name_mismatch("ministry", "Transportation") is not None
    assert rules.naming.core("Township of Elmwood") == "elmwood"


def test_an_edit_takes_effect_on_the_next_load(db: Database):
    before = db.run(seed_and_load, db)
    db.run(edit_tables, db)
    after = db.run(load, db, "CA")

    assert "hospital" not in before.expected_institution_types("municipality")
    assert "hospital" in after.expected_institution_types("municipality")
    assert after.expected_source_types("library") == ["procurement"]
    assert after.is_platform("x.newplatform.example")
    assert not before.is_platform("x.newplatform.example")


def test_an_unseeded_country_is_not_found(db: Database):
    with pytest.raises(NotFoundError, match="seed"):
        db.run(load, db, "XX")
