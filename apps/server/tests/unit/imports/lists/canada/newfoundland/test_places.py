"""The Newfoundland and Labrador places list: `entries()` on the cached census files keeps
every rule and the counts are pinned."""

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.newfoundland import places as newfoundland

MUNICIPALITIES = 277
CITIES = 3
INUIT_COMMUNITY_GOVERNMENTS = 5
DROPPED = {"SNO": 92, "IRI": 3}
QUALIFIED = 6


@pytest.fixture(scope="module")
def opened(sources_of) -> dict[str, files.OpenedFile]:
    return sources_of(newfoundland)


@pytest.fixture(scope="module")
def built(opened) -> tuple[list[PlaceEntry], newfoundland.Notes]:
    return newfoundland.build(opened)


@pytest.fixture(scope="module")
def entries(built) -> list[PlaceEntry]:
    return built[0]


@pytest.fixture(scope="module")
def by_code(entries) -> dict[str, PlaceEntry]:
    return {entry.code.value: entry for entry in entries}


def test_the_counts(entries, built, opened, rules):
    notes = built[1]
    assert len(newfoundland.entries(opened, rules)) == len(entries)
    assert len(entries) == MUNICIPALITIES
    assert sum(1 for entry in entries if entry.government.startswith("City of")) == CITIES
    assert sum(
        1 for entry in entries if entry.government.endswith("Inuit Community Government")
    ) == (INUIT_COMMUNITY_GOVERNMENTS)
    assert dict(notes.dropped) == DROPPED
    assert len(notes.qualified) == QUALIFIED
    assert len(notes.overrides) == INUIT_COMMUNITY_GOVERNMENTS
    assert all(entry.homepage is None for entry in entries)
    codes = [entry.code.value for entry in entries]
    assert len(set(codes)) == len(codes)


def test_every_municipality_has_its_code_population_and_a_composed_government(
    entries, opened, rules: countries.CountryRules
):
    naming = rules.naming
    census = opened[statcan.POPULATION.name]
    for entry in entries:
        assert (entry.level, entry.parent) == ("municipality", newfoundland.PROVINCE)
        assert entry.code.scheme is IdentifierScheme.STATCAN_SGC
        assert entry.code.value.startswith(newfoundland.PROVINCE_CODE)
        (population,) = entry.figures
        assert (population.name, population.year) == (MetricName.POPULATION, statcan.CENSUS_YEAR)
        line = census.line(entry.citations["place"].line)
        assert entry.code.value in line
        assert entry.name in line
        assert "government" not in entry.citations
        bare = newfoundland.bare_name(entry.name)
        assert naming.key(bare) in naming.key(entry.government), entry.name


def test_the_two_seal_coves_stay_two_places(entries, sibling_namesakes):
    seal_coves = [entry for entry in entries if entry.name.startswith("Seal Cove")]
    assert [entry.name for entry in seal_coves] == [
        "Seal Cove (Fortune Bay)",
        "Seal Cove (White Bay)",
    ]
    assert all(entry.aliases == () for entry in seal_coves)
    assert sibling_namesakes(entries) == 0


def test_the_places_that_show_the_rules(by_code):
    assert by_code["1001519"].government == "City of St. John's"
    assert by_code["1011035"].government == "Nain Inuit Community Government"
    charlottetown = by_code["1010013"]
    assert (charlottetown.name, charlottetown.government) == (
        "Charlottetown (Labrador)",
        "Town of Charlottetown",
    )
    assert [alias.text for alias in charlottetown.aliases] == ["Charlottetown"]
    assert by_code["1009011"].government == "Town of Woody Point"
