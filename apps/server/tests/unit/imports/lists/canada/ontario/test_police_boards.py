"""The police boards list: `entries()` on the cached PAS pages keeps every rule, the counts
are pinned, and the table names loaded places at the levels the boards sit at."""

from collections.abc import Callable

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import InstitutionEntry, PlaceEntry
from public_atlas.modules.imports.lists.canada.ontario import police_boards
from public_atlas.modules.imports.lists.canada.ontario.communities import Location

from .conftest import open_sources

BOARDS = 43
LEGACY = 2
LINKS = BOARDS + LEGACY
REGIONAL = {"Durham", "Halton", "Niagara", "Peel", "Waterloo", "York"}


@pytest.fixture(scope="module")
def opened() -> dict[str, files.OpenedFile]:
    return open_sources(police_boards)


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


def test_every_board_cites_its_page_and_sits_at_one_loaded_place(
    entries: list[InstitutionEntry],
    opened: dict[str, files.OpenedFile],
    find_places: Callable[[str, str | None, str | None], list[PlaceEntry]],
):
    for entry in entries:
        assert entry.institution_type == "police_service"
        assert entry.name.endswith(" Police Service Board")
        assert entry.parent_institution is None
        assert entry.homepage is None
        citation = entry.citations["institution"]
        page = opened[citation.source]
        heading = page.line(citation.line)
        assert heading.startswith(police_boards.PREFIX)
        words = entry.name.removesuffix(" Police Service Board").removesuffix(" Regional")
        assert words.lower() in heading.lower(), (entry.name, heading)
        assert page.lines[page.lines.index("Background") + 1].startswith(police_boards.ACT)
        # Every place with its level and parent: other provinces load namesakes.
        assert entry.place_level is not None
        assert entry.place_parent is not None
        found = find_places(entry.place, entry.place_level, entry.place_parent)
        assert len(found) == 1, (entry.name, entry.place)
        assert found[0].parent == entry.place_parent
        assert entry.served_places
        for served in entry.served_places:
            assert served.level is not None
            assert served.parent is not None
            assert len(find_places(served.name, served.level, served.parent)) == 1, served


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
