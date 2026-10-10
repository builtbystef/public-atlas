"""The Nova Scotia places list: `entries()` on the cached files keeps every rule, the counts
are pinned, and a few places show the rules a count cannot."""

from collections import Counter
from collections.abc import Callable, Sequence

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.nova_scotia import places as nova_scotia

MUNICIPALITIES = 49
KINDS = {"Town": 25, "Municipal District": 11, "Municipal County": 9, "Regional Municipality": 4}
COUNTY_MUNICIPALITIES = 9
DROPPED = {"IRI": 27}
# A district and a town of one name (Digby, Lunenburg, Shelburne, Yarmouth), and a county
# municipality and a town (Antigonish, Pictou).
SIBLING_NAMESAKES = 6


@pytest.fixture(scope="module")
def opened(sources_of) -> dict[str, files.OpenedFile]:
    return sources_of(nova_scotia)


@pytest.fixture(scope="module")
def built(opened) -> tuple[list[PlaceEntry], nova_scotia.Notes]:
    return nova_scotia.build(opened)


@pytest.fixture(scope="module")
def entries(built) -> list[PlaceEntry]:
    return built[0]


@pytest.fixture(scope="module")
def by_code(entries) -> dict[str, PlaceEntry]:
    return {entry.code.value: entry for entry in entries}


def test_the_counts(entries, built, opened, rules: countries.CountryRules):
    assert len(nova_scotia.entries(opened, rules)) == len(entries)
    assert len(entries) == MUNICIPALITIES
    rows = nova_scotia.read_rows(opened[nova_scotia.MUNICIPALITIES.name])
    assert Counter(row.kind for row in rows) == KINDS
    assert sum(1 for entry in entries if len(entry.code.value) == statcan.DIVISION_CODE_LENGTH) == (
        COUNTY_MUNICIPALITIES
    )
    assert dict(built[1].dropped) == DROPPED
    assert len(built[1].counties) == COUNTY_MUNICIPALITIES
    codes = [entry.code.value for entry in entries]
    assert len(set(codes)) == len(codes)
    assert all(entry.homepage is None for entry in entries)


def test_every_municipality_sits_under_the_province_with_its_code_population_and_legal_name(
    entries, opened, rules: countries.CountryRules
):
    naming = rules.naming
    census = opened[statcan.POPULATION.name]
    layer = opened[nova_scotia.MUNICIPALITIES.name]
    for entry in entries:
        assert (entry.level, entry.parent, entry.parent_level) == (
            "municipality",
            nova_scotia.PROVINCE,
            statcan.PROVINCE_LEVEL,
        )
        assert entry.code.scheme is IdentifierScheme.STATCAN_SGC
        assert entry.code.value.startswith(nova_scotia.PROVINCE_CODE)
        (population,) = entry.figures
        assert (population.name, population.year) == (MetricName.POPULATION, statcan.CENSUS_YEAR)
        assert population.value > 0
        line = census.line(entry.citations["place"].line)
        assert entry.code.value in line
        assert entry.name in line
        assert entry.government is not None
        legal = layer.line(entry.citations["government"].line)
        assert entry.government in legal
        assert naming.key(entry.name) in naming.key(entry.government)


def test_the_county_municipalities_take_the_division_and_the_sum_of_their_parts(by_code, opened):
    kings = by_code["1207"]
    assert (kings.name, kings.government) == ("Kings", "Municipality of the County of Kings")
    # Kings, Subd. A to D: 22,355 + 11,951 + 8,348 + 5,264.
    assert kings.figures[0].value == 47918
    assert "Kings" in opened[statcan.POPULATION.name].line(kings.citations["place"].line)
    queens = by_code["1204010"]
    assert queens.government == "Region of Queens Municipality"
    assert by_code["1208003"].government == "West Hants Regional Municipality"
    assert by_code["1209034"].government == "Halifax Regional Municipality"


def test_a_district_and_a_town_of_one_name_are_two_places(
    entries, sibling_namesakes: Callable[[Sequence[PlaceEntry]], int]
):
    digby = sorted(entry.government for entry in entries if entry.name == "Digby")
    assert digby == ["Municipality of the District of Digby", "Town of Digby"]
    assert sibling_namesakes(entries) == SIBLING_NAMESAKES
