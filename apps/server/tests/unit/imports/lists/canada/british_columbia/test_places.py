"""The British Columbia places list: the counts are pinned, the governments are the layers'
legal names, municipalities sit under the regional district the layer names, and a few places
show the rules a count cannot. What every list's entries must satisfy is checked by the
contract test beside the lists."""

from typing import Any

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.british_columbia import places as bc

pytestmark = pytest.mark.lists

# The 28 regional districts less the Northern Rockies, whose division holds only the regional
# municipality that replaced it.
REGIONS = 27
MUNICIPALITIES = 160
UNDER_THE_PROVINCE = 1
DROPPED = {"IRI": 423, "RDA": 160, "S-É": 3, "IGD": 2, "TWL": 1, "TAL": 1, "NL": 1}
CENSUS_ONLY = 2
RENAMED = 5


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


@pytest.fixture(scope="module")
def loaded(loaded_places_of) -> Any:
    return loaded_places_of("CA", ("canada/british_columbia/places",))


def test_the_counts(entries, regions, municipalities, built):
    notes = built[1]
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


def test_every_government_is_the_layers_legal_name_of_its_place(
    entries, opened, rules: countries.CountryRules
):
    """A regional district's government is cited in the regional districts layer, a
    municipality's in the municipalities layer, and names the place, apart from the two the
    layer spells otherwise (Hudsons Hope, 100 Mile House)."""
    naming = rules.naming
    for entry in entries:
        assert entry.government is not None, entry.name
        source = bc.REGIONAL_DISTRICTS if entry.level == statcan.REGION else bc.MUNICIPALITIES
        assert entry.citations["government"].source == source.name
        assert entry.government in opened[source.name].line(entry.citations["government"].line)
        if entry.code.value in bc.OVERRIDES:
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


def test_the_overrides_apply(by_code):
    """Each override's name or legal name is the entry's; the census's name is its alias."""
    assert by_code["5941005"].name == "100 Mile House"
    assert by_code["5941005"].government == "District of 100 Mile House"
    assert by_code["5955025"].name == "Hudson's Hope"
    assert by_code["5955025"].government == "District of Hudsons Hope"
    assert by_code["5947026"].name == "Daajing Giids"
    assert by_code["5947026"].government == "Village of Daajing Giids"
    assert by_code["5915"].name == "Metro Vancouver"
    assert by_code["5947"].name == "North Coast"
    for code, fields in bc.OVERRIDES.items():
        entry = by_code[code]
        assert entry.name == fields.get("name", entry.name)
        assert entry.government == fields.get("legal_name", entry.government)
        if "name" in fields:
            assert entry.aliases, entry.name


def test_a_city_and_the_township_of_its_name_are_two_places(loaded: Any) -> None:
    """Langley and North Vancouver: a city beside a township or a district municipality."""
    assert loaded.told_apart == [
        ("Langley", "The Corporation of the Township of Langley", "Langley", "City of Langley"),
        (
            "North Vancouver",
            "The Corporation of the District of North Vancouver",
            "North Vancouver",
            "City of North Vancouver",
        ),
    ]
