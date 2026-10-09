"""The health units list: `entries()` on the saved page keeps every rule, the count is pinned,
and the hand-written table names loaded places at the levels Reg. 553 means."""

from collections.abc import Callable
from urllib.parse import urlsplit

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import InstitutionEntry, PlaceEntry, ServedPlace
from public_atlas.modules.imports.lists.canada.ontario import health_units
from public_atlas.modules.imports.lists.canada.ontario.communities import Location

from .conftest import open_sources

UNITS = 29
DEPARTMENTS = 11
# Served places named like another place: a county like its separated city, a district like
# its town, the City of Hamilton like the township. The level and parent the entry gives tell
# them apart.
NAMESAKES = frozenset(
    {
        "Cochrane",
        "Essex",
        "Hamilton",
        "Kenora",
        "Parry Sound",
        "Perth",
        "Peterborough",
        "Rainy River",
        "Renfrew",
        "Thunder Bay",
        "Waterloo",
    }
)


@pytest.fixture(scope="module")
def opened() -> dict[str, files.OpenedFile]:
    return open_sources(health_units)


@pytest.fixture(scope="module")
def entries(
    opened: dict[str, files.OpenedFile], rules: countries.CountryRules
) -> list[InstitutionEntry]:
    return health_units.entries(opened, rules)


@pytest.fixture(scope="module")
def by_name(entries: list[InstitutionEntry]) -> dict[str, InstitutionEntry]:
    return {entry.name: entry for entry in entries}


def test_the_counts(entries: list[InstitutionEntry]):
    assert len(entries) == UNITS
    assert len(health_units.OVERRIDES) == UNITS
    assert {entry.name for entry in entries} == set(health_units.OVERRIDES)
    assert all(entry.homepage for entry in entries)
    assert all(entry.institution_type == "public_health_unit" for entry in entries)
    departments = [name for name, fields in health_units.OVERRIDES.items() if "place" in fields]
    assert len(departments) == DEPARTMENTS


def test_every_unit_cites_its_row_and_sits_at_one_loaded_place(
    entries: list[InstitutionEntry],
    opened: dict[str, files.OpenedFile],
    find_places: Callable[[str, str | None, str | None], list[PlaceEntry]],
):
    page = opened[health_units.PAGE.name]
    for entry in entries:
        citation = entry.citations["institution"]
        assert citation.source == health_units.PAGE.name
        assert page.line(citation.line).startswith(entry.name)
        assert entry.parent_institution is None
        found = find_places(entry.place, entry.place_level, entry.place_parent)
        assert len(found) == 1, (entry.name, entry.place)
        fields = health_units.OVERRIDES[entry.name]
        assert entry.place_level is not None
        if "place" in fields:
            assert fields["place"] == Location(entry.place, entry.place_level, entry.place_parent)
        else:
            assert entry.place_level == "municipality"
        assert entry.homepage is not None
        parts = urlsplit(entry.homepage)
        assert parts.scheme in ("http", "https")
        assert parts.netloc in page.line(entry.citations["homepage"].line).lower(), entry.name
        legal = str(fields["legal_name"])
        assert legal.endswith("Health Unit")
        if legal != entry.name:
            assert entry.aliases[-1].text == legal
        else:
            assert not entry.aliases


def test_the_served_places_are_loaded_at_the_levels_the_regulation_means(
    entries: list[InstitutionEntry],
    places: list[PlaceEntry],
    find_places: Callable[[str, str | None, str | None], list[PlaceEntry]],
):
    ambiguous: set[str] = set()
    for entry in entries:
        served = health_units.OVERRIDES[entry.name]["served"]
        assert isinstance(served, tuple)
        assert served, entry.name
        for where in served:
            assert isinstance(where, Location)
            found = find_places(where.place, where.level, where.parent)
            assert len(found) == 1, (entry.name, where)
            if len(find_places(where.place, None, None)) > 1:
                ambiguous.add(where.place)
        assert entry.served_places == tuple(
            ServedPlace(name=where.place, level=where.level, parent=where.parent)
            for where in served
        )
    assert ambiguous == NAMESAKES
    # Each place is served by one unit, except the three whose county and separated city
    # share a name and the two the schedules name twice over.
    counts: dict[tuple[str, str], int] = {}
    for fields in health_units.OVERRIDES.values():
        served = fields["served"]
        assert isinstance(served, tuple)
        for where in served:
            counts[where.place, where.level] = counts.get((where.place, where.level), 0) + 1
    assert all(count == 1 for count in counts.values()), counts

    def under(region: str) -> set[str]:
        return {
            entry.name
            for entry in places
            if entry.level == "municipality" and entry.parent == region
        }

    assert {where.place for where in health_units.ALGOMA_LESS_HORNEPAYNE} == under("Algoma") - {
        "Hornepayne"
    }
    assert {where.place for where in health_units.NIPISSING_LESS_TWO} == under("Nipissing") - {
        "Temagami",
        "South Algonquin",
    }


def _names(entry: InstitutionEntry) -> tuple[str, ...]:
    return tuple(served.name for served in entry.served_places)


def test_the_rows_that_show_the_rules(by_name: dict[str, InstitutionEntry]):
    lakelands = by_name["Lakelands Public Health"]
    assert [alias.text for alias in lakelands.aliases] == [
        "Haliburton Kawartha Northumberland Peterborough Health Unit"
    ]
    assert lakelands.homepage == "http://www.lakelandsph.ca/"
    assert (lakelands.place, lakelands.place_level) == ("Peterborough", "municipality")
    assert [(where.name, where.level) for where in lakelands.served_places] == [
        ("Haliburton", "region"),
        ("Kawartha Lakes", "municipality"),
        ("Northumberland", "region"),
        ("Peterborough", "municipality"),
        ("Peterborough", "region"),
    ]
    grand_erie = by_name["Grand Erie Public Health"]
    assert grand_erie.homepage == "http://geph.ca/"
    assert grand_erie.place == "Brantford"
    northeastern = by_name["Northeastern Public Health"]
    assert [(alias.text, alias.is_acronym) for alias in northeastern.aliases] == [
        ("NEPH", True),
        ("Northeastern Health Unit", False),
    ]
    assert _names(northeastern) == ("Cochrane", "Timiskaming", "Hornepayne", "Temagami")
    toronto = by_name["Toronto Public Health"]
    assert (toronto.place, toronto.place_level) == ("Toronto", "municipality")
    assert toronto.homepage == "http://toronto.ca/community-people/health-wellness-care"
    assert _names(toronto) == ("Toronto",)
    hamilton = by_name["Hamilton Public Health Services"]
    assert (hamilton.place, hamilton.place_parent) == ("Hamilton", "Ontario")
    assert hamilton.served_places == (
        ServedPlace(name="Hamilton", level="municipality", parent="Ontario"),
    )
    durham = by_name["Durham Region Health Department"]
    assert (durham.place, durham.place_level) == ("Durham", "region")
    waterloo = by_name["Region of Waterloo Public Health and Paramedic Services"]
    assert (waterloo.place, waterloo.place_level) == ("Waterloo", "region")
    assert by_name["Lambton Public Health"].place_level == "region"
    southeast = by_name["Southeast Public Health"]
    assert [alias.text for alias in southeast.aliases] == ["South East Health Unit"]
    assert southeast.homepage == "http://www.southeastph.ca/"
    assert southeast.place == "Kingston"
    assert by_name["Windsor-Essex County Health Unit"].aliases == ()
    assert _names(by_name["Windsor-Essex County Health Unit"]) == ("Essex", "Windsor", "Pelee")
    assert by_name["Grey Bruce Public Health"].place == "Owen Sound"
    assert by_name["Public Health Sudbury & Districts"].place == "Greater Sudbury"
    assert by_name["Chatham-Kent Public Health"].place == "Chatham-Kent"
    assert by_name["Algoma Public Health"].place == "Sault Ste. Marie"
    assert len(by_name["Algoma Public Health"].served_places) == 21
