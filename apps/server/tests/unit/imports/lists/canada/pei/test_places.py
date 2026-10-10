"""The Prince Edward Island places list: `entries()` on the cached files keeps every rule, the
counts are pinned, and a few places show the rules a count cannot. The directory is a manual
file: without it in the cache the tests are skipped."""

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.pei import places as pei

# The census's 59 municipalities less the two dissolved since.
MUNICIPALITIES = 57
DISSOLVED = 2
HOMEPAGES = 53
DROPPED = {"FD": 35, "IRI": 4}
RENAMED = 3


@pytest.fixture(scope="module")
def opened(sources_of) -> dict[str, files.OpenedFile]:
    return sources_of(pei)


@pytest.fixture(scope="module")
def built(opened, rules: countries.CountryRules) -> tuple[list[PlaceEntry], pei.Notes]:
    return pei.build(opened, rules.naming)


@pytest.fixture(scope="module")
def entries(built) -> list[PlaceEntry]:
    return built[0]


@pytest.fixture(scope="module")
def by_code(entries) -> dict[str, PlaceEntry]:
    return {entry.code.value: entry for entry in entries}


def test_the_counts(entries, built, opened, rules):
    notes = built[1]
    assert len(pei.entries(opened, rules)) == len(entries)
    assert len(entries) == MUNICIPALITIES
    assert sum(1 for entry in entries if entry.homepage) == HOMEPAGES
    assert dict(notes.dropped) == DROPPED
    assert len(notes.dissolved) == DISSOLVED
    assert len(notes.renamed) == RENAMED
    codes = [entry.code.value for entry in entries]
    assert len(set(codes)) == len(codes)


def test_every_municipality_has_its_code_population_and_a_government_from_the_directory(
    entries, opened, rules: countries.CountryRules
):
    naming = rules.naming
    census = opened[statcan.POPULATION.name]
    directory = opened[pei.DIRECTORY.name]
    for entry in entries:
        assert (entry.level, entry.parent) == ("municipality", pei.PROVINCE)
        assert entry.code.scheme is IdentifierScheme.STATCAN_SGC
        assert entry.code.value.startswith(pei.PROVINCE_CODE)
        (population,) = entry.figures
        assert (population.name, population.year) == (MetricName.POPULATION, statcan.CENSUS_YEAR)
        line = census.line(entry.citations["place"].line)
        assert entry.code.value in line
        assert any(name in line for name in (entry.name, *(a.text for a in entry.aliases)))
        assert entry.government is not None
        core = naming.core(entry.government)
        # "Town of X" governs "X"; the layer may drop a period the census writes (Fort St James).
        assert core in (naming.core(entry.name), naming.key(entry.name)) or core in naming.forms(
            entry.name
        ), entry.name
        row = directory.line(entry.citations["government"].line)
        if entry.homepage is not None:
            assert entry.citations["homepage"] == entry.citations["government"]
            host = entry.homepage.removeprefix("http://").removeprefix("https://").rstrip("/")
            assert host.lower() in row.lower()


def test_the_places_that_show_the_rules(by_code, built):
    assert by_code["1102075"].government == "City of Charlottetown"
    assert by_code["1101036"].government == "Town of Souris"
    assert by_code["1102002"].government == "Rural Municipality of Belfast"
    resort = by_code["1102045"]
    assert resort.name == "Stanley Bridge, Hope River, Bayview, Cavendish and North Rustico"
    assert resort.government == f"Resort Municipality of {resort.name}"
    assert resort.homepage == "http://www.resortmunicipalitypei.com/"
    # The directory's spelling wins; the census's is an alias.
    peters = by_code["1101044"]
    assert (peters.name, [alias.text for alias in peters.aliases]) == (
        "St. Peter's Bay",
        ["St. Peters Bay"],
    )
    assert by_code["1103039"].name == "Lot 11 & Area"
    # Dissolved since the census: not loaded.
    assert "1102035" not in by_code
    assert "1103057" not in by_code
    assert {line.split(" ", 1)[0] for line in built[1].dissolved} == {"1102035", "1103057"}
    assert set(pei.OVERRIDES) == {"1102035", "1103057", "1101044", "1102045"}
