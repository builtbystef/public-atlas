"""The transit list: `entries()` on the cached files keeps every rule, the counts per naming
rule and per place are pinned, and a few bodies show the rules a count cannot."""

from collections import Counter

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import InstitutionEntry
from public_atlas.modules.imports.lists.us import transit

ENTRIES = 1518
LEFT_OUT = {
    "": 54,
    "Area Agency on Aging": 49,
    "MPO, COG or Other Planning Agency": 80,
    "Other": 1,
    "Other Publicly-Owned or Privately Chartered Corporation": 16,
    "Private Provider Reporting on Behalf of a Public Entity": 6,
    "Private-For-Profit Corporation": 111,
    "Private-Non-Profit Corporation": 620,
    "Subsidiary Unit of a Transit Agency, Reporting Separately": 8,
    "Tribe": 138,
    "University": 24,
}
ASSET_MODULE = 200
NO_STATE = 5
FOLDED = 19
NAMED = {
    "the agency name": 629,
    "the trade name of a government's service": 701,
    "the division of a government's service": 188,
}
NO_NAME = 65
PLACED = {
    "a government's place": 793,
    "the county of a government whose place shares its name": 96,
    "the city of its address": 414,
    "the county of its city, which shares its name": 76,
    "the state: a state unit": 29,
    "the state: its city is no one place": 110,
}
LEVELS = {"municipality": 831, "county": 548, "state": 139}
ALIASES = 253
WEBSITES = 1485


@pytest.fixture(scope="module")
def opened(transit_files: dict[str, files.OpenedFile]) -> dict[str, files.OpenedFile]:
    return transit_files


@pytest.fixture(scope="module")
def built(
    opened: dict[str, files.OpenedFile], rules: countries.CountryRules
) -> tuple[list[InstitutionEntry], transit.Notes]:
    return transit.build(opened, rules)


@pytest.fixture(scope="module")
def entries(built: tuple[list[InstitutionEntry], transit.Notes]) -> list[InstitutionEntry]:
    return built[0]


@pytest.fixture(scope="module")
def notes(built: tuple[list[InstitutionEntry], transit.Notes]) -> transit.Notes:
    return built[1]


@pytest.fixture(scope="module")
def by_name(entries: list[InstitutionEntry]) -> dict[str, InstitutionEntry]:
    return {entry.name: entry for entry in entries}


def test_the_counts(
    entries: list[InstitutionEntry],
    notes: transit.Notes,
    opened: dict[str, files.OpenedFile],
    rules: countries.CountryRules,
):
    assert len(transit.entries(opened, rules)) == ENTRIES
    assert len(entries) == ENTRIES
    assert dict(notes.left_out) == LEFT_OUT
    assert notes.asset_module == ASSET_MODULE
    assert notes.no_state == NO_STATE
    assert notes.folded == FOLDED
    assert dict(notes.named) == NAMED
    assert len(notes.no_name) == NO_NAME
    assert dict(notes.placed) == PLACED
    assert Counter(entry.place_level for entry in entries) == LEVELS
    assert notes.aliases == ALIASES
    assert sum(len(entry.aliases) for entry in entries) == ALIASES
    assert notes.websites == WEBSITES
    assert sum(1 for entry in entries if entry.homepage) == WEBSITES
    assert all(entry.institution_type == transit.TRANSIT_AGENCY for entry in entries)
    assert all(entry.codes == () for entry in entries)
    # Two bodies of one name ("Jackson County Transit") sit at places of one name in two
    # states, never at one place, so the loader folds none into another.
    at_place = Counter((entry.name, entry.place, entry.place_parent) for entry in entries)
    assert max(at_place.values()) == 1


def test_every_entry_cites_the_row_that_names_it_and_sits_at_a_place(
    entries: list[InstitutionEntry], opened: dict[str, files.OpenedFile]
):
    agencies = opened[transit.AGENCIES.name]
    for entry in entries:
        citation = entry.citations["institution"]
        assert citation.source == transit.AGENCIES.name
        line = agencies.line(citation.line)
        # The name is the row's trade name, its division (composed with the agency name) or
        # the agency name, recased: every word of it is on the line.
        assert all(word.lower() in line.lower() for word in entry.name.split())
        assert entry.place_level in LEVELS
        assert (entry.place_parent is None) == (entry.place_level == "state")
        if entry.homepage is not None:
            homepage = entry.citations["homepage"]
            assert homepage.source == transit.AGENCIES.name
            assert entry.homepage.startswith(("http://", "https://"))


def test_the_bodies_that_show_the_rules(by_name: dict[str, InstitutionEntry]):
    # A city's service goes by its trade name, at the city.
    sun_tran = by_name["Sun Tran"]
    assert (sun_tran.place, sun_tran.place_level, sun_tran.place_parent) == (
        "Tucson",
        "municipality",
        "Pima County",
    )
    # A county's eleven services are one body, named by the one row with a trade name and
    # given the first website among the rows.
    la = by_name["LA County Public Works"]
    assert (la.place, la.place_level) == ("Los Angeles County", "county")
    assert la.homepage == "http://www.dpw.lacounty.gov/transit"
    assert la.citations["institution"].line != la.citations["homepage"].line
    # A division that says it is a transit service, composed with the government's name.
    assert by_name["Town of Wallkill Dial A Bus"].place == "Wallkill"
    # An authority is its own body, with its brand as an alias. Its city shares its name with
    # the charter township beside it, which the loader cannot tell apart, so the county stands
    # in.
    rapid = by_name["Interurban Transit Partnership"]
    assert (rapid.place, rapid.place_level, rapid.place_parent) == (
        "Kent County",
        "county",
        "Michigan",
    )
    assert [alias.text for alias in rapid.aliases] == ["The Rapid"]
    # The City of Jackson, Tennessee, reads like the Township of Jackson under Madison County,
    # Indiana: the county stands in.
    assert by_name["Jackson Transit Authority"].place == "Madison County"
    # The rows of one authority across eight counties are one body.
    assert by_name["Regional Transit Service"].place == "Rochester"
    assert by_name["Ann Arbor Area Transportation Authority"].homepage == "http://www.theride.org/"
    # A state unit sits under its state; Puerto Rico's bodies under Puerto Rico.
    assert by_name["Connecticut Department of Transportation"].place == "Connecticut"
    assert by_name["Metropolitan Bus Authority"].place == "Puerto Rico"
    # A government's service with no name of its own is no body.
    assert "City of Seneca" not in by_name
    assert "Public Works" not in by_name
    assert (
        transit.service_name(
            transit.Reporter(
                "1", "City of Natchez", "Natchez Transit System", "", "", "", "", "", None, 1
            ),
            transit.Attachment("Natchez", "municipality", "Adams County"),
        )
        == "Natchez Transit System"
    )
    assert (
        transit.service_name(
            transit.Reporter("1", "City of Seneca", "Public Works", "", "", "", "", "", None, 1),
            transit.Attachment("Seneca", "municipality", "Oconee County"),
        )
        is None
    )
