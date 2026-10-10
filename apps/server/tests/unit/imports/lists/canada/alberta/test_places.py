"""The Alberta places list: `entries()` on the cached files keeps every rule, the counts are
pinned, and a few places and bodies show the rules a count cannot. The export is a manual
file: without it in the cache the tests are skipped."""

from collections.abc import Callable, Sequence

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import InstitutionEntry, PlaceEntry
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.alberta import places as alberta

# The census's 326 municipalities and 8 improvement districts, less the 6 dissolved since.
MUNICIPALITIES = 328
SPECIAL_AREAS = 3
DISSOLVED = 6
HOMEPAGES = 328
DROPPED = {"IRI": 83, "S-É": 3}
COMMISSIONS = {
    "public_utility": 64,
    "fire_service": 5,
    "transit_agency": 1,
    "airport_authority": 1,
    "other": 4,
}
EXPORT_DROPPED = {"Local Government Association": 9, "Metis Settlement": 8}
# The Town of Taber and the Municipal District of Taber.
SIBLING_NAMESAKES = 1


@pytest.fixture(scope="module")
def opened(sources_of) -> dict[str, files.OpenedFile]:
    return sources_of(alberta)


@pytest.fixture(scope="module")
def built(opened) -> tuple[list[PlaceEntry | InstitutionEntry], alberta.Notes]:
    return alberta.build(opened)


@pytest.fixture(scope="module")
def places(built) -> list[PlaceEntry]:
    return [entry for entry in built[0] if isinstance(entry, PlaceEntry)]


@pytest.fixture(scope="module")
def institutions(built) -> list[InstitutionEntry]:
    return [entry for entry in built[0] if isinstance(entry, InstitutionEntry)]


@pytest.fixture(scope="module")
def by_code(places) -> dict[str, PlaceEntry]:
    return {entry.code.value: entry for entry in places}


def test_the_counts(built, places, institutions, opened, rules):
    notes = built[1]
    assert len(alberta.entries(opened, rules)) == len(built[0])
    assert len(places) == MUNICIPALITIES + SPECIAL_AREAS
    assert sum(1 for entry in places if entry.government is None) == SPECIAL_AREAS
    assert sum(1 for entry in places if entry.homepage) == HOMEPAGES
    assert dict(notes.dropped) == DROPPED
    assert len(notes.dissolved) == DISSOLVED
    assert notes.composed == ["4813012 Alberta Beach -> Village of Alberta Beach"]
    assert dict(notes.commissions) == COMMISSIONS
    assert dict(notes.export_dropped) == EXPORT_DROPPED
    assert notes.untaken == ["Town of Diamond Valley (Town)"]
    assert len(institutions) == 1 + sum(COMMISSIONS.values())
    codes = [entry.code.value for entry in places]
    assert len(set(codes)) == len(codes)


def test_every_place_has_its_code_population_and_the_exports_legal_name(
    places, opened, rules: countries.CountryRules
):
    naming = rules.naming
    census = opened[statcan.POPULATION.name]
    export = opened[alberta.CONTACTS.name]
    for entry in places:
        assert (entry.level, entry.parent) == ("municipality", alberta.PROVINCE)
        assert entry.code.scheme is IdentifierScheme.STATCAN_SGC
        assert entry.code.value.startswith(alberta.PROVINCE_CODE)
        (population,) = entry.figures
        assert (population.name, population.year) == (MetricName.POPULATION, statcan.CENSUS_YEAR)
        line = census.line(entry.citations["place"].line)
        assert entry.code.value in line
        assert entry.name in line
        if entry.government is None:
            assert entry.name.startswith("Special Area")
            continue
        row = export.line(entry.citations["government"].line)
        # The export's legal name, or the kind and the export's bare name (Alberta Beach).
        assert entry.government in row or entry.government.endswith(f" of {row.split(' | ')[0]}")
        assert alberta.key(entry.government) == alberta.key(entry.name), entry.name
        assert naming.key(entry.name).split(" no ")[0].split(" ")[0] in naming.key(entry.government)
        if entry.homepage is not None:
            host = entry.homepage.removeprefix("http://").removeprefix("https://").rstrip("/")
            assert host.lower() in row.lower(), entry.name


def test_the_places_that_show_the_rules(by_code):
    assert by_code["4806016"].government == "City of Calgary"
    assert by_code["4819006"].government == "County of Grande Prairie No. 1"
    assert by_code["4803018"].government == "Municipal District of Willow Creek No. 26"
    assert by_code["4816037"].government == "Regional Municipality of Wood Buffalo"
    assert by_code["4811052"].government == "Strathcona County"
    assert by_code["4815032"].government == "Improvement District No. 09 (Banff)"
    assert by_code["4815013"].government == "Kananaskis Improvement District"
    assert by_code["4813012"].government == "Village of Alberta Beach"
    # One city in two provinces: Alberta's code, the two parts' population.
    lloydminster = by_code["4810039"]
    assert lloydminster.government == "City of Lloydminster"
    assert lloydminster.figures[0].value == 19739 + 11843
    assert lloydminster.homepage == "http://www.lloydminster.ca/"
    # Dissolved since the census.
    for code in alberta.OVERRIDES:
        assert code not in by_code


def test_the_special_areas_board_and_the_commissions(institutions, places):
    board = next(entry for entry in institutions if entry.name == alberta.SPECIAL_AREAS_BOARD)
    assert board.institution_type == "regional_government"
    assert (board.place, board.place_level) == (alberta.PROVINCE, statcan.PROVINCE_LEVEL)
    assert [served.name for served in board.served_places] == [
        "Special Area No. 2",
        "Special Area No. 3",
        "Special Area No. 4",
    ]
    assert {served.name for served in board.served_places} <= {
        entry.name for entry in places if entry.government is None
    }
    assert board.homepage == "http://www.specialareas.ab.ca/"
    commissions = [entry for entry in institutions if entry is not board]
    assert all(entry.place == alberta.PROVINCE for entry in commissions)
    assert all(
        (entry.suggested_type == alberta.COMMISSION) == (entry.institution_type == "other")
        for entry in commissions
    )
    names = {entry.name: entry.institution_type for entry in commissions}
    assert names["Aqua 7 Regional Water Commission"] == "public_utility"
    assert names["Beaver Emergency Services Commission"] == "fire_service"
    assert names["Bow Valley Regional Transit Services Commission"] == "transit_agency"
    assert names["Slave Lake Airport Services Commission"] == "airport_authority"
    assert names["Capital Region Assessment Services Commission"] == "other"
    assert len(names) == len(commissions)


def test_a_town_and_the_municipal_district_of_its_name_are_two_places(
    places, sibling_namesakes: Callable[[Sequence[PlaceEntry]], int]
):
    with_government = [entry for entry in places if entry.government is not None]
    assert sibling_namesakes(with_government) == SIBLING_NAMESAKES
