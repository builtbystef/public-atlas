"""The provincial agencies list: `entries()` on the cached spreadsheet keeps every rule, the
counts are pinned, and every agency sits under a ministry the list also gives."""

import re
from urllib.parse import urlsplit

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import InstitutionEntry
from public_atlas.modules.imports.lists.canada.ontario import agencies

from .conftest import open_sources

MINISTRIES = 25
CROWN_CORPORATIONS = 32
AGENCIES = 105
# Four rows give no address, ten a page title, and four only the directory's own page.
HOMEPAGES = 119


@pytest.fixture(scope="module")
def opened() -> dict[str, files.OpenedFile]:
    return open_sources(agencies)


@pytest.fixture(scope="module")
def entries(
    opened: dict[str, files.OpenedFile], rules: countries.CountryRules
) -> list[InstitutionEntry]:
    return agencies.entries(opened, rules)


@pytest.fixture(scope="module")
def by_name(entries: list[InstitutionEntry]) -> dict[str, InstitutionEntry]:
    return {entry.name: entry for entry in entries}


def _of_type(entries: list[InstitutionEntry], institution_type: str) -> list[InstitutionEntry]:
    return [entry for entry in entries if entry.institution_type == institution_type]


def test_the_counts(entries: list[InstitutionEntry]):
    assert len(_of_type(entries, "ministry")) == MINISTRIES
    assert len(_of_type(entries, "crown_corporation")) == CROWN_CORPORATIONS
    assert len(_of_type(entries, "agency")) == AGENCIES
    assert len(entries) == MINISTRIES + CROWN_CORPORATIONS + AGENCIES
    assert sum(1 for entry in entries if entry.homepage) == HOMEPAGES
    names = [entry.name for entry in entries]
    assert len(set(names)) == len(names)
    # Ministries first, so the loader has the parents before the agencies.
    assert [entry.institution_type for entry in entries[:MINISTRIES]] == ["ministry"] * MINISTRIES


def test_every_ministry_is_named_as_one_and_sits_under_ontario(entries: list[InstitutionEntry]):
    # The Canada seed's name pattern for a ministry.
    pattern = r"^(Ministry of |Ministère d)"
    for entry in _of_type(entries, "ministry"):
        assert entry.place == "Ontario"
        assert entry.place_level == "province_territory"
        assert entry.parent_institution is None
        assert entry.homepage is None
        assert re.match(pattern, entry.name) or entry.name == "Treasury Board Secretariat"
        (french,) = entry.aliases
        assert french.language == "fr"
        assert french.text.startswith(("Ministère", "Ministére", "ministère", "Secrétariat"))


def test_every_agency_cites_its_row_and_sits_under_a_listed_ministry(
    entries: list[InstitutionEntry], opened: dict[str, files.OpenedFile]
):
    sheet = opened[agencies.AGENCIES.name]
    ministries = {entry.name for entry in _of_type(entries, "ministry")}
    for entry in entries:
        if entry.institution_type == "ministry":
            continue
        assert entry.place == "Ontario"
        assert entry.parent_institution in ministries, entry.name
        citation = entry.citations["institution"]
        assert citation.source == agencies.AGENCIES.name
        line = sheet.line(citation.line)
        assert entry.name in line
        assert (
            entry.parent_institution.removeprefix("Ministry of the ").removeprefix("Ministry of ")
            in line
        )
        assert any(alias.language == "fr" for alias in entry.aliases), entry.name
        if entry.homepage is not None:
            parts = urlsplit(entry.homepage)
            assert parts.scheme in ("http", "https")
            assert parts.netloc in line.lower()
            assert "pas.gov.on.ca" not in parts.netloc
            assert entry.citations["homepage"] == citation


def test_the_rows_that_show_the_rules(by_name: dict[str, InstitutionEntry]):
    lcbo = by_name["Liquor Control Board of Ontario"]
    assert lcbo.institution_type == "crown_corporation"
    assert lcbo.parent_institution == "Ministry of Finance"
    assert lcbo.homepage == "http://www.lcbo.com/"
    assert by_name["Metrolinx"].homepage == "http://www.metrolinx.com/en/default.aspx"
    assert by_name["Ontario Securities Commission"].institution_type == "agency"
    assert by_name["Ontario Human Rights Commission"].parent_institution == (
        "Ministry of the Attorney General"
    )
    assert by_name["Committee to Evaluate Drugs"].homepage is None
    assert by_name["Ontario Internal Audit Committee"].parent_institution == (
        "Treasury Board Secretariat"
    )
    assert by_name["Ontario Internal Audit Committee"].homepage is None
    assert by_name["Ontario Provincial Conservation Agency"].homepage is None
    assert by_name["Building Code Commission"].homepage is None
    assert by_name["Accessibility Standards Advisory Council"].homepage == (
        "http://www.ontario.ca/page/accessibility-legislative-reviews-committees-and-councils"
    )
    tvo = by_name["Ontario Educational Communications Authority"]
    assert [(alias.text, alias.language, alias.is_acronym) for alias in tvo.aliases] == [
        ("TVO", "en", True),
        ("Office de la télécommunication éducative de l'Ontario", "fr", False),
    ]
    centre = by_name["Centennial Centre of Science and Technology"]
    assert [(alias.text, alias.language) for alias in centre.aliases] == [
        ("Ontario Science Centre", "en"),
        ("Centre centennial des sciences et de la technologie", "fr"),
        ("centre des sciences de l'Ontario", "fr"),
    ]
    assert "Ontario Special Education Tribunal (English)" in by_name
    french_tribunal = by_name["Ontario Special Education Tribunal (French)"]
    assert [alias.text for alias in french_tribunal.aliases] == [
        "Tribunal de l\u2019éducation spécialisée de l\u2019Ontario (français)"
    ]
    assert "Grievance Settlement Board (Crown Employees)" in by_name
    islands = by_name["Toronto Islands Residential Community Trust Corporation"]
    assert islands.homepage == "https://torontoisland.org/"
    assert by_name["Ministry of Health"].aliases[0].text == "Ministère de la Santé"
    assert by_name["Ministry of Environment, Conservation and Parks"].aliases[0].text == (
        "Ministère de l\u2019Environnement, de la Protection de la nature et des Parcs"
    )
