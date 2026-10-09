"""The FIPPA bodies list: `entries()` on the cached directory keeps every rule, the counts are
pinned, and the universities and colleges match the ministry's own pages."""

from collections.abc import Callable
from urllib.parse import urlsplit

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import InstitutionEntry
from public_atlas.modules.imports.lists.canada.ontario import fippa_bodies
from public_atlas.shared.text import name_key

from .conftest import open_sources

HOSPITALS = 144
COLLEGES = 24
# 22 in the directory, less Royal Military College.
UNIVERSITIES = 21
# Every body but the three whose link is not its own site.
HOMEPAGES = HOSPITALS + COLLEGES + UNIVERSITIES - 3


@pytest.fixture(scope="module")
def opened() -> dict[str, files.OpenedFile]:
    return open_sources(fippa_bodies)


@pytest.fixture(scope="module")
def entries(
    opened: dict[str, files.OpenedFile], rules: countries.CountryRules
) -> list[InstitutionEntry]:
    return fippa_bodies.entries(opened, rules)


@pytest.fixture(scope="module")
def by_name(entries: list[InstitutionEntry]) -> dict[str, InstitutionEntry]:
    return {entry.name: entry for entry in entries}


def _of_type(entries: list[InstitutionEntry], institution_type: str) -> list[InstitutionEntry]:
    return [entry for entry in entries if entry.institution_type == institution_type]


def test_the_counts(entries: list[InstitutionEntry]):
    assert len(_of_type(entries, "hospital")) == HOSPITALS
    assert len(_of_type(entries, "college")) == COLLEGES
    assert len(_of_type(entries, "university")) == UNIVERSITIES
    assert len(entries) == HOSPITALS + COLLEGES + UNIVERSITIES
    assert sum(1 for entry in entries if entry.homepage) == HOMEPAGES
    names = [entry.name for entry in entries]
    assert len(set(names)) == len(names)
    assert [entry.institution_type for entry in entries] == sorted(
        (entry.institution_type for entry in entries),
        key=list(fippa_bodies.TYPES.values()).index,
    )


def test_every_entry_cites_the_line_that_names_it_and_sits_in_a_loaded_place(
    entries: list[InstitutionEntry],
    opened: dict[str, files.OpenedFile],
    is_loaded_place: Callable[[str], bool],
):
    directory = opened[fippa_bodies.DIRECTORY.name]
    for entry in entries:
        citation = entry.citations["institution"]
        assert citation.source == fippa_bodies.DIRECTORY.name
        line = fippa_bodies.as_text(directory.line(citation.line))
        names = [entry.name, *(alias.text for alias in entry.aliases)]
        assert any(name in line for name in names), entry.name
        assert is_loaded_place(entry.place), (entry.name, entry.place)
        assert entry.place_level in ("municipality", "region")
        assert entry.parent_institution is None
        assert entry.served_places == ()
        assert "<" not in entry.name
        assert not entry.name.endswith(")")


def test_every_homepage_is_the_origin_of_the_directorys_link(
    entries: list[InstitutionEntry], opened: dict[str, files.OpenedFile]
):
    directory = opened[fippa_bodies.DIRECTORY.name]
    for entry in entries:
        if entry.homepage is None:
            continue
        parts = urlsplit(entry.homepage)
        assert parts.scheme in ("http", "https")
        assert parts.path == "/"
        assert not parts.query
        citation = entry.citations["homepage"]
        assert citation == entry.citations["institution"]
        assert parts.netloc in directory.line(citation.line).lower()


def test_the_names_and_notes(by_name: dict[str, InstitutionEntry]):
    assert by_name["St. Clair College of Applied Arts and Technology"].place == "Windsor"
    stegh = by_name["St. Thomas Elgin General Hospital"]
    assert [(alias.text, alias.is_acronym) for alias in stegh.aliases] == [("STEGH", True)]
    assert stegh.place == "St. Thomas"
    hsn = by_name["Health Sciences North/Horizon Santé-Nord"]
    assert [alias.text for alias in hsn.aliases] == [
        "Hôpital régional de Sudbury Regional Hospital"
    ]
    assert hsn.place == "Greater Sudbury"
    assert by_name["Sydenham District Hospital"].aliases == ()
    assert by_name["Sydenham District Hospital"].place == "Chatham-Kent"
    assert by_name["Hôpital Notre-Dame Hospital"].place == "Hearst"
    assert by_name["The Royal"].homepage == "https://www.theroyal.ca/"
    assert by_name["Alexandra Hospital"].homepage == "https://www.alexandrahospital.on.ca/"
    assert by_name["Alexandra Hospital"].place == "Ingersoll"
    assert by_name["Collège Boréal"].language == "fr"
    weneebayko = by_name["Weneebayko Area Health Authority"]
    assert (weneebayko.place, weneebayko.place_level) == ("Cochrane", "region")
    lady_minto = by_name["Lady Minto Hospital"]
    assert (lady_minto.place, lady_minto.place_level) == ("Cochrane", "municipality")
    hamilton = by_name["Hamilton Health Sciences Corporation"]
    assert (hamilton.place, hamilton.place_parent) == ("Hamilton", "Ontario")


def test_the_overrides_apply(by_name: dict[str, InstitutionEntry]):
    assert "Royal Military College" not in by_name
    tmu = by_name["Toronto Metropolitan University"]
    assert [alias.text for alias in tmu.aliases] == ["Ryerson University"]
    assert tmu.homepage == "https://www.ryerson.ca/"
    assert by_name["Seneca Polytechnic"].place == "Toronto"
    assert by_name["Wilfrid Laurier University"].place == "Waterloo"
    assert by_name["York University"].place == "Toronto"
    assert by_name["George Brown College"].place == "Toronto"
    assert by_name["Renfrew Victoria Hospital"].place == "Renfrew"
    assert by_name["University of Toronto"].homepage is None
    assert by_name["Atikokan General Hospital"].homepage is None
    assert by_name["Lennox & Addington County General Hospital"].homepage is None
    for name in fippa_bodies.OVERRIDES:
        assert name in by_name or any(
            alias.text == name for entry in by_name.values() for alias in entry.aliases
        ), name


def test_the_universities_and_colleges_match_the_ministrys_pages(entries: list[InstitutionEntry]):
    page = {name_key(name) for name in fippa_bodies.UNIVERSITIES_PAGE}
    page.remove(name_key("Royal Military College"))
    assert len(page) == UNIVERSITIES + len(fippa_bodies.UNIVERSITIES_NOT_IN_DIRECTORY) - len(
        fippa_bodies.UNIVERSITIES_ONLY_IN_DIRECTORY
    )
    universities = {name_key(entry.name) for entry in _of_type(entries, "university")}
    assert universities - page == {
        name_key(name) for name in fippa_bodies.UNIVERSITIES_ONLY_IN_DIRECTORY
    }
    assert page - universities == {
        name_key(name) for name in fippa_bodies.UNIVERSITIES_NOT_IN_DIRECTORY
    }

    assert len(fippa_bodies.COLLEGES_PAGE) == COLLEGES
    page_keys = [name_key(name) for name in fippa_bodies.COLLEGES_PAGE]
    for entry in _of_type(entries, "college"):
        key = name_key(entry.name)
        matches = [p for p in page_keys if p == key or p.startswith(f"{key} ")]
        assert len(matches) == 1, entry.name
