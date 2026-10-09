"""The school boards list: `entries()` on the cached contact list keeps every rule and the
counts are pinned."""

from collections.abc import Callable
from urllib.parse import urlsplit

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import InstitutionEntry
from public_atlas.modules.imports.lists.canada.ontario import school_boards

from .conftest import open_sources

DISTRICT_BOARDS = 72
# 13 rows, less the ministry's unit and Grandview's second address.
SCHOOL_AUTHORITIES = 11
FRENCH = 13


@pytest.fixture(scope="module")
def opened() -> dict[str, files.OpenedFile]:
    return open_sources(school_boards)


@pytest.fixture(scope="module")
def entries(
    opened: dict[str, files.OpenedFile], rules: countries.CountryRules
) -> list[InstitutionEntry]:
    return school_boards.entries(opened, rules)


@pytest.fixture(scope="module")
def by_name(entries: list[InstitutionEntry]) -> dict[str, InstitutionEntry]:
    return {entry.name: entry for entry in entries}


def test_the_counts(entries: list[InstitutionEntry]):
    authorities = [entry for entry in entries if school_boards.is_school_authority(entry)]
    assert len(entries) == DISTRICT_BOARDS + SCHOOL_AUTHORITIES
    assert len(authorities) == SCHOOL_AUTHORITIES
    assert entries[DISTRICT_BOARDS:] == authorities
    assert sum(1 for entry in entries if entry.language == "fr") == FRENCH
    assert all(entry.homepage for entry in entries)
    names = [entry.name for entry in entries]
    assert len(set(names)) == len(names)


def test_every_entry_cites_its_row_and_sits_in_a_loaded_place(
    entries: list[InstitutionEntry],
    opened: dict[str, files.OpenedFile],
    is_loaded_place: Callable[[str], bool],
):
    contacts = opened[school_boards.CONTACTS.name]
    for entry in entries:
        assert entry.institution_type == "school_board"
        citation = entry.citations["institution"]
        assert citation.source == school_boards.CONTACTS.name
        line = contacts.line(citation.line)
        assert entry.name in line
        assert is_loaded_place(entry.place), (entry.name, entry.place)
        assert entry.homepage is not None
        parts = urlsplit(entry.homepage)
        assert parts.scheme in ("http", "https")
        assert parts.netloc in line.lower()
        assert entry.citations["homepage"] == citation
        assert len(entry.aliases) <= 1
        if entry.aliases:
            assert entry.aliases[0].text in school_boards.AUTHORITY_KINDS.values()


def test_the_rows_that_show_the_rules(by_name: dict[str, InstitutionEntry]):
    assert "Provincial and Demonstration Schools" not in by_name
    grandview = by_name["Grandview School Authority"]
    assert grandview.place == "Ajax"
    assert [alias.text for alias in grandview.aliases] == ["Hospital school authority"]
    assert by_name["Toronto District School Board"].place == "Toronto"
    assert by_name["Toronto District School Board"].aliases == ()
    assert by_name["Ottawa Catholic School Board"].place == "Ottawa"
    assert by_name["Simcoe County District School Board"].place == "Springwater"
    assert by_name["Rainbow District School Board"].place == "Greater Sudbury"
    assert by_name["Conseil scolaire Viamonde"].language == "fr"
    assert by_name["Conseil scolaire Viamonde"].place == "Toronto"
    assert by_name["Conseil scolaire catholique Providence"].homepage == (
        "http://www.cscprovidence.ca/"
    )
    assert by_name["Halton Catholic District School Board"].homepage == "http://hcdsb.org/"
    moose = by_name["Moose Factory Island District School Area Board"]
    assert (moose.place, moose.place_level, moose.place_parent) == ("Cochrane", "region", "Ontario")
    hamilton = by_name["Hamilton-Wentworth District School Board"]
    assert (hamilton.place, hamilton.place_level, hamilton.place_parent) == (
        "Hamilton",
        "municipality",
        "Ontario",
    )
    thunder_bay = by_name["Thunder Bay Catholic District School Board"]
    assert (thunder_bay.place, thunder_bay.place_level) == ("Thunder Bay", "municipality")
    assert [alias.text for alias in moose.aliases] == ["District school area board"]
    assert [alias.text for alias in by_name["Consortium Centre Jules-Léger"].aliases] == [
        "School authority consortium"
    ]
