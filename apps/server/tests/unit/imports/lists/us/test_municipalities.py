"""The municipalities list: the counts are pinned, every government is named from its place
with the line's figure, every parent is the loaded county the code names or the state, and a
few places show the rules a count cannot. What every list's entries must satisfy is checked
by the contract test beside the lists."""

from collections import Counter
from typing import Any

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.us import census, municipalities

pytestmark = pytest.mark.lists

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
def opened(sources_of) -> dict[str, files.OpenedFile]:
    return sources_of(municipalities)


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


def test_the_counts(entries: list[PlaceEntry]):
    assert len(entries) == ENTRIES
    assert all(entry.level == "municipality" for entry in entries)
    assert all(entry.government for entry in entries)
    codes = [entry.code.value for entry in entries]
    assert len(set(codes)) == len(codes)
    assert Counter(len(code) for code in codes) == {
        7: PLACES + CONSOLIDATED_CITIES,
        10: SUBDIVISIONS,
    }


def test_the_rules_leave_out_and_fold_what_they_say(notes: municipalities.Notes):
    """The independent cities, the consolidated cities, the subdivisions merged into their
    place and the places left under their state, by what the notes name."""
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


def test_every_government_is_named_from_its_place_and_the_figure_is_the_lines(
    entries: list[PlaceEntry], opened: dict[str, files.OpenedFile], rules: countries.CountryRules
):
    naming = rules.naming
    register = opened[census.SUB_EST.name]
    for entry in entries:
        (population,) = entry.figures
        assert str(population.value) in register.line(entry.citations["place"].line)
        assert entry.government is not None, entry.name
        # "City of Springfield" governs "Springfield"; "Carson City" and "Township 1" are their
        # own names; "Town of Dodge City" carries its place's whole name.
        assert naming.core(entry.government) in (
            naming.core(entry.name),
            naming.key(entry.name),
        ) or naming.key(entry.name) in naming.key(entry.government), entry.name


def test_every_parent_is_the_loaded_county_the_code_names_or_the_state(
    entries: list[PlaceEntry],
    loaded: Any,
):
    for entry in entries:
        if entry.parent_level == "county":
            (county,) = loaded.find(entry.parent, "county", entry.parent_parent)
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
    assert any(
        pair.name == "Hamburg"
        and {pair.government, pair.other_government} == {"Town of Hamburg", "Village of Hamburg"}
        for pair in loaded.told_apart
    )


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
