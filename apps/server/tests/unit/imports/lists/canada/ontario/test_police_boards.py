"""The police boards list: the counts are pinned, every board is read from its agency page
with its place and served places said whole, and a few boards show the rules a count cannot.
What every list's entries must satisfy is checked by the contract test beside the lists."""

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import InstitutionEntry
from public_atlas.modules.imports.lists.canada.ontario import police_boards
from public_atlas.modules.imports.lists.canada.ontario.communities import Location

pytestmark = pytest.mark.lists

BOARDS = 43
LEGACY = 2
LINKS = BOARDS + LEGACY
REGIONAL = {"Durham", "Halton", "Niagara", "Peel", "Waterloo", "York"}


@pytest.fixture(scope="module")
def opened(sources_of) -> dict[str, files.OpenedFile]:
    return sources_of(police_boards)


@pytest.fixture(scope="module")
def entries(
    opened: dict[str, files.OpenedFile], rules: countries.CountryRules
) -> list[InstitutionEntry]:
    return police_boards.entries(opened, rules)


@pytest.fixture(scope="module")
def by_id(entries: list[InstitutionEntry]) -> dict[str, InstitutionEntry]:
    return {
        entry.citations["institution"].source.removeprefix("pas_agency_"): entry
        for entry in entries
    }


def test_the_counts(entries: list[InstitutionEntry], opened: dict[str, files.OpenedFile]):
    assert len(entries) == BOARDS
    assert len(police_boards.BOARDS) == BOARDS
    assert len(police_boards.LEGACY) == LEGACY
    assert len(police_boards.SOURCES) == 1 + BOARDS
    links = police_boards.board_links(opened[police_boards.LIST.name])
    assert len(links) == LINKS
    assert all(title.startswith(police_boards.PREFIX) for title in links.values())
    assert len({entry.name for entry in entries}) == BOARDS
    assert {entry.place for entry in entries if entry.place_level == "region"} == REGIONAL


def test_every_board_is_read_from_its_agency_page_with_its_places_said_whole(
    entries: list[InstitutionEntry], opened: dict[str, files.OpenedFile]
):
    for entry in entries:
        assert entry.institution_type == "police_service"
        assert entry.name.endswith(" Police Service Board")
        assert entry.parent_institution is None
        assert entry.homepage is None
        citation = entry.citations["institution"]
        page = opened[citation.source]
        assert page.line(citation.line).startswith(police_boards.PREFIX)
        assert page.lines[page.lines.index("Background") + 1].startswith(police_boards.ACT)
        # Every place with its level and parent: other provinces load namesakes.
        assert entry.place_level is not None
        assert entry.place_parent is not None
        assert entry.served_places
        for served in entry.served_places:
            assert served.level is not None
            assert served.parent is not None


def test_the_boards_that_show_the_rules(by_id: dict[str, InstitutionEntry]):
    south_simcoe = by_id["53"]
    assert south_simcoe.name == "South Simcoe Police Service Board"
    assert (south_simcoe.place, south_simcoe.place_parent) == ("Innisfil", "Simcoe")
    assert [served.name for served in south_simcoe.served_places] == [
        "Bradford West Gwillimbury",
        "Innisfil",
    ]
    assert by_id["72"].name == "Durham Regional Police Service Board"
    assert by_id["137"].name == "Peel Police Service Board"
    assert by_id["190"].name == "Waterloo Regional Police Service Board"
    assert (by_id["190"].place, by_id["190"].place_level) == ("Waterloo", "region")
    assert by_id["110"].name == "LaSalle Police Service Board"
    hamilton = by_id["90"]
    assert (hamilton.place, hamilton.place_level, hamilton.place_parent) == (
        "Hamilton",
        "municipality",
        "Ontario",
    )
    assert (by_id["183"].place, by_id["183"].place_level) == ("Thunder Bay", "municipality")
    assert police_boards.municipality("Hamilton", "Ontario") == Location(
        "Hamilton", "municipality", "Ontario"
    )
    # The legacy entries are not loaded.
    assert "49" not in by_id
    assert "127" not in by_id
