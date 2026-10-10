"""The federal list: `entries()` on the cached inventory keeps every rule, the counts are
pinned, and a few bodies show the rules a count cannot."""

from collections import Counter

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import InstitutionEntry
from public_atlas.modules.imports.lists.canada import federal

from .conftest import open_sources

ROWS = 332
ENTRIES = 277
TYPED = {
    "department": 22,
    "agency": 100,
    "crown_corporation": 45,
    "legislature": 2,
    "public_authority": 41,
    "airport_authority": 21,
    "port_authority": 18,
    "other": 28,
}
STRUCTURES = {
    "Ministerial Departments": 22,
    "Departmental Agencies": 52,
    "Service Agencies": 3,
    "Special Operating Agencies": 17,
    "Departmental Corporations": 17,
    "Agents Of Parliament": 6,
    "Crown Corporations": 45,
    "Shared-Governance Corporations": 80,
    "International Organizations": 16,
    "Parliamentary Entities": 7,
    "Joint Enterprises": 2,
    "Other Organizations": 10,
}
INACTIVE = {"d": 31, "t": 24}
PORTFOLIOS = 27
HEADED_PORTFOLIOS = 25
WITH_PARENT = 240
WEBSITES = 253
ALIASES = 186
ACRONYMS = 117
# Abbreviations two bodies share, given to neither.
SHARED_ABBREVIATIONS = ["HC"]


@pytest.fixture(scope="module")
def opened() -> dict[str, files.OpenedFile]:
    return open_sources(federal)


@pytest.fixture(scope="module")
def built(
    opened: dict[str, files.OpenedFile], rules: countries.CountryRules
) -> tuple[list[InstitutionEntry], federal.Notes]:
    return federal.build(opened, rules)


@pytest.fixture(scope="module")
def entries(built: tuple[list[InstitutionEntry], federal.Notes]) -> list[InstitutionEntry]:
    return built[0]


@pytest.fixture(scope="module")
def notes(built: tuple[list[InstitutionEntry], federal.Notes]) -> federal.Notes:
    return built[1]


@pytest.fixture(scope="module")
def by_name(entries: list[InstitutionEntry]) -> dict[str, InstitutionEntry]:
    return {entry.name: entry for entry in entries}


def test_the_counts(
    entries: list[InstitutionEntry],
    notes: federal.Notes,
    opened: dict[str, files.OpenedFile],
    rules: countries.CountryRules,
):
    assert len(federal.read_organizations(opened[federal.INVENTORY.name])) == ROWS
    assert len(federal.entries(opened, rules)) == ENTRIES
    assert len(entries) == ENTRIES
    assert dict(notes.typed) == TYPED
    assert Counter(entry.institution_type for entry in entries) == TYPED
    assert dict(notes.structures) == STRUCTURES
    assert dict(notes.inactive) == INACTIVE
    assert len(notes.heads) == PORTFOLIOS
    assert sum(1 for head in notes.heads.values() if head is not None) == HEADED_PORTFOLIOS
    assert notes.with_parent == WITH_PARENT
    assert sum(1 for entry in entries if entry.parent_institution) == WITH_PARENT
    assert notes.websites == WEBSITES
    assert sum(1 for entry in entries if entry.homepage) == WEBSITES
    assert sum(len(entry.aliases) for entry in entries) == ALIASES
    assert sum(1 for entry in entries for alias in entry.aliases if alias.is_acronym) == ACRONYMS
    assert notes.shared_abbreviations == SHARED_ABBREVIATIONS
    # No two bodies share a name or an alias: the loader would read the second as the first.
    texts = [alias.text for entry in entries for alias in entry.aliases] + [e.name for e in entries]
    assert len(set(texts)) == len(texts)


def test_every_entry_cites_the_row_that_names_it_and_sits_under_canada(
    entries: list[InstitutionEntry], opened: dict[str, files.OpenedFile]
):
    inventory = opened[federal.INVENTORY.name]
    for entry in entries:
        citation = entry.citations["institution"]
        assert citation.source == federal.INVENTORY.name
        line = inventory.line(citation.line)
        assert entry.name in line
        assert " | a | " in line
        assert (entry.place, entry.place_level) == (federal.PLACE, federal.PLACE_LEVEL)
        assert entry.codes == ()
        assert (entry.suggested_type is not None) == (entry.institution_type == federal.OTHER)
        if entry.homepage is not None:
            assert entry.citations["homepage"] == citation
            assert entry.homepage.startswith(("http://", "https://"))


def test_the_heads_of_the_portfolios_are_loaded_before_the_bodies_under_them(
    entries: list[InstitutionEntry], by_name: dict[str, InstitutionEntry], notes: federal.Notes
):
    """The loader finds a parent by name among the bodies already at the place."""
    heads = {head for head in notes.heads.values() if head is not None}
    seen: set[str] = set()
    for entry in entries:
        if entry.parent_institution is not None:
            assert entry.parent_institution in heads
            assert entry.parent_institution in seen, entry.name
            assert entry.parent_institution in by_name
        else:
            assert entry.name in heads or entry.name in (
                "House of Commons",
                "Senate",
                "Library of Parliament",
                "Office of the Conflict of Interest and Ethics Commissioner",
                "Senate Ethics Officer",
                "Office of the Parliamentary Budget Officer",
                "Parliamentary Protective Service",
                "Communication Canada",
                "Commissioner of Canada Election",
                "Canada Investment and Savings",
                "Staff of the Non-Public Funds, Canadian Forces",
                "Statistics Survey Operations",
            ), entry.name
        seen.add(entry.name)
    for head in heads:
        assert by_name[head].parent_institution is None


def test_the_bodies_that_show_the_rules(by_name: dict[str, InstitutionEntry]):
    agriculture = by_name["Department of Agriculture and Agri-Food"]
    assert agriculture.institution_type == "department"
    assert agriculture.parent_institution is None
    assert [(alias.text, alias.is_acronym) for alias in agriculture.aliases] == [
        ("Agriculture and Agri-Food Canada", False),
        ("AAFC", True),
    ]
    assert agriculture.homepage == "http://www.agr.gc.ca/"
    grain = by_name["Canadian Grain Commission"]
    assert (grain.institution_type, grain.parent_institution) == (
        "agency",
        "Department of Agriculture and Agri-Food",
    )
    # A portfolio with two ministerial departments is headed by the one the hand table names.
    prairies = by_name["Department of Western Economic Diversification"]
    assert (prairies.institution_type, prairies.parent_institution) == (
        "department",
        "Department of Industry",
    )
    assert by_name["Department of Industry"].parent_institution is None
    # A portfolio with no ministerial department is headed by the body the hand table names.
    assert by_name["Office of the Chief Electoral Officer"].parent_institution == (
        "Privy Council Office"
    )
    assert by_name["Privy Council Office"].parent_institution is None
    assert by_name["Canada Revenue Agency"].parent_institution is None
    assert by_name["Canada Infrastructure Bank"].parent_institution == (
        "Department of Housing, Infrastructure and Communities"
    )
    bank = by_name["Bank of Canada"]
    assert (bank.institution_type, bank.parent_institution) == (
        "crown_corporation",
        "Department of Finance",
    )
    # The shared abbreviation goes to neither body; Parliament's entities have no parent.
    commons = by_name["House of Commons"]
    assert (commons.institution_type, commons.suggested_type) == ("legislature", None)
    assert commons.aliases == ()
    assert commons.parent_institution is None
    assert by_name["Senate"].institution_type == "legislature"
    assert by_name["Library of Parliament"].institution_type == "agency"
    assert by_name["Library of Parliament"].parent_institution is None
    # A shared-governance corporation is typed by what its name says it runs.
    assert by_name["Greater Toronto Airports Authority"].institution_type == "airport_authority"
    assert by_name["Aéroports de Montréal"].institution_type == "airport_authority"
    assert by_name["Vancouver Fraser Port Authority"].institution_type == "port_authority"
    assert by_name["NAV CANADA"].institution_type == "public_authority"
    assert by_name["NAV CANADA"].suggested_type is None
    assert by_name["Buffalo and Fort Erie Public Bridge Authority"].institution_type == (
        "public_authority"
    )
    assert by_name["International Monetary Fund"].institution_type == "other"
    assert federal.type_of("Shared-Governance Corporations", "Saint John Airport Inc.") == (
        "airport_authority"
    )
    assert federal.type_of("Shared-Governance Corporations", "Oshawa Port Authority") == (
        "port_authority"
    )
    assert federal.type_of("Parliamentary Entities", "Senate Ethics Officer") == "agency"
    assert by_name["Department of Health"].aliases == (federal.AliasEntry(text="Health Canada"),)
    # Two sites in one cell: the first is kept.
    assert by_name["Offices of the Information and Privacy Commissioners of Canada"].homepage == (
        "http://www.priv.gc.ca/"
    )
    assert by_name["Canadian Tourism Commission"].homepage == "http://en-corporate.canada.travel/"
    soldier = by_name["Director of Soldier Settlement"]
    assert (soldier.institution_type, soldier.suggested_type, soldier.homepage) == (
        "other",
        "Other Organizations",
        None,
    )
    assert "Canada Industrial Relations Board" not in by_name
    assert federal.website("www.priv.gc.ca *,* www.oic-ci.gc.ca") == "http://www.priv.gc.ca/"
    assert federal.website("") is None
    assert federal.website("not a site") is None
