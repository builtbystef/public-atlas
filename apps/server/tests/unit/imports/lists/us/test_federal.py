"""The federal list: `entries()` on the cached files keeps every rule, the counts are pinned,
and a few bodies show the rules a count cannot."""

from collections import Counter

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import InstitutionEntry
from public_atlas.modules.imports.lists.us import federal

ENTRIES = 276
TYPED = {"department": 15, "agency": 261}
KEPT_BY = {
    "published in the window": 269,
    "a registered domain in its own name": 7,
}
LEFT_OUT = 197
OFFICIAL_NAMES = 21
WITH_PARENT = 141
WEBSITES = 196
REGISTERED = 190
ALIASES = 285
ACRONYMS = 257
# Short names two kept bodies share, given to neither.
SHARED_SHORT_NAMES = ["FS", "LOC", "OFR"]


@pytest.fixture(scope="module")
def opened(federal_files: dict[str, files.OpenedFile]) -> dict[str, files.OpenedFile]:
    return federal_files


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
    assert len(federal.entries(opened, rules)) == ENTRIES
    assert len(entries) == ENTRIES
    assert dict(notes.typed) == TYPED
    assert Counter(entry.institution_type for entry in entries) == TYPED
    assert dict(notes.kept_by) == KEPT_BY
    assert len(notes.left_out) == LEFT_OUT
    assert notes.official_names == OFFICIAL_NAMES
    assert notes.with_parent == WITH_PARENT
    assert sum(1 for entry in entries if entry.parent_institution) == WITH_PARENT
    assert notes.websites == WEBSITES
    assert sum(1 for entry in entries if entry.homepage) == WEBSITES
    assert len(notes.registered) == REGISTERED
    assert sum(len(entry.aliases) for entry in entries) == ALIASES
    assert sum(1 for entry in entries for alias in entry.aliases if alias.is_acronym) == ACRONYMS
    assert notes.shared_short_names == SHARED_SHORT_NAMES
    # No two bodies share a name or an alias: the loader would read the second as the first.
    texts = [alias.text for entry in entries for alias in entry.aliases] + [e.name for e in entries]
    assert len(set(texts)) == len(texts)
    names = [entry.name for entry in entries]
    assert len(set(names)) == len(names)


def test_every_entry_cites_the_record_that_names_it_and_sits_under_the_country(
    entries: list[InstitutionEntry], opened: dict[str, files.OpenedFile]
):
    records = opened[federal.AGENCIES.name]
    for entry in entries:
        citation = entry.citations["institution"]
        assert citation.source == federal.AGENCIES.name
        line = records.line(citation.line)
        listed = next(
            (alias.text for alias in entry.aliases if alias.text in federal.OFFICIAL_NAMES), None
        )
        assert (listed or entry.name) in line
        assert (entry.place, entry.place_level) == (federal.PLACE, federal.PLACE_LEVEL)
        assert entry.codes == ()
        if entry.homepage is not None:
            assert entry.citations["homepage"] == citation
            assert entry.homepage.startswith(("http://", "https://"))


def test_parents_are_loaded_before_their_children(
    entries: list[InstitutionEntry], by_name: dict[str, InstitutionEntry]
):
    """The loader finds a parent by name among the bodies already at the place."""
    seen: set[str] = set()
    for entry in entries:
        if entry.parent_institution is not None:
            assert entry.parent_institution in seen, entry.name
            assert entry.parent_institution in by_name
        seen.add(entry.name)


def test_the_bodies_that_show_the_rules(by_name: dict[str, InstitutionEntry]):
    defense = by_name["Department of Defense"]
    assert defense.institution_type == "department"
    assert defense.parent_institution is None
    assert [(alias.text, alias.is_acronym) for alias in defense.aliases] == [
        ("Defense Department", False),
        ("DOD", True),
    ]
    navy = by_name["Department of the Navy"]
    assert (navy.institution_type, navy.parent_institution) == ("agency", "Department of Defense")
    forest = by_name["Forest Service"]
    assert (forest.parent_institution, forest.homepage) == (
        "Department of Agriculture",
        "https://www.fs.usda.gov/",
    )
    # "FS" is the Fiscal Service's short name too: neither carries it.
    assert forest.aliases == ()
    assert by_name["Fiscal Service"].aliases == ()
    # A body two levels down keeps its own parent.
    firstnet = by_name["First Responder Network Authority"]
    assert (
        firstnet.parent_institution == "National Telecommunications and Information Administration"
    )
    assert by_name[firstnet.parent_institution].parent_institution == "Department of Commerce"
    # A name the list inverts around a comma, from the hand table.
    ustr = by_name["Office of the United States Trade Representative"]
    assert ustr.aliases[0].text == "Trade Representative, Office of United States"
    # Kept for its domain alone: no documents in the window.
    assert by_name["Architect of the Capitol"].homepage == "http://www.aoc.gov/"
    assert "Interstate Commerce Commission" not in by_name
    assert "Resolution Trust Corporation" not in by_name
    assert federal.official_name("Agriculture Department") == (
        "Department of Agriculture",
        "Agriculture Department",
    )
    assert federal.official_name("National Park Service") == ("National Park Service", None)
    assert federal.registrable_domain("https://www.fs.usda.gov/") == "usda.gov"


def test_the_files_as_the_loader_renders_them(opened: dict[str, files.OpenedFile]):
    """The list is one line per record, so a citation is one body's; the document counts are
    one object, read for the slugs alone."""
    records = opened[federal.AGENCIES.name]
    assert len(records.lines) == len(records.document) == 473
    assert federal.published_slugs(opened[federal.DOCUMENTS.name]) <= {
        record["slug"] for record in records.document
    }
    assert len(opened[federal.DOCUMENTS.name].lines) == 1
    registry = federal.registered_domains(opened[federal.DOTGOV_FEDERAL.name])
    assert registry["cbo.gov"] == "Congressional Budget Office"
