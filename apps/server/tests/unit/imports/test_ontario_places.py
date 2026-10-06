"""The Ontario places list: `entries()` on the cached files keeps every rule, and a few places
show the rules a count cannot. The files are fetched into the lists cache when they are not
there; without the network the module's tests are skipped."""

import pytest

from public_atlas.config import Settings
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import canada
from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists import ontario_places

REGIONS = 40
MUNICIPALITIES = 414
GOVERNMENTS = 444
DISTRICTS = 10
# Three governments have no link in the directory.
HOMEPAGES = 441


@pytest.fixture(scope="module")
def rules() -> countries.CountryRules:
    return countries.rules_from_seed(canada.SEED)


@pytest.fixture(scope="module")
def opened() -> dict[str, files.OpenedFile]:
    cache_dir = Settings().lists_cache_dir
    try:
        return {
            source.name: files.open_source(source, cache_dir) for source in ontario_places.SOURCES
        }
    except files.ListFileError as exc:
        pytest.skip(f"the list's files are not cached and could not be fetched: {exc}")


@pytest.fixture(scope="module")
def entries(opened: dict[str, files.OpenedFile], rules: countries.CountryRules) -> list[PlaceEntry]:
    return ontario_places.entries(opened, rules)


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


def test_every_entry_has_its_code_population_and_a_government_name_the_naming_rules_give(
    entries: list[PlaceEntry], rules: countries.CountryRules, opened: dict[str, files.OpenedFile]
):
    naming = rules.naming
    register = opened[ontario_places.POPULATION.name]
    for entry in entries:
        assert entry.code.scheme is IdentifierScheme.STATCAN_SGC
        assert entry.code.value.isdigit()
        assert entry.code.value.startswith("35")
        (population,) = entry.figures
        assert (population.name, population.year) == (MetricName.POPULATION, 2021)
        assert population.value > 0
        # The cited line names the place and carries its code.
        line = register.line(entry.citations["place"].line)
        assert entry.code.value in line
        assert any(name in line for name in (entry.name, *(a.text for a in entry.aliases)))
        if entry.government is not None:
            # "City of Kingston" governs "Kingston"; "Haldimand County" governs itself; the
            # designator in "Whitewater Region" is the name's own.
            assert naming.core(entry.government) in (
                naming.core(entry.name),
                naming.key(entry.name),
            ), entry.name
        else:
            assert entry.level == "region"
            assert entry.homepage is None


def test_every_homepage_is_the_directorys_link(
    entries: list[PlaceEntry], opened: dict[str, files.OpenedFile]
):
    directory = opened[ontario_places.DIRECTORY.name]
    for entry in entries:
        if entry.homepage is None:
            continue
        assert entry.homepage.startswith(("http://", "https://"))
        citation = entry.citations["homepage"]
        assert citation.source == ontario_places.DIRECTORY.name
        assert citation == entry.citations["government"]
        line = directory.line(citation.line)
        host = entry.homepage.removeprefix("http://").removeprefix("https://").rstrip("/")
        assert host.lower() in line.lower()
        assert entry.government is not None


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
