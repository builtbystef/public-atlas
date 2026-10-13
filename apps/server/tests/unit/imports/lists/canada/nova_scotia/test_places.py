"""The Nova Scotia places list: the counts are pinned, the governments are the layer's legal
names, and a few places show the rules a count cannot. What every list's entries must satisfy
is checked by the contract test beside the lists."""

from collections import Counter
from typing import Any

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.nova_scotia import places as nova_scotia

pytestmark = pytest.mark.lists

MUNICIPALITIES = 49
KINDS = {"Town": 25, "Municipal District": 11, "Municipal County": 9, "Regional Municipality": 4}
COUNTY_MUNICIPALITIES = 9
DROPPED = {"IRI": 27}


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


@pytest.fixture(scope="module")
def loaded(loaded_places_of) -> Any:
    return loaded_places_of("CA", ("canada/nova_scotia/places",))


def test_the_counts(entries, built, opened):
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


def test_every_government_is_the_layers_legal_name_and_names_its_place(
    entries, opened, rules: countries.CountryRules
):
    naming = rules.naming
    layer = opened[nova_scotia.MUNICIPALITIES.name]
    for entry in entries:
        assert entry.parent_level == statcan.PROVINCE_LEVEL
        assert entry.government is not None, entry.name
        assert entry.government in layer.line(entry.citations["government"].line)
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


def test_a_district_and_a_town_of_one_name_are_two_places(loaded: Any) -> None:
    """A district and a town of one name (Digby, Lunenburg, Shelburne, Yarmouth), and a county
    municipality and a town (Antigonish, Pictou)."""
    assert [(pair.name, pair.government, pair.other_government) for pair in loaded.told_apart] == [
        ("Antigonish", "Municipality of the County of Antigonish", "Town of Antigonish"),
        ("Digby", "Municipality of the District of Digby", "Town of Digby"),
        ("Lunenburg", "Municipality of the District of Lunenburg", "Town of Lunenburg"),
        ("Pictou", "Municipality of the County of Pictou", "Town of Pictou"),
        ("Shelburne", "Municipality of the District of Shelburne", "Town of Shelburne"),
        ("Yarmouth", "Municipality of the District of Yarmouth", "Town of Yarmouth"),
    ]
