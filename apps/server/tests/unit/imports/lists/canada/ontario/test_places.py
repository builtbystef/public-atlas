"""The Ontario places list: the counts of the pilot are pinned, each government is named from
its place and each homepage is the directory's link, regions sit under Ontario and
municipalities inside their division, and a few places show the rules a count cannot. What
every list's entries must satisfy is checked by the contract test beside the lists."""

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.canada.ontario import places as ontario_places

REGIONS = 40
MUNICIPALITIES = 414
GOVERNMENTS = 444
DISTRICTS = 10
# Three governments have no link in the directory.
HOMEPAGES = 441


@pytest.fixture(scope="module")
def entries(places: list[PlaceEntry]) -> list[PlaceEntry]:
    return places


@pytest.fixture(scope="module")
def by_name(entries: list[PlaceEntry]) -> dict[tuple[str, str], PlaceEntry]:
    return {(entry.level, entry.name): entry for entry in entries}


def test_the_counts_of_the_pilot(entries: list[PlaceEntry]):
    regions = [entry for entry in entries if entry.level == "region"]
    municipalities = [entry for entry in entries if entry.level == "municipality"]
    assert len(regions) == REGIONS
    assert len(municipalities) == MUNICIPALITIES
    assert len(entries) == REGIONS + MUNICIPALITIES
    assert sum(1 for entry in entries if entry.government) == GOVERNMENTS
    assert sum(1 for entry in regions if entry.government is None) == DISTRICTS
    assert sum(1 for entry in entries if entry.homepage) == HOMEPAGES
    codes = [entry.code.value for entry in entries]
    assert len(set(codes)) == len(codes)


def test_every_government_is_named_from_its_place_and_a_district_has_none(
    entries: list[PlaceEntry], rules: countries.CountryRules
):
    naming = rules.naming
    for entry in entries:
        if entry.government is None:
            # A district: no government, so no homepage to claim.
            assert entry.level == "region", entry.name
            assert entry.homepage is None
            continue
        # "City of Kingston" governs "Kingston"; "Haldimand County" governs itself; the
        # designator in "Whitewater Region" is the name's own.
        assert naming.core(entry.government) in (
            naming.core(entry.name),
            naming.key(entry.name),
        ), entry.name


def test_every_homepage_is_the_directorys_link_on_the_governments_row(entries: list[PlaceEntry]):
    for entry in entries:
        if entry.homepage is None:
            continue
        citation = entry.citations["homepage"]
        assert citation.source == ontario_places.DIRECTORY.name
        assert citation == entry.citations["government"]


def test_regions_sit_under_ontario_and_municipalities_inside_their_division(
    entries: list[PlaceEntry], by_name: dict[tuple[str, str], PlaceEntry]
):
    regions = {entry.code.value: entry for entry in entries if entry.level == "region"}
    assert all(entry.parent == "Ontario" for entry in regions.values())
    for entry in entries:
        if entry.level != "municipality":
            continue
        division = regions.get(entry.code.value[:4])
        if entry.parent != "Ontario":
            # A lower tier: its census division is its upper tier or district.
            assert division is not None, entry.name
            assert division.name == entry.parent
            assert by_name[("region", entry.parent)] is division
        elif division is not None:
            # Under the province inside a division: a separated municipality, never a district's.
            assert division.government is not None, entry.name


def test_the_places_that_show_the_rules(by_name: dict[tuple[str, str], PlaceEntry]):
    assert by_name[("municipality", "Kitchener")].parent == "Waterloo"
    assert by_name[("region", "Waterloo")].government == "Regional Municipality of Waterloo"
    assert by_name[("municipality", "Mattice-Val Côté")].parent == "Cochrane"
    assert by_name[("municipality", "Mattice-Val Côté")].government == (
        "Township of Mattice-Val Côté"
    )
    assert by_name[("region", "Cochrane")].government is None
    assert by_name[("municipality", "Cochrane")].government == "Town of Cochrane"
    # Separated from Frontenac.
    assert by_name[("municipality", "Kingston")].parent == "Ontario"
    assert by_name[("municipality", "Kingston")].homepage == "http://www.cityofkingston.ca/"
    sudbury = by_name[("municipality", "Greater Sudbury")]
    assert [(alias.text, alias.language) for alias in sudbury.aliases] == [("Grand Sudbury", "fr")]
    assert by_name[("region", "Stormont, Dundas and Glengarry")].government == (
        "United Counties of Stormont, Dundas and Glengarry"
    )


def test_the_overrides_apply(by_name: dict[tuple[str, str], PlaceEntry], entries: list[PlaceEntry]):
    codes = {entry.code.value for entry in entries}
    assert set(ontario_places.OVERRIDES) <= codes
    tarbutt = by_name[("municipality", "Tarbutt")]
    assert tarbutt.code.value == "3557014"
    assert tarbutt.government == "Township of Tarbutt"
    assert tarbutt.homepage == "https://tarbutt.ca/"
    assert [alias.text for alias in tarbutt.aliases] == ["Tarbutt and Tarbutt Additional"]
    for code, fields in ontario_places.OVERRIDES.items():
        if "parent" in fields:
            entry = next(entry for entry in entries if entry.code.value == code)
            assert entry.parent == fields["parent"]
