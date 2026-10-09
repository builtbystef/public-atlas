"""The municipalities list: `entries()` on the cached files keeps every rule, the counts of
each exception class are pinned, and a few places show the rules a count cannot."""

from collections import Counter

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.us import census, municipalities, states_counties

# 19,469 places of status A and the two of status B.
PLACES = 19471
# 16,147 subdivisions of status A and 17 of status B; the 29 of status C are merged.
SUBDIVISIONS = 16164
CONSOLIDATED_CITIES = 8
ENTRIES = PLACES + SUBDIVISIONS + CONSOLIDATED_CITIES
INDEPENDENT_CITIES = 41
MERGED = 29
# The 22 cities whose county is consolidated with them and the places incorporated beside them
# (Jacksonville Beach in Duval County, the eighty small cities of Jefferson County, Kentucky).
IN_CONSOLIDATED_COUNTY = 151
UNDER_STATE = {
    "Massachusetts": 254,
    "Connecticut": 179,
    "Alaska": 96,
    "Rhode Island": 39,
    "Virginia": 38,
    "Maryland": 1,
    "Missouri": 1,
    "Nevada": 1,
}


@pytest.fixture(scope="module")
def opened(municipalities_files: dict[str, files.OpenedFile]) -> dict[str, files.OpenedFile]:
    return municipalities_files


@pytest.fixture(scope="module")
def built(opened: dict[str, files.OpenedFile]) -> tuple[list[PlaceEntry], municipalities.Notes]:
    return municipalities.build(opened)


@pytest.fixture(scope="module")
def entries(built: tuple[list[PlaceEntry], municipalities.Notes]) -> list[PlaceEntry]:
    return built[0]


@pytest.fixture(scope="module")
def notes(built: tuple[list[PlaceEntry], municipalities.Notes]) -> municipalities.Notes:
    return built[1]


@pytest.fixture(scope="module")
def by_code(entries: list[PlaceEntry]) -> dict[str, PlaceEntry]:
    return {entry.code.value: entry for entry in entries}


@pytest.fixture(scope="module")
def counties(states_counties_files: dict[str, files.OpenedFile]) -> dict[str, PlaceEntry]:
    """The county places the counties list loads, by code."""
    found, _ = states_counties.build(states_counties_files)
    return {entry.code.value: entry for entry in found if entry.level == "county"}


def test_the_counts(
    entries: list[PlaceEntry], opened: dict[str, files.OpenedFile], rules: countries.CountryRules
):
    assert len(municipalities.entries(opened, rules)) == ENTRIES
    assert len(entries) == ENTRIES
    assert all(entry.level == "municipality" for entry in entries)
    assert all(entry.government for entry in entries)
    codes = [entry.code.value for entry in entries]
    assert len(set(codes)) == len(codes)
    assert Counter(len(code) for code in codes) == {
        7: PLACES + CONSOLIDATED_CITIES,
        10: SUBDIVISIONS,
    }


def test_the_exception_classes_are_pinned(notes: municipalities.Notes):
    assert dict(notes.place_classes) == {
        ("?", "A"): 37,
        ("C1", "A"): 14963,
        ("C1", "B"): 2,
        ("C2", "A"): 268,
        ("C5", "A"): 4136,
        ("C5", "N"): 1,
        ("C6", "A"): 14,
        ("C7", "A"): INDEPENDENT_CITIES,
        ("C8", "F"): CONSOLIDATED_CITIES,
        ("C9", "N"): 2,
        ("U1", "A"): 10,
        ("U2", "S"): 1,
    }
    assert dict(notes.subdivision_classes) == {
        ("?", "A"): 5,
        ("?", "F"): 23,
        ("?", "I"): 2,
        ("?", "S"): 8,
        ("C2", "F"): 232,
        ("C5", "F"): 4140,
        ("T1", "A"): 16142,
        ("T1", "C"): 1,
        ("T1", "F"): 2,
        ("T1", "I"): 9,
        ("T1", "S"): 1,
        ("T5", "B"): 17,
        ("T5", "C"): 28,
        ("T9", "I"): 108,
        ("Z1", "N"): 41,
        ("Z2", "F"): 18,
        ("Z3", "S"): 237,
    }
    assert dict(notes.dropped) == {
        ("061", "F"): 4415,
        ("061", "I"): 119,
        ("061", "N"): 41,
        ("061", "S"): 246,
        ("162", "F"): 8,
        ("162", "N"): 3,
        ("162", "S"): 1,
    }
    assert dict(notes.kinds) == {
        "township": 12449,
        "city": 10225,
        "town": 7838,
        "village": 3707,
        "borough": 1214,
        "charter township": 118,
        None: 42,
        "plantation": 29,
        "municipality": 7,
        "unified government": 5,
        "city and borough": 3,
        "consolidated government": 2,
        "metropolitan government": 2,
        "urban county": 1,
        "metro government": 1,
    }
    assert len(notes.independent_cities) == INDEPENDENT_CITIES
    assert "5101000 Alexandria city, Virginia" in notes.independent_cities
    assert "3209700 Carson City, Nevada" in notes.independent_cities
    assert len(notes.consolidated_cities) == CONSOLIDATED_CITIES
    assert len(notes.merged) == MERGED
    assert "0911037070 Hartford town, Connecticut -> Hartford city" in notes.merged
    assert "0917047535 Milford town, Connecticut -> Milford city (balance), Woodmont borough" in (
        notes.merged
    )
    assert "3915981242 Washington township, Ohio -> Dublin city (pt.)" in notes.merged
    assert len(notes.in_consolidated_county) == IN_CONSOLIDATED_COUNTY
    assert Counter(line.split(", ")[-1] for line in notes.under_state) == UNDER_STATE
    assert len(notes.overrides) == len(municipalities.OVERRIDES)


def test_every_entry_has_its_code_population_and_a_government_the_naming_rules_give(
    entries: list[PlaceEntry], opened: dict[str, files.OpenedFile], rules: countries.CountryRules
):
    naming = rules.naming
    register = opened[census.SUB_EST.name]
    for entry in entries:
        assert entry.code.scheme is IdentifierScheme.FIPS
        assert entry.code.value.isdigit()
        (population,) = entry.figures
        assert (population.name, population.year) == (MetricName.POPULATION, 2025)
        assert population.value >= 0
        line = register.line(entry.citations["place"].line)
        assert any(name in line for name in (entry.name, *(a.text for a in entry.aliases)))
        assert str(population.value) in line
        assert entry.government is not None
        # "City of Springfield" governs "Springfield"; "Carson City" and "Township 1" are their
        # own names; "Town of Dodge City" carries its place's whole name.
        assert naming.core(entry.government) in (
            naming.core(entry.name),
            naming.key(entry.name),
        ) or naming.key(entry.name) in naming.key(entry.government), entry.name


def test_every_parent_is_a_loaded_county_named_with_its_state_or_the_state(
    entries: list[PlaceEntry], counties: dict[str, PlaceEntry]
):
    by_name = {(entry.name, entry.parent): entry for entry in counties.values()}
    for entry in entries:
        if entry.parent_level == "county":
            assert entry.parent is not None
            county = by_name[entry.parent, entry.parent_parent]
            assert entry.code.value[:2] == county.code.value[:2], entry.name
            if len(entry.code.value) == 10:
                assert entry.code.value[:5] == county.code.value, entry.name
        else:
            assert entry.parent_level == "state"
            assert entry.parent_parent is None
    # A town and the village inside it are two places under one county, told apart by their
    # governments' designators.
    hamburgs = [
        entry
        for entry in entries
        if entry.name == "Hamburg"
        and (entry.parent, entry.parent_parent) == ("Erie County", "New York")
    ]
    assert sorted(entry.government or "" for entry in hamburgs) == [
        "Town of Hamburg",
        "Village of Hamburg",
    ]


def test_no_two_places_of_one_name_and_kind_sit_under_one_parent(
    entries: list[PlaceEntry], rules: countries.CountryRules
):
    """What the loader tells apart: two places under one parent whose plain name is a form of
    the other's ("Hamburg" and "Hamburg") are bodies of different kinds by the designators
    around their names ("Town of Hamburg" and "Village of Hamburg", "City of Bird City" and
    "Township of Bird City"); any other pair would be merged into one place. "Galesburg City"
    is no form of "Galesburg", so the two townships are two places."""
    naming = rules.naming

    def kind(entry: PlaceEntry) -> set[int]:
        assert entry.government is not None
        return naming.designators_in(
            naming.key(entry.government).replace(naming.key(entry.name), " ")
        )

    by_parent: dict[tuple[str | None, str | None], list[PlaceEntry]] = {}
    for entry in entries:
        by_parent.setdefault((entry.parent, entry.parent_parent), []).append(entry)
    for siblings in by_parent.values():
        # In the loader's order: by name, so "Galesburg" is loaded before "Galesburg City" and
        # the second is matched against the first, not the other way round.
        loaded: dict[str, list[PlaceEntry]] = {}
        for entry in sorted(siblings, key=lambda entry: entry.name):
            for form in naming.plain_forms(entry.name):
                for earlier in loaded.get(form, []):
                    pair = (earlier.name, earlier.government, entry.name, entry.government)
                    assert kind(earlier), pair
                    assert kind(entry), pair
                    assert not kind(earlier) & kind(entry), pair
            for form in naming.forms(entry.name):
                loaded.setdefault(form, []).append(entry)


def test_the_places_that_show_the_rules(by_code: dict[str, PlaceEntry]):
    springfield = by_code["1772000"]
    assert (springfield.name, springfield.parent, springfield.parent_parent) == (
        "Springfield",
        "Sangamon County",
        "Illinois",
    )
    assert springfield.government == "City of Springfield"
    # An independent city sits under its state; its county code is not kept.
    alexandria = by_code["5101000"]
    assert (alexandria.parent, alexandria.parent_level, alexandria.government) == (
        "Virginia",
        "state",
        "City of Alexandria",
    )
    assert "51510" not in by_code
    assert by_code["3209700"].government == "Carson City"
    # A consolidated city under the county of its balance; the balance is not loaded.
    indianapolis = by_code["1836000"]
    assert (indianapolis.name, indianapolis.parent, indianapolis.government) == (
        "Indianapolis",
        "Marion County",
        "City of Indianapolis",
    )
    assert "1836003" not in by_code
    assert by_code["1816336"].government == "Town of Cumberland"
    louisville = by_code["2148003"]
    assert louisville.government == "Louisville/Jefferson County Metro Government"
    assert [alias.text for alias in louisville.aliases] == ["Louisville"]
    assert by_code["0947500"].parent == "Connecticut"
    # A county consolidated with its city: the city carries the government.
    assert by_code["0667000"].government == "City and County of San Francisco"
    assert by_code["0667000"].parent == "San Francisco County"
    new_york = by_code["3651000"]
    assert (new_york.parent, new_york.government) == ("Kings County", "City of New York")
    assert by_code["1235050"].parent == "Duval County"
    # Connecticut's merged towns and its boroughs.
    assert by_code["0937000"].government == "City of Hartford"
    assert "0911037070" not in by_code
    assert by_code["0988050"].government == "Borough of Woodmont"
    # A charter township, a plantation, a numbered township.
    assert by_code["2616313120"].government == "Charter Township of Canton"
    assert by_code["2300315990"].government == "Cyr Plantation"
    assert by_code["2007771201"].government == "Township 1"
    # Overrides.
    assert by_code["3460900"].government == "Municipality of Princeton"
    ranson = by_code["5466988"]
    assert (ranson.name, ranson.government) == ("Ranson", "City of Ranson")
    assert [alias.text for alias in ranson.aliases] == ["Ranson corporation"]
    # Baton Rouge beside its parish; Washington city is not loaded.
    assert by_code["2205000"].government == "City of Baton Rouge"
    assert "1150000" not in by_code
