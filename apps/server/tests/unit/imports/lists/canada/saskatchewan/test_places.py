"""The Saskatchewan places list: `entries()` on the cached files keeps every rule, the counts
are pinned, and a few places show the rules a count cannot. The directory is a manual file:
without it in the cache the tests are skipped."""

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.saskatchewan import places as saskatchewan

# The census's 775 municipalities less the 17 villages restructured since and the two parts of
# cities loaded by Alberta and Manitoba, plus the one resort village the interim list codes.
CENSUS_MUNICIPALITIES = 775
RESTRUCTURED = 17
SHARED = 2
CREATED = 1
MUNICIPALITIES = CENSUS_MUNICIPALITIES - RESTRUCTURED - SHARED + CREATED
HOMEPAGES = 293
DROPPED = {"IRI": 172, "NO": 2, "CN": 1, "S-É": 1}
RENAMED = 2
# Lloydminster, loaded by Alberta, and the two resort villages the interim list does not code.
UNCODED = 3
DIRECTORY_ROWS = 761


@pytest.fixture(scope="module")
def opened(sources_of) -> dict[str, files.OpenedFile]:
    return sources_of(saskatchewan)


@pytest.fixture(scope="module")
def built(opened) -> tuple[list[PlaceEntry], saskatchewan.Notes]:
    return saskatchewan.build(opened)


@pytest.fixture(scope="module")
def entries(built) -> list[PlaceEntry]:
    return built[0]


@pytest.fixture(scope="module")
def by_code(entries) -> dict[str, PlaceEntry]:
    return {entry.code.value: entry for entry in entries}


def test_the_counts(entries, built, opened, rules):
    notes = built[1]
    assert len(saskatchewan.entries(opened, rules)) == len(entries)
    assert len(entries) == MUNICIPALITIES
    assert len(opened[saskatchewan.DIRECTORY.name].rows) == DIRECTORY_ROWS
    assert sum(1 for entry in entries if entry.homepage) == HOMEPAGES
    assert dict(notes.dropped) == DROPPED
    assert len(notes.restructured) == RESTRUCTURED
    assert len(notes.shared) == SHARED
    assert len(notes.created) == CREATED
    assert len(notes.uncoded) == UNCODED
    assert len(notes.renamed) == RENAMED
    district = "Northern Saskatchewan Administration District"
    assert notes.directory_dropped == [f"{district} ({district})"]
    codes = [entry.code.value for entry in entries]
    assert len(set(codes)) == len(codes)


def test_every_municipality_has_its_code_population_and_a_government_from_the_directory(
    entries, opened, rules: countries.CountryRules
):
    naming = rules.naming
    census = opened[statcan.POPULATION.name]
    directory = opened[saskatchewan.DIRECTORY.name]
    for entry in entries:
        assert (entry.level, entry.parent) == ("municipality", saskatchewan.PROVINCE)
        assert entry.code.scheme is IdentifierScheme.STATCAN_SGC
        assert entry.code.value.startswith(saskatchewan.PROVINCE_CODE)
        assert entry.government is not None
        assert naming.key(entry.name) in naming.key(entry.government), entry.name
        row = directory.line(entry.citations["government"].line)
        if entry.homepage is not None:
            host = entry.homepage.removeprefix("http://").removeprefix("https://").rstrip("/")
            assert host.lower() in row.lower(), entry.name
        if entry.citations["place"].source == statcan.INTERIM_CHANGES.name:
            # Incorporated since the census: coded by the interim list, no figure.
            assert entry.figures == ()
            assert entry.code.value in opened[statcan.INTERIM_CHANGES.name].line(
                entry.citations["place"].line
            )
            continue
        (population,) = entry.figures
        assert (population.name, population.year) == (MetricName.POPULATION, statcan.CENSUS_YEAR)
        line = census.line(entry.citations["place"].line)
        assert entry.code.value in line
        assert any(name in line for name in (entry.name, *(a.text for a in entry.aliases)))


def test_the_places_that_show_the_rules(by_code, built):
    assert by_code["4706027"].government == "City of Regina"
    assert by_code["4706027"].homepage == "https://www.regina.ca/"
    aberdeen = by_code["4715018"]
    assert (aberdeen.name, aberdeen.government) == (
        "Aberdeen No. 373",
        "Rural Municipality of Aberdeen No. 373",
    )
    assert by_code["4718041"].government == "Northern Town of La Ronge"
    assert by_code["4718042"].government == "Northern Village of Air Ronge"
    assert by_code["4717002"].government == "Resort Village of Cochin"
    katepwa = by_code["4706050"]
    assert (katepwa.name, katepwa.government) == (
        "District of Katepwa",
        "Resort Village of the District of Katepwa",
    )
    assert [alias.text for alias in katepwa.aliases] == ["Katepwa"]
    assert by_code["4715075"].government == "District of Lakeland No. 521"
    # The census's spelling where the directory only drops the accent.
    assert by_code["4701019"].name == "Roche Percée"
    assert by_code["4701019"].aliases == ()
    # Incorporated 2024-01-01, coded by the interim list.
    pasqua = by_code["4706043"]
    assert (pasqua.name, pasqua.government) == ("Pasqua Lake", "Resort Village of Pasqua Lake")
    assert pasqua.citations["place"].source == statcan.INTERIM_CHANGES.name
    # The parts of cities other provinces load.
    assert "4717029" not in by_code
    assert "4718052" not in by_code
    assert {line.split(" ", 1)[0] for line in built[1].restructured} == {
        code for code, fields in saskatchewan.OVERRIDES.items() if "dissolved" in fields
    }
