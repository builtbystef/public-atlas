"""The government units list: `entries()` on the cached files keeps every rule, the counts of
rows matched, dropped and corrected are pinned, the share of governments given a candidate
homepage is pinned per level, and a few governments show the rules a count cannot."""

from collections import Counter

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import IdentifierScheme
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.us import (
    census,
    government_units,
    governments,
    municipalities,
    states_counties,
)

# Every loaded place the sheet or the registry adds to: 3,031 counties and 35,549
# municipalities.
ENTRIES = 38580
MATCHED = {
    ("county", "code"): 3031,
    ("municipal", "code"): 19424,
    ("municipal", "name"): 3,
    ("municipal", "override"): 5,
    ("township", "code"): 16095,
    ("township", "name"): 1,
}
INACTIVE = 96
# Active rows whose unit the 2025 estimates no longer carry.
NO_UNIT = 80
LEGAL_NAMES = 3707
REGISTRY = {
    "matched": 9463,
    "naming no government": 1539,
    "naming no loaded government": 574,
    "naming several governments": 270,
}
GOVERNMENTS = {"county": 3031, "municipality": 35549}
HOMEPAGES = {
    ("county", governments.GOVT_UNITS.name): 2225,
    ("county", government_units.DOTGOV.name): 313,
    ("municipality", governments.GOVT_UNITS.name): 13900,
    ("municipality", government_units.DOTGOV.name): 1888,
}


@pytest.fixture(scope="module")
def opened(government_units_files: dict[str, files.OpenedFile]) -> dict[str, files.OpenedFile]:
    return government_units_files


@pytest.fixture(scope="module")
def built(
    opened: dict[str, files.OpenedFile], rules: countries.CountryRules
) -> tuple[list[PlaceEntry], government_units.Notes]:
    return government_units.build(opened, rules)


@pytest.fixture(scope="module")
def entries(built: tuple[list[PlaceEntry], government_units.Notes]) -> list[PlaceEntry]:
    return built[0]


@pytest.fixture(scope="module")
def notes(built: tuple[list[PlaceEntry], government_units.Notes]) -> government_units.Notes:
    return built[1]


@pytest.fixture(scope="module")
def by_code(entries: list[PlaceEntry]) -> dict[str, PlaceEntry]:
    return {entry.code.value: entry for entry in entries}


@pytest.fixture(scope="module")
def loaded(opened: dict[str, files.OpenedFile]) -> dict[str, PlaceEntry]:
    """The places the two places lists load, by code."""
    counties, _ = states_counties.build(opened)
    places, _ = municipalities.build(opened)
    return {entry.code.value: entry for entry in [*counties, *places]}


def test_the_counts(
    entries: list[PlaceEntry],
    notes: government_units.Notes,
    opened: dict[str, files.OpenedFile],
    rules: countries.CountryRules,
):
    assert len(government_units.entries(opened, rules)) == ENTRIES
    assert len(entries) == ENTRIES
    assert dict(notes.matched) == MATCHED
    assert notes.inactive == INACTIVE
    assert len(notes.no_unit) == NO_UNIT
    assert "1150000 CITY OF WASHINGTON DC, DC" in notes.left_out[0]
    assert notes.no_government == ["13101 COUNTY OF ECHOLS, GA"]
    assert len(notes.overrides) == len(government_units.OVERRIDES) == 5
    assert notes.legal_names == LEGAL_NAMES
    assert dict(notes.registry) == REGISTRY
    assert dict(notes.governments) == GOVERNMENTS
    assert Counter(entry.level for entry in entries) == GOVERNMENTS
    assert dict(notes.homepages) == HOMEPAGES
    codes = [entry.code.value for entry in entries]
    assert len(set(codes)) == len(codes)
    ids = [entry.codes[0].value for entry in entries if entry.codes]
    assert len(ids) == sum(MATCHED.values()) - 1
    assert len(set(ids)) == len(ids)


def test_the_share_of_governments_with_a_candidate_homepage(entries: list[PlaceEntry]):
    with_homepage = Counter(entry.level for entry in entries if entry.homepage)
    assert with_homepage == {"county": 2538, "municipality": 15788}
    assert with_homepage["county"] / GOVERNMENTS["county"] > 0.83
    assert with_homepage["municipality"] / GOVERNMENTS["municipality"] > 0.44


def test_every_entry_is_a_loaded_place_again_with_what_the_sheet_adds(
    entries: list[PlaceEntry],
    loaded: dict[str, PlaceEntry],
    opened: dict[str, files.OpenedFile],
    rules: countries.CountryRules,
):
    naming = rules.naming
    workbook = opened[governments.GOVT_UNITS.name]
    registry = opened[government_units.DOTGOV.name]
    for entry in entries:
        place = loaded[entry.code.value]
        assert (entry.name, entry.level, entry.parent, entry.parent_level, entry.parent_parent) == (
            place.name,
            place.level,
            place.parent,
            place.parent_level,
            place.parent_parent,
        )
        assert entry.aliases == place.aliases
        assert entry.figures == ()
        assert entry.citations["place"] == place.citations["place"]
        assert place.government is not None
        assert entry.government is not None
        government = entry.citations.get("government")
        if government is None:
            # A registry match alone: the composed name stays and the homepage is the domain's.
            assert entry.government == place.government
            assert entry.codes == ()
            assert entry.homepage is not None
            assert entry.citations["homepage"].source == government_units.DOTGOV.name
        else:
            assert government.source == governments.GOVT_UNITS.name
            line = workbook.line(government.line)
            # The legal name is the sheet's, recased; the place name inside it is the census's.
            assert naming.core(entry.government) == naming.core(place.government) or (
                naming.core(entry.government) in naming.key(line)
            )

            for code in entry.codes:
                assert code.scheme is IdentifierScheme.CENSUS_GID
                assert line.startswith(f"{code.value} | ")
        if entry.homepage is not None:
            citation = entry.citations["homepage"]
            if citation.source == governments.GOVT_UNITS.name:
                assert citation == government
            else:
                assert entry.homepage.startswith("https://")
                domain = entry.homepage.removeprefix("https://").rstrip("/")
                assert registry.line(citation.line).startswith(f"{domain} | ")


def test_the_governments_that_show_the_rules(
    by_code: dict[str, PlaceEntry], loaded: dict[str, PlaceEntry]
):
    autauga = by_code["01001"]
    assert (autauga.government, autauga.homepage) == (
        "County of Autauga",
        "http://www.autaugaco.org/",
    )
    assert autauga.codes[0].value == "01100100100000"
    assert loaded["01001"].government == "Autauga County"
    # Overrides: the consolidated cities, Honolulu and Terrebonne by the codes the sheet gives.
    assert by_code["0947500"].government == "City of Milford"
    assert by_code["1836000"].homepage == "http://www.ci.indianapolis.in.us/"
    assert by_code["1304200"].government == "Consolidated Government of Augusta-Richmond County"
    assert by_code["15003"].government == "City and County of Honolulu"
    assert by_code["15003"].level == "municipality"
    assert by_code["22109"].government == "Consolidated Government of Terrebonne"
    assert loaded["22109"].government == "Terrebonne Parish"
    # The census's spelling of the place name is kept inside the legal name.
    assert by_code["0667000"].government == "City and County of San Francisco"
    assert by_code["3651000"].homepage == "https://www.nyc.gov/"
    # A legal designator that differs from the census kind is an alias worth adding; one that
    # differs only in punctuation is not.
    liberties = [
        entry
        for entry in by_code.values()
        if entry.name == "Liberty" and entry.government == "Town of Liberty"
    ]
    assert any(loaded[entry.code.value].government == "Village of Liberty" for entry in liberties)
    assert by_code["5101000"].government == "City of Alexandria"
    # The City of Washington and Echols County name no government here.
    assert "1150000" not in by_code
    assert "13101" not in by_code
    # A registry domain for a government the sheet gives no website.
    barbour = by_code["01005"]
    assert barbour.homepage == "https://barbourcountyal.gov/"
    assert barbour.citations["homepage"].source == government_units.DOTGOV.name


def test_a_registry_organization_is_read_as_a_place_name_and_a_designator(
    rules: countries.CountryRules,
):
    naming = rules.naming
    county = naming.designators_in("Cook County")
    assert government_units.registry_key(naming, "Henry County Government") == ("henry", county)
    assert government_units.registry_key(naming, "Adams County, IL") == ("adams", county)
    assert government_units.registry_key(naming, "Adams County Iowa") == ("adams", county)
    assert government_units.registry_key(naming, "Alachua County BOCC") == ("alachua", county)
    assert government_units.registry_key(naming, "Aransas County, State of Texas") == (
        "aransas",
        county,
    )
    assert government_units.registry_key(naming, "Assumption Parish Police Jury") == (
        "assumption",
        naming.designators_in("Orleans Parish"),
    )
    township = naming.designators_in("Township of Abington")
    assert government_units.registry_key(naming, "Abington Township") == ("abington", township)
    assert government_units.registry_key(naming, "APEX, TOWN OF") == (
        "apex",
        naming.designators_in("Town of Apex"),
    )
    assert government_units.registry_key(naming, "The City of Ashland, KY") == (
        "ashland",
        naming.designators_in("City of Ashland"),
    )
    assert government_units.registry_key(naming, "Lexington-Fayette Urban County Government") == (
        government_units.government_key(naming, "Lexington-Fayette Urban County Government")
    )
    assert government_units.registry_key(naming, "Town of Maine") == (
        "maine",
        naming.designators_in("Town of Maine"),
    )
    for other in (
        "Riverside County Fire Department",
        "Arapahoe County Clerk Recorder",
        "Alice Baker Memorial Public Library",
        "Town and Village of Allegany",
    ):
        assert government_units.registry_key(naming, other) is None, other
    assert government_units.government_key(naming, "Cook County") == ("cook", county)
    assert government_units.government_key(naming, "Carson City") == (
        "carson",
        naming.designators_in("City of Carson"),
    )
    assert government_units.government_key(naming, "Springfield") is None


def test_the_legal_name_takes_the_census_spelling_where_the_two_agree():
    def unit(name: str) -> governments.GovernmentUnit:
        return governments.GovernmentUnit(
            gid=None,
            name=name,
            unit_type=governments.MUNICIPAL,
            function="",
            city="",
            state="XX",
            website=None,
            fips_state="00",
            fips_county="000",
            fips_place="00000",
            county_area="",
            active=True,
            line=1,
        )

    assert government_units.legal_name(unit("CITY OF ST MARTIN"), "St. Martin") == (
        "City of St. Martin"
    )
    assert government_units.legal_name(unit("TOWN OF SEWALLS POINT"), "Sewall's Point") == (
        "Town of Sewall's Point"
    )
    assert government_units.legal_name(unit("CITY OF TEMPLE"), "Temple City") == "City of Temple"
    assert government_units.legal_name(unit("TOWNSHIP OF NUMBER 9"), "Township 9") == (
        "Township of Number 9"
    )
    assert government_units.legal_name(unit("BUTTE-SILVER BOW"), "Butte-Silver Bow") == (
        "Butte-Silver Bow"
    )
    assert census.split_name("Carson City") == ("Carson City", None)
