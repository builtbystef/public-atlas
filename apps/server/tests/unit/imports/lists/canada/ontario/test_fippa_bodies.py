"""The FIPPA bodies list: the counts are pinned, every body is named cleanly at a municipality
or a region with its homepage the origin of the directory's link, and the universities and
colleges match the ministry's own pages. What every list's entries must satisfy is checked by
the contract test beside the lists."""

from urllib.parse import urlsplit

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import InstitutionEntry
from public_atlas.modules.imports.lists.canada.ontario import fippa_bodies
from public_atlas.shared.text import name_key

pytestmark = pytest.mark.lists

HOSPITALS = 144
COLLEGES = 24
# 22 in the directory, less Royal Military College.
UNIVERSITIES = 21
# Every body but the three whose link is not its own site.
HOMEPAGES = HOSPITALS + COLLEGES + UNIVERSITIES - 3


@pytest.fixture(scope="module")
def opened(sources_of) -> dict[str, files.OpenedFile]:
    return sources_of(fippa_bodies)


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


def test_every_body_is_named_cleanly_at_a_municipality_or_a_region(
    entries: list[InstitutionEntry],
):
    for entry in entries:
        assert entry.place_level in ("municipality", "region"), entry.name
        assert entry.parent_institution is None
        assert entry.served_places == ()
        # No tag or trailing note from the directory's HTML.
        assert "<" not in entry.name
        assert not entry.name.endswith(")")


def test_every_homepage_is_the_origin_of_the_directorys_link(entries: list[InstitutionEntry]):
    for entry in entries:
        if entry.homepage is None:
            continue
        parts = urlsplit(entry.homepage)
        assert parts.path == "/"
        assert not parts.query
        assert entry.citations["homepage"] == entry.citations["institution"]


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
    """Each override's field is the entry's: a renamed body goes by the new name with the
    directory's as an alias, and a place or language given by hand is the entry's."""
    assert "Royal Military College" not in by_name
    tmu = by_name["Toronto Metropolitan University"]
    assert [alias.text for alias in tmu.aliases] == ["Ryerson University"]
    assert tmu.homepage == "https://www.ryerson.ca/"
    assert by_name["University of Toronto"].homepage is None
    assert by_name["Atikokan General Hospital"].homepage is None
    assert by_name["Lennox & Addington County General Hospital"].homepage is None
    for listed, fields in fippa_bodies.OVERRIDES.items():
        entry = by_name[str(fields.get("name", listed))]
        if "name" in fields:
            assert listed in [alias.text for alias in entry.aliases], listed
        for field in ("place", "language", "homepage"):
            if field in fields:
                assert getattr(entry, field) == fields[field], (listed, field)


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
