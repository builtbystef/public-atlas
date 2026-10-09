"""The service managers list: `entries()` on the cached list keeps every rule, the counts are
pinned, every board sits at its district and every served place is a loaded municipality."""

from collections.abc import Callable
from urllib.parse import urlsplit

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import InstitutionEntry, PlaceEntry
from public_atlas.modules.imports.lists.canada.ontario import service_managers

from .conftest import open_sources

ROWS = 425
MANAGERS = 47
BOARDS = 10
MUNICIPAL_MANAGERS = MANAGERS - BOARDS
# The boards' rows, less the ten for unincorporated territory and the one for Wawa's old name.
SERVED_PLACES = 143
# Served municipalities named like their district or like a township elsewhere: the level the
# entry gives tells them apart.
NAMESAKES = frozenset(
    {
        "Town of Cochrane",
        "City of Kenora",
        "Township of Nipissing",
        "Town of Parry Sound",
        "Town of Rainy River",
        "City of Thunder Bay",
    }
)


@pytest.fixture(scope="module")
def opened() -> dict[str, files.OpenedFile]:
    return open_sources(service_managers)


@pytest.fixture(scope="module")
def entries(
    opened: dict[str, files.OpenedFile], rules: countries.CountryRules
) -> list[InstitutionEntry]:
    return service_managers.entries(opened, rules)


@pytest.fixture(scope="module")
def managers(opened: dict[str, files.OpenedFile]) -> list[service_managers.Manager]:
    return service_managers.read_managers(opened[service_managers.LIST.name])


@pytest.fixture(scope="module")
def by_name(entries: list[InstitutionEntry]) -> dict[str, InstitutionEntry]:
    return {entry.name: entry for entry in entries}


def test_the_counts(
    entries: list[InstitutionEntry],
    managers: list[service_managers.Manager],
    opened: dict[str, files.OpenedFile],
):
    assert len(opened[service_managers.LIST.name].rows) == ROWS
    assert len(managers) == MANAGERS
    assert sum(1 for manager in managers if manager.is_board) == BOARDS
    assert len(entries) == BOARDS
    assert sum(len(entry.served_places) for entry in entries) == SERVED_PLACES
    assert all(entry.homepage for entry in entries)
    assert set(service_managers.DISTRICTS) == {entry.name for entry in entries}


def test_a_municipal_service_manager_is_a_loaded_government(
    managers: list[service_managers.Manager],
    find_places: Callable[[str, str | None, str | None], list[PlaceEntry]],
):
    for manager in managers:
        if manager.is_board:
            continue
        assert find_places(manager.name, None, None), manager.name


def test_every_board_cites_its_row_sits_at_its_district_and_serves_loaded_places(
    entries: list[InstitutionEntry],
    opened: dict[str, files.OpenedFile],
    find_places: Callable[[str, str | None, str | None], list[PlaceEntry]],
):
    listed = opened[service_managers.LIST.name]
    ambiguous: set[str] = set()
    for entry in entries:
        assert entry.institution_type == "municipal_corporation"
        assert entry.place_level == "region"
        assert entry.place_parent == "Ontario"
        (district,) = find_places(entry.place, entry.place_level, entry.place_parent)
        assert district.government is None, entry.place
        assert entry.parent_institution is None
        citation = entry.citations["institution"]
        assert citation.source == service_managers.LIST.name
        line = listed.line(citation.line)
        assert entry.name in service_managers.clean_name(line)
        assert entry.homepage is not None
        parts = urlsplit(entry.homepage)
        assert parts.scheme in ("http", "https")
        assert parts.netloc in line.lower()
        assert entry.citations["homepage"] == citation
        for served in entry.served_places:
            assert served.level == "municipality"
            assert served.parent is None
            assert "unincorporated" not in served.name.casefold()
            assert "&" not in served.name
            if len(find_places(served.name, None, None)) > 1:
                ambiguous.add(served.name)
            assert len(find_places(served.name, served.level, served.parent)) == 1, (
                entry.name,
                served.name,
            )
    assert ambiguous == NAMESAKES


def _names(entry: InstitutionEntry) -> tuple[str, ...]:
    return tuple(served.name for served in entry.served_places)


def test_the_rows_that_show_the_rules(by_name: dict[str, InstitutionEntry]):
    sault = by_name["District of Sault Ste. Marie Social Services Administration Board"]
    assert sault.place == "Algoma"
    assert _names(sault) == ("City of Sault Ste. Marie", "Township of Prince")
    assert sault.homepage == "https://socialservices-ssmd.ca/housing/"
    algoma = by_name["Algoma District Services Administration Board"]
    assert "Township of Michipicoten" not in _names(algoma)
    assert "Municipality of Wawa" in _names(algoma)
    assert "Tarbutt" in _names(algoma)
    assert "Macdonald, Meredith and Aberdeen Additional" in " ".join(_names(algoma))
    assert len(algoma.served_places) == 20
    kenora = by_name["Kenora District Services Board"]
    assert "Sioux Narrows-Nestor Falls" in _names(kenora)
    assert "Township of Sioux Narrows\u2013Nester Falls" not in _names(kenora)
    cochrane = by_name["District of Cochrane Social Service Administration Board"]
    assert "Mattice-Val Côté" in _names(cochrane)
    manitoulin = by_name["Manitoulin-Sudbury District Services Board"]
    assert manitoulin.place == "Sudbury"
    assert "Tehkummah" in _names(manitoulin)
    assert "St.-Charles" in _names(manitoulin)
    assert "Sables-Spanish Rivers" in _names(manitoulin)
    assert manitoulin.homepage == "http://www.msdsb.net/"
    for cell in service_managers.MEMBERS:
        assert cell not in {
            served.name for entry in by_name.values() for served in entry.served_places
        }
