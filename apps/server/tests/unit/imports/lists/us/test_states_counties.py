"""The states and counties list: `entries()` on the cached files keeps every rule, the counts
of each exception class are pinned, and a few places show the rules a count cannot."""

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import united_states
from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.us import census, states_counties

STATES = 52
# 3,032 active, 2 partially consolidated and 33 consolidated, less Honolulu, promoted.
COUNTIES = 3066
CONSOLIDATED_COUNTIES = 33
MUNICIPIOS = 78
# Honolulu and the municipios.
MUNICIPALITIES = MUNICIPIOS + 1
ENTRIES = STATES + COUNTIES + MUNICIPALITIES


@pytest.fixture(scope="module")
def opened(states_counties_files: dict[str, files.OpenedFile]) -> dict[str, files.OpenedFile]:
    return states_counties_files


@pytest.fixture(scope="module")
def built(opened: dict[str, files.OpenedFile]) -> tuple[list[PlaceEntry], states_counties.Notes]:
    return states_counties.build(opened)


@pytest.fixture(scope="module")
def entries(built: tuple[list[PlaceEntry], states_counties.Notes]) -> list[PlaceEntry]:
    return built[0]


@pytest.fixture(scope="module")
def notes(built: tuple[list[PlaceEntry], states_counties.Notes]) -> states_counties.Notes:
    return built[1]


@pytest.fixture(scope="module")
def by_code(entries: list[PlaceEntry]) -> dict[str, PlaceEntry]:
    return {entry.code.value: entry for entry in entries}


def test_the_counts(
    entries: list[PlaceEntry], opened: dict[str, files.OpenedFile], rules: countries.CountryRules
):
    assert len(states_counties.entries(opened, rules)) == ENTRIES
    assert len(entries) == ENTRIES
    assert sum(1 for entry in entries if entry.level == "state") == STATES
    assert sum(1 for entry in entries if entry.level == "county") == COUNTIES
    assert sum(1 for entry in entries if entry.level == "municipality") == MUNICIPALITIES
    assert sum(1 for entry in entries if entry.government is None) == CONSOLIDATED_COUNTIES
    codes = [entry.code.value for entry in entries]
    assert len(set(codes)) == len(codes)


def test_the_exception_classes_are_pinned(notes: states_counties.Notes):
    # By the 2020 class and the 2025 functional status; the nine '?' are Connecticut's planning
    # regions, which the 2020 file does not know.
    assert dict(notes.classes) == {
        ("?", "N"): 9,
        ("C7", "F"): 41,
        ("H1", "A"): 3030,
        ("H4", "G"): 1,
        ("H4", "N"): 14,
        ("H5", "S"): 11,
        ("H6", "A"): 2,
        ("H6", "B"): 2,
        ("H6", "C"): 33,
        ("H6", "F"): 1,
    }
    assert {status: len(names) for status, names in notes.dropped.items()} == {
        "F": 42,
        "G": 1,
        "N": 23,
        "S": 11,
    }
    assert "15005 Kalawao County, Hawaii" in notes.dropped["G"]
    assert "11001 District of Columbia, District of Columbia" in notes.dropped["F"]
    assert "51510 Alexandria city, Virginia" in notes.dropped["F"]
    assert "09110 Capitol Planning Region, Connecticut" in notes.dropped["N"]
    assert "25017 Middlesex County, Massachusetts" in notes.dropped["N"]
    assert "02290 Yukon-Koyukuk Census Area, Alaska" in notes.dropped["S"]
    assert len(notes.consolidated) == CONSOLIDATED_COUNTIES
    assert "06075 San Francisco County, California" in notes.consolidated
    assert "36047 Kings County, New York" in notes.consolidated
    assert len(notes.overrides) == len(states_counties.OVERRIDES) == 1


def test_every_entry_has_its_code_population_and_a_line_naming_it(
    entries: list[PlaceEntry], opened: dict[str, files.OpenedFile], rules: countries.CountryRules
):
    naming = rules.naming
    for entry in entries:
        assert entry.code.scheme is IdentifierScheme.FIPS
        assert entry.code.value.isdigit()
        assert len(entry.code.value) in {2, 5}
        (population,) = entry.figures
        assert (population.name, population.year) == (MetricName.POPULATION, 2025)
        assert population.value > 0
        line = opened[entry.citations["place"].source].line(entry.citations["place"].line)
        assert entry.name in line
        figure_line = opened[population.citation.source].line(population.citation.line)
        assert str(population.value) in figure_line
        if entry.government is not None:
            # "State of Ohio" governs "Ohio"; "Cook County" governs itself; "Government of the
            # District of Columbia" carries its place's whole name.
            assert naming.core(entry.government) in (
                naming.core(entry.name),
                naming.key(entry.name),
            ) or naming.key(entry.name) in naming.key(entry.government), entry.name


def test_the_states_are_the_seeds_anchors(entries: list[PlaceEntry]):
    states = {entry.name: entry for entry in entries if entry.level == "state"}
    seeded = {name: government for name, government, _ in united_states.STATES}
    assert states.keys() == seeded.keys()
    for name, entry in states.items():
        assert entry.government == seeded[name], name
        assert (entry.parent, entry.parent_level) == ("United States", "country")
        assert len(entry.code.value) == 2
    assert states["District of Columbia"].code.value == "11"
    assert states["Puerto Rico"].code.value == "72"
    assert states["Puerto Rico"].citations["place"].source == census.PUERTO_RICO_POPULATION.name


def test_counties_sit_under_their_state_by_level(entries: list[PlaceEntry]):
    states = {entry.name for entry in entries if entry.level == "state"}
    for entry in entries:
        if entry.level != "state":
            assert entry.parent in states, entry.name
            assert entry.parent_level == "state"
            assert entry.code.value[:2] == next(
                state.code.value for state in entries if state.name == entry.parent
            )
    # Thirty counties are named Washington; Rhode Island's is no government.
    washingtons = [entry for entry in entries if entry.name == "Washington County"]
    assert len(washingtons) == 29
    assert len({entry.parent for entry in washingtons}) == 29


def test_the_places_that_show_the_rules(by_code: dict[str, PlaceEntry]):
    cook = by_code["17031"]
    assert (cook.name, cook.level, cook.parent, cook.government) == (
        "Cook County",
        "county",
        "Illinois",
        "Cook County",
    )
    assert by_code["22071"].name == "Orleans Parish"
    assert by_code["22071"].government is None
    assert by_code["02090"].government == "Fairbanks North Star Borough"
    assert by_code["02020"].government is None
    # Partially consolidated: the parish keeps its government beside the city's.
    assert by_code["22033"].government == "East Baton Rouge Parish"
    # Terrebonne is consolidated with Houma, whose city row is nonfunctioning: the parish is the
    # government.
    assert by_code["22109"].government == "Terrebonne Parish"
    # Promoted.
    honolulu = by_code["15003"]
    assert (honolulu.name, honolulu.level, honolulu.parent, honolulu.government) == (
        "Honolulu County",
        "municipality",
        "Hawaii",
        "City and County of Honolulu",
    )
    assert "15005" not in by_code
    assert "09110" not in by_code
    assert "51510" not in by_code


def test_puerto_ricos_municipios_are_municipalities_under_puerto_rico(
    entries: list[PlaceEntry], opened: dict[str, files.OpenedFile]
):
    municipios = [entry for entry in entries if entry.code.value.startswith("72")]
    assert len(municipios) == MUNICIPIOS + 1
    adjuntas = next(entry for entry in municipios if entry.code.value == "72001")
    assert (adjuntas.name, adjuntas.level, adjuntas.parent, adjuntas.parent_level) == (
        "Adjuntas",
        "municipality",
        "Puerto Rico",
        "state",
    )
    assert adjuntas.government == "Municipality of Adjuntas"
    assert [(alias.text, alias.language) for alias in adjuntas.aliases] == [
        ("Municipio de Adjuntas", "es")
    ]
    assert adjuntas.citations["place"].source == census.GAZETTEER_COUNTIES.name
    (population,) = adjuntas.figures
    assert population.citation.source == census.PUERTO_RICO_POPULATION.name
    assert population.value == 17994
    line = opened[census.PUERTO_RICO_POPULATION.name].line(population.citation.line)
    assert line.startswith(".Adjuntas Municipio, Puerto Rico")
    mayaguez = next(entry for entry in municipios if entry.code.value == "72097")
    assert mayaguez.name == "Mayagüez"
