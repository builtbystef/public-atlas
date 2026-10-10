"""The British Columbia places list: `entries()` on the cached files keeps every rule, the
counts are pinned, and a few places show the rules a count cannot."""

from collections.abc import Callable, Sequence

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.british_columbia import places as bc

# The 28 regional districts less the Northern Rockies, whose division holds only the regional
# municipality that replaced it.
REGIONS = 27
MUNICIPALITIES = 160
UNDER_THE_PROVINCE = 1
DROPPED = {"IRI": 423, "RDA": 160, "S-É": 3, "IGD": 2, "TWL": 1, "TAL": 1, "NL": 1}
CENSUS_ONLY = 2
RENAMED = 5
# Langley and North Vancouver, a city beside a township or district.
SIBLING_NAMESAKES = 2


@pytest.fixture(scope="module")
def opened(sources_of) -> dict[str, files.OpenedFile]:
    return sources_of(bc)


@pytest.fixture(scope="module")
def built(opened, rules: countries.CountryRules) -> tuple[list[PlaceEntry], bc.Notes]:
    return bc.build(opened, rules.naming)


@pytest.fixture(scope="module")
def entries(built) -> list[PlaceEntry]:
    return built[0]


@pytest.fixture(scope="module")
def regions(entries) -> list[PlaceEntry]:
    return [entry for entry in entries if entry.level == statcan.REGION]


@pytest.fixture(scope="module")
def municipalities(entries) -> list[PlaceEntry]:
    return [entry for entry in entries if entry.level == statcan.MUNICIPALITY]


@pytest.fixture(scope="module")
def by_code(entries) -> dict[str, PlaceEntry]:
    return {entry.code.value: entry for entry in entries}


def test_the_counts(entries, regions, municipalities, built, opened, rules):
    notes = built[1]
    assert len(bc.entries(opened, rules)) == len(entries)
    assert len(regions) == REGIONS
    assert len(municipalities) == MUNICIPALITIES
    assert sum(1 for entry in municipalities if entry.parent == bc.PROVINCE) == UNDER_THE_PROVINCE
    assert dict(notes.dropped) == DROPPED
    assert len(notes.census_only) == CENSUS_ONLY
    assert len(notes.renamed) == RENAMED
    assert notes.moved == []
    assert notes.untaken == ["Stikine Region (Unincorporated)"]
    assert all(entry.homepage is None for entry in entries)
    codes = [entry.code.value for entry in entries]
    assert len(set(codes)) == len(codes)


def test_every_place_has_its_code_population_and_the_layers_legal_name(
    entries, opened, rules: countries.CountryRules
):
    naming = rules.naming
    census = opened[statcan.POPULATION.name]
    for entry in entries:
        assert entry.code.scheme is IdentifierScheme.STATCAN_SGC
        assert entry.code.value.startswith(bc.PROVINCE_CODE)
        (population,) = entry.figures
        assert (population.name, population.year) == (MetricName.POPULATION, statcan.CENSUS_YEAR)
        line = census.line(entry.citations["place"].line)
        assert entry.code.value in line
        assert any(name in line for name in (entry.name, *(a.text for a in entry.aliases)))
        assert entry.government is not None
        source = bc.REGIONAL_DISTRICTS if entry.level == statcan.REGION else bc.MUNICIPALITIES
        assert entry.citations["government"].source == source.name
        assert entry.government in opened[source.name].line(entry.citations["government"].line)
        if entry.code.value in bc.OVERRIDES:
            # The layer spells the name otherwise (Hudsons Hope, 100 Mile House).
            continue
        core = naming.core(entry.government)
        # "Town of X" governs "X"; the layer may drop a period the census writes (Fort St James).
        assert core in (naming.core(entry.name), naming.key(entry.name)) or core in naming.forms(
            entry.name
        ), entry.name


def test_municipalities_sit_under_the_regional_district_the_layer_names(
    regions, municipalities, by_code
):
    names = {entry.name for entry in regions}
    assert all(entry.parent == bc.PROVINCE for entry in regions)
    for entry in municipalities:
        if entry.parent == bc.PROVINCE:
            assert entry.name == "Northern Rockies"
            assert entry.government == "Northern Rockies Regional Municipality"
        else:
            assert entry.parent in names, entry.name
            assert (entry.parent_level, entry.parent_parent) == (statcan.REGION, bc.PROVINCE)
            # The layer's regional district is the census division.
            assert by_code[entry.code.value[:4]].name == entry.parent


def test_the_places_that_show_the_rules(by_code):
    metro = by_code["5915"]
    assert (metro.name, metro.government) == (
        "Metro Vancouver",
        "Metro Vancouver Regional District",
    )
    assert [alias.text for alias in metro.aliases] == ["Greater Vancouver"]
    assert by_code["5927"].name == "qathet"
    assert by_code["5947"].name == "North Coast"
    assert by_code["5937"].government == "Regional District of North Okanagan"
    assert by_code["5915022"].government == "City of Vancouver"
    assert by_code["5915001"].government == "The Corporation of the Township of Langley"
    assert by_code["5915002"].government == "City of Langley"
    assert by_code["5915062"].government == "Bowen Island Municipality"
    assert by_code["5933045"].government == "Sun Peaks Mountain Resort Municipality"
    assert by_code["5931020"].government == "Resort Municipality of Whistler"
    assert by_code["5941005"].name == "100 Mile House"
    assert by_code["5947026"].name == "Daajing Giids"
    assert [alias.text for alias in by_code["5947026"].aliases] == ["Queen Charlotte"]
    assert by_code["5955025"].name == "Hudson's Hope"


def test_the_overrides_apply(entries):
    codes = {entry.code.value for entry in entries}
    assert set(bc.OVERRIDES) <= codes


def test_a_city_and_the_township_of_its_name_are_two_places(
    entries, sibling_namesakes: Callable[[Sequence[PlaceEntry]], int]
):
    assert sibling_namesakes(entries) == SIBLING_NAMESAKES
