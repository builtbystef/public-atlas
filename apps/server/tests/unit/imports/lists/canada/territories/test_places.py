"""The territories' places list: `entries()` on the cached files keeps every rule, the counts
are pinned, and a few places show the rules a count cannot. The directories are manual files:
without every one in the cache the tests are skipped."""

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.territories import places as territories

BY_TERRITORY = {"Yukon": 8, "Northwest Territories": 24, "Nunavut": 25}
HOMEPAGES = {"Yukon": 8, "Northwest Territories": 11, "Nunavut": 18}
DESIGNATED_AUTHORITIES = 9
RENAMED = 4
DROPPED = {"NO": 14, "SÉ": 13, "SET": 12, "SG": 4, "S-É": 2, "HAM": 2, "IRI": 2, "TL": 1}
SOURCES = 2 + 1 + 33 + 25


@pytest.fixture(scope="module")
def opened(sources_of) -> dict[str, files.OpenedFile]:
    return sources_of(territories)


@pytest.fixture(scope="module")
def built(opened) -> tuple[list[PlaceEntry], territories.Notes]:
    return territories.build(opened)


@pytest.fixture(scope="module")
def entries(built) -> list[PlaceEntry]:
    return built[0]


@pytest.fixture(scope="module")
def by_code(entries) -> dict[str, PlaceEntry]:
    return {entry.code.value: entry for entry in entries}


def test_the_counts(entries, built, opened, rules):
    notes = built[1]
    assert len(territories.SOURCES) == SOURCES
    assert len(territories.entries(opened, rules)) == len(entries)
    by_territory = dict.fromkeys(BY_TERRITORY, 0)
    homepages = dict.fromkeys(BY_TERRITORY, 0)
    for entry in entries:
        by_territory[entry.parent] += 1
        homepages[entry.parent] += entry.homepage is not None
    assert by_territory == BY_TERRITORY
    assert homepages == HOMEPAGES
    assert dict(notes.dropped) == DROPPED
    assert len(notes.designated_authorities) == DESIGNATED_AUTHORITIES
    assert len(notes.renamed) == RENAMED
    codes = [entry.code.value for entry in entries]
    assert len(set(codes)) == len(codes)


def test_every_municipality_has_its_code_population_and_a_government_from_its_directory(
    entries, opened, rules: countries.CountryRules
):
    naming = rules.naming
    census = opened[statcan.POPULATION.name]
    for entry in entries:
        assert entry.level == "municipality"
        assert entry.parent_level == statcan.PROVINCE_LEVEL
        assert entry.code.scheme is IdentifierScheme.STATCAN_SGC
        (population,) = entry.figures
        assert (population.name, population.year) == (MetricName.POPULATION, statcan.CENSUS_YEAR)
        line = census.line(entry.citations["place"].line)
        assert entry.code.value in line
        assert any(name in line for name in (entry.name, *(a.text for a in entry.aliases)))
        assert entry.government is not None
        cited = opened[entry.citations["government"].source].line(
            entry.citations["government"].line
        )
        # A page that never names the body gets a government composed from the census type,
        # cited at the page's heading, which is the community's name.
        assert entry.government in cited or entry.government.endswith(f" of {cited}")
        if entry.homepage is not None:
            site = opened[entry.citations["homepage"].source].line(entry.citations["homepage"].line)
            host = entry.homepage.removeprefix("http://").removeprefix("https://").rstrip("/")
            assert host.lower().removeprefix("www.") in site.lower().replace(
                "https//", "https://"
            ) or ("ebsite" in site), entry.name
        if entry.parent != "Northwest Territories":
            assert naming.key(entry.name) in naming.key(entry.government), entry.name


def test_the_places_that_show_the_rules(by_code):
    assert by_code["6001029"].government == "City of Dawson"
    assert by_code["6001012"].government == "Village of Carmacks"
    assert by_code["6001012"].homepage == "http://www.carmacks.ca/"
    assert by_code["6106023"].government == "City of Yellowknife"
    behchoko = by_code["6103031"]
    assert behchoko.government == "Community Government of Behchokǫ̀"
    assert [alias.text for alias in behchoko.aliases] == ["Behchokǫ̀"]
    assert by_code["6102009"].government == "Charter Community of K\u2019asho Got\u2019ine"
    assert by_code["6204003"].government == "City of Iqaluit"
    assert by_code["6204003"].homepage == "https://www.iqaluit.ca/"
    assert by_code["6204015"].government == "Municipality of Clyde River"
    assert by_code["6204015"].homepage == "https://clyderiver.ca/"
    assert by_code["6205015"].government == "Hamlet of Arviat"
    arctic_bay = by_code["6204018"]  # its page names no body and links no website
    assert (arctic_bay.government, arctic_bay.homepage) == ("Hamlet of Arctic Bay", None)
    assert arctic_bay.citations["government"].line == 55
    kinngait = by_code["6204007"]
    assert (kinngait.name, kinngait.government) == ("Kinngait", "Hamlet of Kinngait")
    assert [alias.text for alias in kinngait.aliases] == ["Cape Dorset"]
    assert by_code["6204011"].name == "Sanirajak"
    assert by_code["6204022"].name == "Resolute Bay"
