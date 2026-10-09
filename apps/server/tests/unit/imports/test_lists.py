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


def test_lists_are_found_by_walking_the_package_and_named_by_their_path():
    assert LISTS["canada/ontario/places"] is places
    assert list(LISTS) == sorted(LISTS)
    # A shared reader defines no `entries`, so it is not a list.
    assert statcan not in LISTS.values()
    for name, module in LISTS.items():
        assert "/" in name
        assert module.COUNTRY
        assert module.SOURCES
        assert isinstance(module.OVERRIDES, dict)
        assert callable(module.entries)


def test_a_list_is_named_by_its_path_under_the_package():
    assert list_name(places.__name__) == "canada/ontario/places"
    assert list_name("public_atlas.modules.imports.lists.us.municipalities") == "us/municipalities"
    assert service.module_name(places) == "canada/ontario/places"
    # A module made for a test, outside the package, keeps its last segment.
    assert service.module_name(ModuleType("tests.tiny_places")) == "tiny_places"


def _module(name: str, *sources: ListFile) -> ModuleType:
    module = ModuleType(f"public_atlas.modules.imports.lists.{name}")
    module.__dict__.update(
        COUNTRY="CA", SOURCES=sources, OVERRIDES={}, entries=lambda _files, _rules: []
    )
    return module


def test_the_manifest_lists_the_fetched_urls_with_hashes_and_the_manual_steps():
    text = service.manifest(Path("/cache"))
    fetched = sum(len(module.SOURCES) for module in LISTS.values())
    assert text.startswith(f"Fetched files ({fetched})")
    for file in places.SOURCES:
        assert f"canada/ontario/places/{file.name}: {file.title}" in text
        assert f"  {file.url}" in text
        assert f"  sha256 {file.sha256}" in text
    assert text.endswith("Manual files (0)\n  none")

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
        Path("/cache"), {"canada/alberta/places": _module("canada.alberta.places", export)}
    )
    assert "Fetched files (0)\n  none" in text
    assert "Manual files (1)" in text
    assert "canada/alberta/places/alberta_contacts: Local Authority Contact Information" in text
    assert "  put it at /cache/alberta_contacts.xlsx" in text
    assert "  at least 400 rows" in text
    assert "  Open the dashboard.\n  Export the table, all rows, Excel (427 rows)." in text


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
