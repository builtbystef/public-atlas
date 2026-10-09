"""The libraries list: `entries()` on the cached statistics keeps every rule, the counts are
pinned, and every board sits at one loaded place."""

from collections.abc import Callable
from urllib.parse import urlsplit

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import InstitutionEntry, PlaceEntry
from public_atlas.modules.imports.lists.canada.ontario import libraries
from public_atlas.modules.imports.lists.canada.ontario.communities import Location

from .conftest import open_sources

PUBLIC_AND_UNION = 241
COUNTY = 12
FIRST_NATIONS = 33
LOCAL_SERVICES_BOARDS = 4
BOARDS = PUBLIC_AND_UNION + COUNTY + FIRST_NATIONS + LOCAL_SERVICES_BOARDS
CONTRACTING = 52 + 12
# Two rows give no address, two a name or an email address, and seven a social network page.
HOMEPAGES = BOARDS - 11


@pytest.fixture(scope="module")
def opened() -> dict[str, files.OpenedFile]:
    return open_sources(libraries)


@pytest.fixture(scope="module")
def entries(
    opened: dict[str, files.OpenedFile], rules: countries.CountryRules
) -> list[InstitutionEntry]:
    return libraries.entries(opened, rules)


@pytest.fixture(scope="module")
def by_name(entries: list[InstitutionEntry]) -> dict[str, InstitutionEntry]:
    return {entry.name: entry for entry in entries}


@pytest.fixture(scope="module")
def by_shorthand(entries: list[InstitutionEntry]) -> dict[str, InstitutionEntry]:
    return {alias.text: entry for entry in entries for alias in entry.aliases}


def test_the_counts(entries: list[InstitutionEntry], opened: dict[str, files.OpenedFile]) -> None:
    rows = opened[libraries.STATISTICS.name].rows
    assert len(rows) == BOARDS + CONTRACTING + 1
    assert sum(1 for row in rows if row[libraries.TYPE] in libraries.CONTRACTING_TYPES) == (
        CONTRACTING
    )
    assert len(entries) == BOARDS
    assert sum(1 for entry in entries if entry.homepage) == HOMEPAGES
    assert all(entry.institution_type == "library" for entry in entries)
    names = [entry.name for entry in entries]
    assert len(set(names)) == len(names)
    assert names == sorted(names, key=libraries.name_key)


def test_every_entry_cites_its_row_and_sits_at_one_loaded_place(
    entries: list[InstitutionEntry],
    opened: dict[str, files.OpenedFile],
    find_places: Callable[[str, str | None, str | None], list[PlaceEntry]],
) -> None:
    statistics = opened[libraries.STATISTICS.name]
    for entry in entries:
        citation = entry.citations["institution"]
        assert citation.source == libraries.STATISTICS.name
        line = statistics.line(citation.line)
        shorthand = entry.aliases[0].text if entry.aliases else entry.name
        assert shorthand in line.replace(" - ", "-"), entry.name
        assert entry.name.endswith("Public Library"), entry.name
        assert " & " not in entry.name
        assert len(entry.aliases) <= 1
        assert entry.parent_institution is None
        assert entry.served_places == ()
        found = find_places(entry.place, entry.place_level, entry.place_parent)
        assert len(found) == 1, (entry.name, entry.place, entry.place_level)
        if entry.homepage is not None:
            parts = urlsplit(entry.homepage)
            assert parts.scheme in ("http", "https")
            assert parts.netloc in line.lower(), entry.name
            assert "facebook" not in parts.netloc
            assert entry.citations["homepage"] == citation


def _shorthand(entry: InstitutionEntry) -> str:
    """The file's name of the board: its alias, or its name when the two are one."""
    return entry.aliases[0].text if entry.aliases else entry.name


def test_the_types_place_the_boards(entries: list[InstitutionEntry]) -> None:
    first_nations = [entry for entry in entries if _shorthand(entry) in libraries.FIRST_NATIONS]
    assert len(first_nations) == FIRST_NATIONS
    for entry in first_nations:
        assert "First Nation" in entry.name or entry.name in (
            "Six Nations Public Library",
            "Biigtigong Nishnaabeg Public Library",
        ), entry.name
    by_hand = {*libraries.FIRST_NATIONS, *libraries.PLACES}
    counties = [
        entry
        for entry in entries
        if entry.place_level == "region" and _shorthand(entry) not in by_hand
    ]
    assert len(counties) == COUNTY
    assert all(entry.place_parent == "Ontario" for entry in counties)
    boards = [
        entry
        for entry in entries
        if _shorthand(entry)
        in {
            "Britt Area",
            "Gogama LSB",
            "Phelps",
            "Loring, Port Loring and District Local Services Board",
        }
    ]
    assert len(boards) == LOCAL_SERVICES_BOARDS
    assert all(entry.place_level == "region" for entry in boards)


def test_the_names_and_places_that_show_the_rules(
    by_name: dict[str, InstitutionEntry], by_shorthand: dict[str, InstitutionEntry]
) -> None:
    assert by_shorthand["Addington Highlands Twp"].name == "Addington Highlands Public Library"
    assert by_shorthand["Addington Highlands Twp"].place == "Addington Highlands"
    assert by_shorthand["Kenora City"].name == "Kenora Public Library"
    assert by_shorthand["Kenora City"].place_level == "municipality"
    cochrane = by_shorthand["Cochrane Public Library Board"]
    assert (cochrane.name, cochrane.place, cochrane.place_level) == (
        "Cochrane Public Library",
        "Cochrane",
        "municipality",
    )
    hamilton = by_shorthand["Hamilton"]
    assert (hamilton.name, hamilton.place, hamilton.place_parent) == (
        "Hamilton Public Library",
        "Hamilton",
        "Ontario",
    )
    assert by_shorthand["Cavan Monaghan Public Library Board, Township of"].name == (
        "Cavan Monaghan Public Library"
    )
    assert by_shorthand["Cavan Monaghan Public Library Board, Township of"].place == (
        "Cavan Monaghan"
    )
    assert by_shorthand["Kawartha Lakes, City of"].place == "Kawartha Lakes"
    assert by_shorthand["Severn Township Library"].name == "Severn Public Library"
    assert by_shorthand["Scugog Memorial"].name == "Scugog Memorial Public Library"
    assert by_shorthand["Scugog Memorial"].place == "Scugog"
    assert by_shorthand["Kearney & Area"].name == "Kearney and Area Public Library"
    assert by_shorthand["Kearney & Area"].place == "Kearney"
    assert by_shorthand["Head, Clara & Maria"].name == "Head, Clara and Maria Public Library"
    assert by_shorthand["Elizabethtown-Kitley"].name == "Elizabethtown-Kitley Public Library"
    assert by_shorthand["Southgate Twp."].place == "Southgate"
    bonnechere = by_shorthand["Bonnechere Union"]
    assert (bonnechere.name, bonnechere.place) == (
        "Bonnechere Union Public Library",
        "Bonnechere Valley",
    )
    assert by_shorthand["Owen Sound & North Grey Union"].name == (
        "Owen Sound and North Grey Union Public Library"
    )
    perth = by_shorthand["Perth and District Union"]
    assert (perth.name, perth.place, perth.place_level, perth.place_parent) == (
        "Perth and District Union Public Library",
        "Perth",
        "municipality",
        "Lanark",
    )
    bruce = by_shorthand["Bruce County"]
    assert (bruce.name, bruce.place, bruce.place_level) == (
        "Bruce County Public Library",
        "Bruce County",
        "region",
    )
    essex = by_shorthand["Essex County"]
    assert (essex.place, essex.place_level) == ("Essex County", "region")
    assert by_shorthand["Waterloo City"].place_level == "municipality"
    assert by_shorthand["Waterloo Region"].place_level == "region"
    assert by_shorthand["Middlesex County Library"].name == "Middlesex County Public Library"
    alderville = by_shorthand["Alderville FN"]
    assert (alderville.name, alderville.place, alderville.place_level) == (
        "Alderville First Nation Public Library",
        "Northumberland",
        "region",
    )
    assert by_shorthand["Six Nations"].name == "Six Nations Public Library"
    assert by_shorthand["Six Nations"].place == "Brant"
    assert by_name["Beausoleil First Nation Public Library"].name == (
        "Beausoleil First Nation Public Library"
    )
    assert by_shorthand["Gogama LSB"].name == "Gogama Public Library"
    assert by_shorthand["Gogama LSB"].place == "Sudbury"
    assert by_name["Phelps Public Library"].place == "Nipissing"
    assert by_shorthand["Prince Edward County"].place == "Prince Edward County"
    assert by_shorthand["Brant County"].place == "Brant County"
    assert by_shorthand["Blue Mountains"].place == "The Blue Mountains"


def test_the_homepages_that_show_the_rules(by_shorthand: dict[str, InstitutionEntry]) -> None:
    assert by_shorthand["Addington Highlands Twp"].homepage == (
        "http://www.addingtonhighlandspubliclibrary.ca/"
    )
    assert by_shorthand["Whitchurch-Stouffville"].homepage == "http://www.wsplibrary.ca/"
    assert by_shorthand["Quinte West"].homepage == "http://www.qwpl.ca/"
    assert by_shorthand["South River-Machar Union"].homepage is None
    assert by_shorthand["Gogama LSB"].homepage is None
    assert by_shorthand["Britt Area"].homepage is None
    assert by_shorthand["Chippewas of Kettle & Stony Point FN"].homepage is None
    assert by_shorthand["Biigtigong Nishnaabeg"].homepage is None
    assert by_shorthand["Englehart"].homepage == (
        "https://olsn.ent.sirsidynix.net/client/en_US/englehart/?dt=list"
    )


def test_the_overrides_apply(by_name: dict[str, InstitutionEntry]) -> None:
    assert by_name["Kingston Frontenac Public Library"].place == "Kingston"
    assert by_name["Atikameksheng Anishnawbek First Nation Public Library"].place == (
        "Greater Sudbury"
    )
    assert by_name["Mattice-Val Cote Public Library"].place == "Mattice-Val Côté"
    assert by_name["St. Charles Public Library"].place == "St.-Charles"
    assert by_name["La Nation Public Library"].place == "The Nation"
    shorthands = {_shorthand(entry) for entry in by_name.values()}
    for listed in (*libraries.OVERRIDES, *libraries.PLACES, *libraries.FIRST_NATIONS):
        assert listed in shorthands, listed


def test_the_hand_tables_name_loaded_places(
    find_places: Callable[[str, str | None, str | None], list[PlaceEntry]],
) -> None:
    for where in (*libraries.PLACES.values(), *libraries.FIRST_NATIONS.values()):
        assert isinstance(where, Location)
        assert len(find_places(where.place, where.level, where.parent)) == 1, where
