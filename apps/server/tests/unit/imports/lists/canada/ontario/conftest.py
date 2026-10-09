"""What the Ontario lists' rule tests share: the country's rules, the cached files of a list
(skipped when they are not cached and cannot be fetched), and the names of the places the
places list loads, which the other lists attach their bodies to."""

from collections.abc import Callable
from types import ModuleType

import pytest

from public_atlas.config import Settings
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import canada
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import Citation, Code, PlaceEntry
from public_atlas.modules.imports.lists.canada.ontario import places as ontario_places


@pytest.fixture(scope="package")
def rules() -> countries.CountryRules:
    return countries.rules_from_seed(canada.SEED)


def open_sources(module: ModuleType) -> dict[str, files.OpenedFile]:
    cache_dir = Settings().lists_cache_dir
    try:
        return {source.name: files.open_file(source, cache_dir) for source in module.SOURCES}
    except files.ListFileError as exc:
        pytest.skip(f"the list's files are not cached and could not be fetched: {exc}")


@pytest.fixture(scope="package")
def places(rules: countries.CountryRules) -> list[PlaceEntry]:
    """What `canada/ontario/places` loads."""
    return ontario_places.entries(open_sources(ontario_places), rules)


@pytest.fixture(scope="package")
def place_names(places: list[PlaceEntry]) -> frozenset[str]:
    """The names of the loaded places and the province."""
    return frozenset({ontario_places.PROVINCE, *(entry.name for entry in places)})


@pytest.fixture(scope="package")
def is_loaded_place(
    place_names: frozenset[str], rules: countries.CountryRules
) -> Callable[[str], bool]:
    """Whether a name is a loaded place's, compared as the loader compares names: "Sault Ste
    Marie" is "Sault Ste. Marie"."""
    forms: set[str] = set()
    for name in place_names:
        forms |= rules.naming.forms(name)
    return lambda name: bool(rules.naming.forms(name) & forms)


@pytest.fixture(scope="package")
def municipality_names(places: list[PlaceEntry]) -> frozenset[str]:
    return frozenset(entry.name for entry in places if entry.level == ontario_places.MUNICIPALITY)


@pytest.fixture(scope="package")
def region_names(places: list[PlaceEntry]) -> frozenset[str]:
    return frozenset(entry.name for entry in places if entry.level == ontario_places.REGION)


@pytest.fixture(scope="package")
def find_places(
    places: list[PlaceEntry], rules: countries.CountryRules
) -> Callable[[str, str | None, str | None], list[PlaceEntry]]:
    """The loaded places that go by a name, as the loader finds them for an institution: at the
    level when one is given, under the parent when one is given, the province included."""
    province = PlaceEntry(
        name=ontario_places.PROVINCE,
        level="province_territory",
        parent="Canada",
        code=Code(scheme="statcan_sgc", value=ontario_places.PROVINCE_CODE),
        citations={"place": Citation(source="seed", line=1)},
    )
    loaded = [province, *places]
    forms_of = {entry.name: rules.naming.forms(entry.name) for entry in loaded}

    def find(name: str, level: str | None, parent: str | None) -> list[PlaceEntry]:
        forms = rules.naming.forms(name)
        found = [
            entry
            for entry in loaded
            if forms & forms_of[entry.name] and (level is None or entry.level == level)
        ]
        if parent is not None and len(found) > 1:
            wanted = rules.naming.forms(parent)
            found = [
                entry
                for entry in found
                if entry.parent is not None and rules.naming.forms(entry.parent) & wanted
            ]
        return found

    return find
