"""The Saskatchewan places list: the counts are pinned, a place incorporated since the census
is coded by the interim list with no figure, and a few places show the rules a count cannot.
What every list's entries must satisfy is checked by the contract test beside the lists. The
directory is a manual file: without it in the cache the tests are skipped."""

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import MetricName
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.saskatchewan import places as saskatchewan

pytestmark = pytest.mark.lists

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


def test_the_counts(entries, built, opened):
    notes = built[1]
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


def test_a_place_the_census_counts_has_its_figure_and_one_incorporated_since_has_none(
    entries, rules: countries.CountryRules
):
    naming = rules.naming
    interim = 0
    for entry in entries:
        assert entry.government is not None, entry.name
        assert naming.key(entry.name) in naming.key(entry.government), entry.name
        assert entry.citations["government"].source == saskatchewan.DIRECTORY.name
        if entry.citations["place"].source == statcan.INTERIM_CHANGES.name:
            assert entry.figures == ()
            interim += 1
        else:
            assert entry.citations["place"].source == statcan.POPULATION.name
            assert [(figure.name, figure.year) for figure in entry.figures] == [
                (MetricName.POPULATION, statcan.CENSUS_YEAR)
            ]
    assert interim == CREATED


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
