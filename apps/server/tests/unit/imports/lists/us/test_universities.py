"""The universities list: `entries()` on the cached files keeps every rule, the counts per
type and per place level are pinned, and a few campuses show the rules a count cannot."""

from collections import Counter

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import IdentifierScheme
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import InstitutionEntry
from public_atlas.modules.imports.lists.us import universities

ENTRIES = 1738
TYPED = {"university": 889, "college": 849}
PLACED = {"county": 1647, "municipality": 65, "state": 26}
PRIVATE = 4092
INACTIVE = 5
LESS_THAN_TWO_YEAR = 229
# American Samoa, Guam, the Northern Mariana Islands, the Virgin Islands, Micronesia, Palau
# and the Marshall Islands.
NO_STATE = 8
ALIASES = 1366
WEBSITES = 1738
STATES = 52


@pytest.fixture(scope="module")
def opened(universities_files: dict[str, files.OpenedFile]) -> dict[str, files.OpenedFile]:
    return universities_files


@pytest.fixture(scope="module")
def built(
    opened: dict[str, files.OpenedFile], rules: countries.CountryRules
) -> tuple[list[InstitutionEntry], universities.Notes]:
    return universities.build(opened, rules)


@pytest.fixture(scope="module")
def entries(
    built: tuple[list[InstitutionEntry], universities.Notes],
) -> list[InstitutionEntry]:
    return built[0]


@pytest.fixture(scope="module")
def notes(built: tuple[list[InstitutionEntry], universities.Notes]) -> universities.Notes:
    return built[1]


@pytest.fixture(scope="module")
def by_name(entries: list[InstitutionEntry]) -> dict[str, InstitutionEntry]:
    return {entry.name: entry for entry in entries}


def test_the_counts(
    entries: list[InstitutionEntry],
    notes: universities.Notes,
    opened: dict[str, files.OpenedFile],
    rules: countries.CountryRules,
):
    assert len(universities.entries(opened, rules)) == ENTRIES
    assert len(entries) == ENTRIES
    assert dict(notes.typed) == TYPED
    assert Counter(entry.institution_type for entry in entries) == TYPED
    assert dict(notes.placed) == PLACED
    assert Counter(entry.place_level for entry in entries) == PLACED
    assert notes.private == PRIVATE
    assert notes.inactive == INACTIVE
    assert notes.less_than_two_year == LESS_THAN_TWO_YEAR
    assert len(notes.no_state) == NO_STATE
    assert notes.aliases == ALIASES
    assert sum(len(entry.aliases) for entry in entries) == ALIASES
    assert notes.websites == WEBSITES
    assert sum(1 for entry in entries if entry.homepage) == WEBSITES
    ids = [entry.codes[0].value for entry in entries]
    assert len(set(ids)) == len(ids)
    states = {
        entry.place if entry.place_level == "state" else entry.place_parent for entry in entries
    }
    assert len(states) == STATES


def test_every_entry_cites_the_row_that_names_it_and_sits_at_a_place(
    entries: list[InstitutionEntry], opened: dict[str, files.OpenedFile]
):
    directory = opened[universities.DIRECTORY.name]
    for entry in entries:
        citation = entry.citations["institution"]
        assert citation.source == universities.DIRECTORY.name
        # The directory writes a few names with two spaces inside ("Clayton  State").
        line = " ".join(directory.line(citation.line).split())
        assert entry.name in line
        (code,) = entry.codes
        assert code.scheme is IdentifierScheme.IPEDS
        assert line.startswith(code.value)
        assert entry.place_level in PLACED
        assert (entry.place_parent is None) == (entry.place_level == "state")
        for alias in entry.aliases:
            assert len(alias.text) <= universities.ALIAS_LENGTH
        if entry.homepage is not None:
            assert entry.citations["homepage"] == citation
            assert entry.homepage.startswith(("http://", "https://"))


def test_the_campuses_that_show_the_rules(by_name: dict[str, InstitutionEntry]):
    michigan = by_name["University of Michigan-Ann Arbor"]
    assert (michigan.institution_type, michigan.place, michigan.place_level) == (
        "university",
        "Washtenaw County",
        "county",
    )
    assert michigan.place_parent == "Michigan"
    assert michigan.homepage == "https://umich.edu/"
    assert "U of M" in [alias.text for alias in michigan.aliases]
    college = by_name["Washtenaw Community College"]
    assert (college.institution_type, college.place) == ("college", "Washtenaw County")
    # A system office is a body of its own, at the level of its campuses.
    assert by_name["University of Alabama System Office"].institution_type == "university"
    # Connecticut's planning regions are no places, and Storrs is no municipality: the state.
    assert by_name["University of Connecticut"].place == "Connecticut"
    # An independent city is the place of its campus.
    assert (
        by_name["Virginia Commonwealth University"].place,
        by_name["Virginia Commonwealth University"].place_level,
    ) == ("Richmond", "municipality")
    assert by_name["University of the District of Columbia"].place == "District of Columbia"
    assert by_name["University of Puerto Rico-Mayaguez"].place == "Puerto Rico"
    assert "University of Guam" not in by_name
    assert universities.aliases_of("AUM||Auburn University at Montgomery|Auburn Montgomery") == (
        universities.AliasEntry(text="AUM", is_acronym=True),
        universities.AliasEntry(text="Auburn University at Montgomery"),
        universities.AliasEntry(text="Auburn Montgomery"),
    )
    assert universities.aliases_of("UAH  University of Alabama Huntsville")[0].text == "UAH"
    assert universities.aliases_of("x" * 301) == ()
