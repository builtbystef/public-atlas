"""The lists package: modules are found by walking it and named by their path, the loader
names a list the same way, and the manifest is read from the modules."""

from pathlib import Path
from types import ModuleType

from public_atlas.modules.imports import service
from public_atlas.modules.imports.entries import Citation, Code, PlaceEntry
from public_atlas.modules.imports.files import Format, ListFile, Retrieval
from public_atlas.modules.imports.lists import LISTS, list_name
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.ontario import places
from public_atlas.modules.imports.lists.us import (
    census,
    government_units,
    governments,
    loaded,
    municipalities,
    school_districts,
    special_districts,
    states_counties,
)

NAMES = [
    "canada/alberta/places",
    "canada/british_columbia/places",
    "canada/federal",
    "canada/manitoba/places",
    "canada/new_brunswick/places",
    "canada/newfoundland/places",
    "canada/nova_scotia/places",
    "canada/ontario/agencies",
    "canada/ontario/conservation_authorities",
    "canada/ontario/fippa_bodies",
    "canada/ontario/health_units",
    "canada/ontario/libraries",
    "canada/ontario/places",
    "canada/ontario/police_boards",
    "canada/ontario/school_boards",
    "canada/ontario/service_managers",
    "canada/pei/places",
    "canada/quebec/places",
    "canada/saskatchewan/places",
    "canada/territories/places",
    "us/federal",
    "us/government_units",
    "us/municipalities",
    "us/school_districts",
    "us/special_districts",
    "us/states_counties",
    "us/transit",
    "us/universities",
]


def test_lists_are_found_by_walking_the_package_and_named_by_their_path():
    assert list(LISTS) == NAMES
    assert LISTS["canada/ontario/places"] is places
    assert LISTS["us/states_counties"] is states_counties
    assert LISTS["us/municipalities"] is municipalities
    assert LISTS["us/government_units"] is government_units
    assert LISTS["us/school_districts"] is school_districts
    assert LISTS["us/special_districts"] is special_districts
    # A shared reader defines no `entries`, so it is not a list.
    assert statcan not in LISTS.values()
    assert census not in LISTS.values()
    assert governments not in LISTS.values()
    assert loaded not in LISTS.values()

    for module in LISTS.values():
        assert module.COUNTRY in ("CA", "US")
        assert isinstance(module.OVERRIDES, dict)
        assert callable(module.entries)
        assert [source.name for source in module.SOURCES]


def test_a_list_is_named_by_its_path_under_the_package():
    assert list_name(places.__name__) == "canada/ontario/places"
    assert list_name("public_atlas.modules.imports.lists.us.municipalities") == "us/municipalities"
    assert service.module_name(places) == "canada/ontario/places"
    # A module made for a test, outside the package, keeps its last segment.
    assert service.module_name(ModuleType("tests.tiny_places")) == "tiny_places"


def _module(name: str, *sources: ListFile) -> ModuleType:
    """A list module under the package, with these sources and no entries."""
    module = ModuleType(f"public_atlas.modules.imports.lists.{name}")
    module.__dict__.update(
        COUNTRY="CA", SOURCES=sources, OVERRIDES={}, entries=lambda _files, _rules: []
    )
    return module


def test_the_manifest_lists_the_fetched_urls_with_hashes_and_the_manual_steps():
    """An overview counts the lists and their files by country, then a fetched file is listed
    with its URL and hash, a manual one with where to put it and the steps to get it, and a
    file two lists read is described once."""
    fetched = ListFile(
        name="population",
        title="Population counts",
        url="https://example.test/population.csv",
        format=Format.CSV,
        sha256="a" * 64,
    )
    export = ListFile(
        name="alberta_contacts",
        title="Local Authority Contact Information",
        url="https://visualizations.alberta.ca/dashboard",
        format=Format.SPREADSHEET,
        retrieval=Retrieval.MANUAL,
        instructions="Open the dashboard.\nExport the table, all rows, Excel (427 rows).",
        filename_override="alberta-local-authority-contacts.xlsx",
        min_rows=400,
    )
    text = service.manifest(
        Path("/cache"),
        {
            "canada/alberta/places": _module("canada.alberta.places", fetched, export),
            "canada/manitoba/places": _module("canada.manitoba.places", fetched),
        },
    )
    assert text.startswith(
        "Official lists: 2 lists reading 2 files (1 fetched and pinned by hash, 1 collected by "
        "hand)\n\ncanada/ (2 lists)\n"
        "  alberta/places     2 files  example.test, visualizations.alberta.ca\n"
        "  manitoba/places    1 file   example.test\n"
    )
    assert "\ncanada/alberta/places\n" in text
    assert "  population (fetched)\n    Population counts\n" in text
    assert "    https://example.test/population.csv\n" in text
    assert f"    sha256 {'a' * 64}\n" in text
    assert (
        "  alberta_contacts (collected by hand)\n    Local Authority Contact Information\n" in text
    )
    assert "    put it at /cache/alberta_contacts.xlsx\n" in text
    assert "    at least 400 rows\n" in text
    assert "    steps:\n      Open the dashboard.\n      Export the table, all rows, Excel" in text
    rule = "─" * 100
    assert text.endswith(
        f"\ncanada/manitoba/places\n{rule}\n\n  population: as under canada/alberta/places"
    )
    none = service.manifest(Path("/cache"), {"x/y": _module("x.y")})
    assert none.startswith("Official lists: 1 list reading 0 files")
    assert none.endswith(f"\nx/y\n{rule}\n  no files")


def test_an_override_matches_an_entry_by_code_name_or_alias():
    citation = Citation(source="x", line=2)
    entry = PlaceEntry(
        name="Oakville",
        aliases=(),
        level="municipality",
        parent="Ontario",
        code=Code(scheme="statcan_sgc", value="3598001"),
        citations={"place": citation},
    )
    overrides = {"3598001": {}, "Oakville": {}, "3598999": {}, "Pine": {}}
    assert service.idle_overrides(overrides, [entry]) == ["3598999", "Pine"]


def test_an_override_that_dissolves_its_entry_is_expected_to_match_nothing():
    overrides = {"3598999": {"dissolved": "2023-01-01", "reason": "merged"}, "Pine": {}}
    assert service.idle_overrides(overrides, []) == ["Pine"]
