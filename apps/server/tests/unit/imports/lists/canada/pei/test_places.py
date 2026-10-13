"""The Prince Edward Island places list: the counts are pinned, the governments and websites
come from the directory's row, and a few places show the rules a count cannot. What every
list's entries must satisfy is checked by the contract test beside the lists. The directory is
a manual file: without it in the cache the tests are skipped."""

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.canada.pei import places as pei

pytestmark = pytest.mark.lists

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


def test_the_counts(entries, built):
    notes = built[1]
    assert len(entries) == MUNICIPALITIES
    assert sum(1 for entry in entries if entry.homepage) == HOMEPAGES
    assert dict(notes.dropped) == DROPPED
    assert len(notes.dissolved) == DISSOLVED
    assert len(notes.renamed) == RENAMED
    codes = [entry.code.value for entry in entries]
    assert len(set(codes)) == len(codes)


def test_every_government_and_website_come_from_one_directory_row(
    entries, rules: countries.CountryRules
):
    naming = rules.naming
    for entry in entries:
        assert entry.government is not None, entry.name
        core = naming.core(entry.government)
        assert core in (naming.core(entry.name), naming.key(entry.name)) or core in naming.forms(
            entry.name
        ), entry.name
        assert entry.citations["government"].source == pei.DIRECTORY.name
        if entry.homepage is not None:
            assert entry.citations["homepage"] == entry.citations["government"]


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
