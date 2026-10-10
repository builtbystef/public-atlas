"""The Manitoba places list: `entries()` on the cached files keeps every rule, the counts are
pinned, and a few places show the rules a count cannot. The directory is a PDF: the first run
parses it with Docling and keeps the pages beside the cache."""

from collections.abc import Callable, Sequence

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.manitoba import places as manitoba

# The census's 138 municipalities, the two parts of Mountain as one.
MUNICIPALITIES = 137
DIRECTORY_ENTRIES = 137
HOMEPAGES = 130
DROPPED = {"IRI": 88, "NO": 10, "S-É": 3}
# The rural municipality beside the town of Lac du Bonnet, Morris and Ste. Anne, and beside the
# city of Dauphin, Portage la Prairie and Thompson.
SIBLING_NAMESAKES = 6


@pytest.fixture(scope="module")
def opened(sources_of) -> dict[str, files.OpenedFile]:
    return sources_of(manitoba)


@pytest.fixture(scope="module")
def built(opened) -> tuple[list[PlaceEntry], manitoba.Notes]:
    return manitoba.build(opened)


@pytest.fixture(scope="module")
def entries(built) -> list[PlaceEntry]:
    return built[0]


@pytest.fixture(scope="module")
def by_code(entries) -> dict[str, PlaceEntry]:
    return {entry.code.value: entry for entry in entries}


def test_the_counts(entries, built, opened, rules):
    notes = built[1]
    assert len(manitoba.entries(opened, rules)) == len(entries)
    assert len(entries) == MUNICIPALITIES
    assert len(manitoba.read_entries(opened[manitoba.DIRECTORY.name])) == DIRECTORY_ENTRIES
    assert sum(1 for entry in entries if entry.homepage) == HOMEPAGES
    assert dict(notes.dropped) == DROPPED
    assert notes.untaken == []
    assert len(notes.without_website) == MUNICIPALITIES - HOMEPAGES
    assert len(notes.merged) == 1
    assert len(notes.renamed) == 2
    codes = [entry.code.value for entry in entries]
    assert len(set(codes)) == len(codes)


def test_every_municipality_has_its_code_population_and_a_government_from_the_directory(
    entries, opened, rules: countries.CountryRules
):
    naming = rules.naming
    census = opened[statcan.POPULATION.name]
    directory = opened[manitoba.DIRECTORY.name]
    for entry in entries:
        assert (entry.level, entry.parent) == ("municipality", manitoba.PROVINCE)
        assert entry.code.scheme is IdentifierScheme.STATCAN_SGC
        assert entry.code.value.startswith(manitoba.PROVINCE_CODE)
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
        heading = directory.line(entry.citations["government"].line)
        assert manitoba.key(entry.name) in manitoba.key(heading), entry.name
        if entry.homepage is not None:
            site = directory.line(entry.citations["homepage"].line)
            assert "ebsite" in site
            host = entry.homepage.removeprefix("http://").removeprefix("https://").rstrip("/")
            assert host.lower().removeprefix("www.") in site.lower(), entry.name


def test_the_places_that_show_the_rules(by_code, built):
    assert by_code["4611040"].government == "City of Winnipeg"
    assert by_code["4611040"].homepage == "http://www.winnipeg.ca/"
    assert by_code["4601071"].government == "Rural Municipality of Alexander"
    assert by_code["4601051"].government == "Local Government District of Pinawa"
    assert by_code["4602075"].government == "Rural Municipality of Ritchot"
    assert by_code["4605025"].government == "Municipality of Killarney - Turtle Mountain"
    assert by_code["4602069"].government == "Rural Municipality of Taché"
    # One city in two provinces: Manitoba's code, the two parts' population.
    flin_flon = by_code["4621064"]
    assert (flin_flon.name, flin_flon.government) == ("Flin Flon", "City of Flin Flon")
    assert flin_flon.figures[0].value == 4940 + 159
    roblin = by_code["4616048"]
    assert (roblin.name, roblin.government) == ("Roblin", "Municipality of Roblin")
    assert [alias.text for alias in roblin.aliases] == ["Hillsburg-Roblin-Shell River"]
    mountain = by_code["4620055"]
    assert mountain.government == "Rural Municipality of Mountain"
    assert mountain.figures[0].value == 980
    assert {alias.text for alias in mountain.aliases} == {"Mountain (North)", "Mountain (South)"}
    assert "4620032" not in by_code
    assert built[1].merged == ["4620032 Mountain (South) -> 4620055"]


def test_the_rural_municipality_and_the_town_of_one_name_are_two_places(
    entries, sibling_namesakes: Callable[[Sequence[PlaceEntry]], int]
):
    morris = sorted(entry.government for entry in entries if entry.name == "Morris")
    assert morris == ["Rural Municipality of Morris", "Town of Morris"]
    assert sibling_namesakes(entries) == SIBLING_NAMESAKES
