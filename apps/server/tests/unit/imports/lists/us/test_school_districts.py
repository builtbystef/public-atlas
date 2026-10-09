"""The school districts list: `entries()` on the cached files keeps every rule, the counts per
agency type and per place level are pinned, and a few agencies show the rules a count cannot."""

from collections import Counter

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import IdentifierScheme
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import InstitutionEntry
from public_atlas.modules.imports.lists.us import school_districts

ENTRIES = 18229
SERVICE_AGENCIES = "other: Service agency"
CHARTERS = "school_board: Independent charter district"
COMPONENTS = (
    "school_board: Regular public school district that is a component of a supervisory union"
)
REGULAR = (
    "school_board: Regular public school district that is not a component of a supervisory union"
)
TYPED = {SERVICE_AGENCIES: 681, CHARTERS: 4212, COMPONENTS: 173, REGULAR: 13163}

LEFT_OUT = {
    "Federal operated agency": 4,
    "Other local education agency": 246,
    "Specialized public school district": 441,
    "State operated agency": 186,
    "Supervisory union": 114,
}
NOT_OPERATING = {"Closed": 137, "Future": 49, "Inactive": 48}
PLACED = {"county": 17510, "municipality": 547, "state": 172}
OUT_OF_STATE = 189
# The Bureau of Indian Education's schools and the territories' agencies; Puerto Rico's
# Department of Education sits under Puerto Rico.
NO_STATE = 183
# One more than the first load: a served place is judged by the loaded name, as the loader
# reads it, since the transit list needed that reading.
SERVED = 12864
WEBSITES = 16107


@pytest.fixture(scope="module")
def opened(school_districts_files: dict[str, files.OpenedFile]) -> dict[str, files.OpenedFile]:
    return school_districts_files


@pytest.fixture(scope="module")
def built(
    opened: dict[str, files.OpenedFile], rules: countries.CountryRules
) -> tuple[list[InstitutionEntry], school_districts.Notes]:
    return school_districts.build(opened, rules)


@pytest.fixture(scope="module")
def entries(
    built: tuple[list[InstitutionEntry], school_districts.Notes],
) -> list[InstitutionEntry]:
    return built[0]


@pytest.fixture(scope="module")
def notes(built: tuple[list[InstitutionEntry], school_districts.Notes]) -> school_districts.Notes:
    return built[1]


@pytest.fixture(scope="module")
def by_id(entries: list[InstitutionEntry]) -> dict[str, InstitutionEntry]:
    return {entry.codes[0].value: entry for entry in entries}


def test_the_counts(
    entries: list[InstitutionEntry],
    notes: school_districts.Notes,
    opened: dict[str, files.OpenedFile],
    rules: countries.CountryRules,
):
    assert len(school_districts.entries(opened, rules)) == ENTRIES
    assert len(entries) == ENTRIES
    assert dict(notes.typed) == TYPED
    assert dict(notes.left_out) == LEFT_OUT
    assert dict(notes.not_operating) == NOT_OPERATING
    assert dict(notes.placed) == PLACED
    assert Counter(entry.place_level for entry in entries) == PLACED
    assert notes.out_of_state == OUT_OF_STATE
    assert notes.no_geocode == 0
    assert len(notes.no_state) == NO_STATE
    assert notes.served == SERVED
    assert sum(1 for entry in entries if entry.served_places) == SERVED
    assert notes.websites == WEBSITES
    assert sum(1 for entry in entries if entry.homepage) == WEBSITES
    ids = [entry.codes[0].value for entry in entries]
    assert len(set(ids)) == len(ids)
    assert Counter(entry.institution_type for entry in entries) == {
        "school_board": TYPED[CHARTERS] + TYPED[COMPONENTS] + TYPED[REGULAR],
        "other": TYPED[SERVICE_AGENCIES],
    }


def test_every_entry_cites_the_line_that_names_it_and_sits_at_a_place(
    entries: list[InstitutionEntry], opened: dict[str, files.OpenedFile]
):
    directory = opened[school_districts.DIRECTORY.name]
    for entry in entries:
        citation = entry.citations["institution"]
        assert citation.source == school_districts.DIRECTORY.name
        line = " ".join(directory.line(citation.line).split())
        assert entry.name in line

        (code,) = entry.codes
        assert code.scheme is IdentifierScheme.NCES
        assert line.startswith(f"{code.value} | ")
        assert (entry.institution_type == "other") == (
            entry.suggested_type == school_districts.SERVICE_AGENCY_TYPE
        )
        assert entry.place_level in PLACED
        assert (entry.place_parent is None) == (entry.place_level == "state")
        for served in entry.served_places:
            assert entry.place_level == "county"
            assert (served.level, served.parent) == ("municipality", entry.place)
        if entry.homepage is not None:
            assert entry.citations["homepage"] == citation
        if entry.aliases:
            assert [alias.text for alias in entry.aliases] == ["Independent charter district"]


def test_the_agencies_that_show_the_rules(by_id: dict[str, InstitutionEntry]):
    albertville = by_id["0100005"]
    assert (albertville.name, albertville.institution_type, albertville.aliases) == (
        "Albertville City",
        "school_board",
        (),
    )
    assert (albertville.place, albertville.place_level, albertville.place_parent) == (
        "Marshall County",
        "county",
        "Alabama",
    )
    assert [(s.name, s.level, s.parent) for s in albertville.served_places] == [
        ("Albertville", "municipality", "Marshall County")
    ]
    assert albertville.homepage == "http://www.albertk12.org/"
    # A state agency's district sits where its office is.
    assert by_id["0100002"].place == "Montgomery County"
    charters = [entry for entry in by_id.values() if entry.aliases]
    assert len(charters) == TYPED[CHARTERS]
    agencies = [entry for entry in by_id.values() if entry.institution_type == "other"]
    assert len(agencies) == TYPED[SERVICE_AGENCIES]

    assert all(entry.suggested_type == "education service agency" for entry in agencies)
    # Connecticut's towns are the places of its districts; the District of Columbia's are at
    # the District.
    connecticut = [entry for entry in by_id.values() if entry.place_parent == "Connecticut"]
    assert connecticut
    assert {entry.place_level for entry in connecticut} == {"municipality"}
    assert any(entry.place == "Hartford" for entry in connecticut)
    district = [entry for entry in by_id.values() if entry.place == "District of Columbia"]
    assert district
    assert {entry.place_level for entry in district} == {"state"}
