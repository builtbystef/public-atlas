"""The special districts list: `entries()` on the cached workbook keeps every rule, the counts
per type and per place level are pinned, and a few districts show the rules a count cannot."""

from collections import Counter

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import IdentifierScheme
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import InstitutionEntry
from public_atlas.modules.imports.lists.us import governments, special_districts

ENTRIES = 39313
INACTIVE = 242
NO_ID = 36
WEBSITES = 11209
TYPED = {
    "fire_service": 5998,
    "hospital": 641,
    "library": 1668,
    "municipal_corporation": 4088,
    "other": 17034,
    "park_district": 1901,
    "police_service": 35,
    "public_utility": 7583,
    "transit_agency": 365,
}
PLACED = {"county": 38403, "municipality": 749, "state": 161}


@pytest.fixture(scope="module")
def opened(special_districts_files: dict[str, files.OpenedFile]) -> dict[str, files.OpenedFile]:
    return special_districts_files


@pytest.fixture(scope="module")
def built(
    opened: dict[str, files.OpenedFile], rules: countries.CountryRules
) -> tuple[list[InstitutionEntry], special_districts.Notes]:
    return special_districts.build(opened, rules)


@pytest.fixture(scope="module")
def entries(
    built: tuple[list[InstitutionEntry], special_districts.Notes],
) -> list[InstitutionEntry]:
    return built[0]


@pytest.fixture(scope="module")
def notes(
    built: tuple[list[InstitutionEntry], special_districts.Notes],
) -> special_districts.Notes:
    return built[1]


@pytest.fixture(scope="module")
def by_id(entries: list[InstitutionEntry]) -> dict[str, InstitutionEntry]:
    return {entry.codes[0].value: entry for entry in entries if entry.codes}


def test_the_counts(
    entries: list[InstitutionEntry],
    notes: special_districts.Notes,
    opened: dict[str, files.OpenedFile],
    rules: countries.CountryRules,
):
    assert len(special_districts.entries(opened, rules)) == ENTRIES
    assert len(entries) == ENTRIES
    assert dict(notes.typed) == TYPED
    assert Counter(entry.institution_type for entry in entries) == TYPED
    assert dict(notes.placed) == PLACED
    assert Counter(entry.place_level for entry in entries) == PLACED
    assert notes.inactive == INACTIVE
    assert notes.no_id == NO_ID
    assert sum(1 for entry in entries if not entry.codes) == NO_ID
    assert notes.websites == WEBSITES
    assert sum(1 for entry in entries if entry.homepage) == WEBSITES
    ids = [entry.codes[0].value for entry in entries if entry.codes]
    assert len(set(ids)) == len(ids)
    assert sum(notes.suggested.values()) == TYPED["other"]
    assert notes.suggested["cemeteries"] == 1673
    assert notes.suggested["soil and water conservation"] == 2536


def test_every_entry_cites_the_line_that_names_it_and_sits_at_a_place(
    entries: list[InstitutionEntry], opened: dict[str, files.OpenedFile]
):
    workbook = opened[governments.GOVT_UNITS.name]
    for entry in entries:
        citation = entry.citations["institution"]
        assert citation.source == governments.GOVT_UNITS.name
        line = " ".join(workbook.line(citation.line).split())
        assert entry.name.upper() in line.upper()

        assert (entry.institution_type == "other") == (entry.suggested_type is not None)
        for code in entry.codes:
            assert code.scheme is IdentifierScheme.CENSUS_GID
            assert code.value in line
        assert entry.place_level in PLACED
        assert (entry.place_parent is None) == (entry.place_level == "state")
        if entry.homepage is not None:
            assert entry.citations["homepage"] == citation
            assert entry.homepage.startswith(("http://", "https://"))


def test_the_districts_that_show_the_rules(by_id: dict[str, InstitutionEntry]):
    housing = by_id["01400150100000"]
    assert (housing.name, housing.institution_type, housing.place, housing.place_level) == (
        "Prattville Housing Authority",
        "municipal_corporation",
        "Autauga County",
        "county",
    )
    assert housing.place_parent == "Alabama"
    water = by_id["01400160100000"]
    assert (water.name, water.institution_type) == (
        "Autauga County Water Authority",
        "public_utility",
    )
    assert special_districts.function_type("24 - LOCAL FIRE PROTECTION") == ("fire_service", None)
    assert special_districts.function_type("02 - CEMETERIES") == ("other", "cemeteries")
    assert special_districts.function_type("99 - OTHER MULTI-FUNCTION DISTRICTS") == (
        "other",
        "other multi-function districts",
    )
    assert special_districts.function_type("62 - POLICE PROTECTION") == ("police_service", None)


def test_a_district_in_a_county_that_is_no_place_sits_under_its_city_or_state(
    entries: list[InstitutionEntry],
):
    """Connecticut's planning regions and Massachusetts' abolished counties are no places: a
    district there sits under the town of its address when one is loaded, else the state;
    Virginia's independent cities are the places of their districts."""
    connecticut = [entry for entry in entries if entry.place_parent == "Connecticut"]
    assert connecticut
    assert {entry.place_level for entry in connecticut} == {"municipality"}
    under_state = [entry for entry in entries if entry.place_level == "state"]
    assert Counter(entry.place for entry in under_state).most_common(3)[0][0] in {
        "Connecticut",
        "Massachusetts",
        "Alaska",
        "District of Columbia",
        "Rhode Island",
    }
    virginia_cities = [
        entry
        for entry in entries
        if entry.place_parent == "Virginia" and entry.place_level == "municipality"
    ]
    assert any(entry.place == "Richmond" for entry in virginia_cities)
    assert all(entry.place_level == "county" for entry in entries if entry.place == "Cook County")
