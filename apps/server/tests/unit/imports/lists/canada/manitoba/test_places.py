"""The Manitoba places list: the counts are pinned, the governments come from the directory's
headings, and a few places show the rules a count cannot. What every list's entries must
satisfy is checked by the contract test beside the lists. The directory is a PDF: the first
run parses it with Docling and keeps the pages beside the cache."""

from typing import Any

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.canada.manitoba import places as manitoba

pytestmark = [pytest.mark.lists, pytest.mark.parse]

# The census's 138 municipalities, the two parts of Mountain as one.
MUNICIPALITIES = 137
DIRECTORY_ENTRIES = 137
HOMEPAGES = 130
DROPPED = {"IRI": 88, "NO": 10, "S-É": 3}


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


@pytest.fixture(scope="module")
def loaded(loaded_places_of) -> Any:
    return loaded_places_of("CA", ("canada/manitoba/places",))


def test_the_counts(entries, built, opened):
    notes = built[1]
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


def test_every_government_comes_from_the_directorys_heading_for_its_place(
    entries, opened, rules: countries.CountryRules
):
    """The government is cited at the directory heading that names the place, and names the
    place itself; a website is cited at the "Website" line under that heading."""
    naming = rules.naming
    directory = opened[manitoba.DIRECTORY.name]
    for entry in entries:
        assert entry.government is not None, entry.name
        core = naming.core(entry.government)
        assert core in (naming.core(entry.name), naming.key(entry.name)) or core in naming.forms(
            entry.name
        ), entry.name
        heading = directory.line(entry.citations["government"].line)
        assert manitoba.key(entry.name) in manitoba.key(heading), entry.name
        if entry.homepage is not None:
            assert "ebsite" in directory.line(entry.citations["homepage"].line), entry.name


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


def test_the_rural_municipality_and_the_town_of_one_name_are_two_places(loaded: Any) -> None:
    """The rural municipality beside the town of Lac du Bonnet, Morris and Ste. Anne, and
    beside the city of Dauphin, Portage la Prairie and Thompson."""
    assert [(pair.name, pair.government, pair.other_government) for pair in loaded.told_apart] == [
        ("Dauphin", "Rural Municipality of Dauphin", "City of Dauphin"),
        ("Lac du Bonnet", "Rural Municipality of Lac du Bonnet", "Town of Lac du Bonnet"),
        ("Morris", "Rural Municipality of Morris", "Town of Morris"),
        (
            "Portage la Prairie",
            "Rural Municipality of Portage la Prairie",
            "City of Portage la Prairie",
        ),
        ("Ste. Anne", "Rural Municipality of Ste. Anne", "Town of Ste. Anne"),
        ("Thompson", "Rural Municipality of Thompson", "City of Thompson"),
    ]
