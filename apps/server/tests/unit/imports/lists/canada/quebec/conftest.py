"""What the Quebec lists' rule tests share: the cached files of a list (skipped when they are
not cached and cannot be fetched), the places the places list loads, which the other lists
attach their bodies to, and a lookup that finds a place as the loader does."""

from collections.abc import Callable
from types import ModuleType

import pytest

from public_atlas.config import Settings
from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import Citation, Code, InstitutionEntry, PlaceEntry
from public_atlas.modules.imports.lists.canada.quebec import places as quebec_places


def open_sources(module: ModuleType) -> dict[str, files.OpenedFile]:
    cache_dir = Settings().lists_cache_dir
    try:
        return {source.name: files.open_file(source, cache_dir) for source in module.SOURCES}
    except files.ListFileError as exc:
        pytest.skip(f"the list's files are not cached and could not be fetched: {exc}")


@pytest.fixture(scope="package")
def quebec_entries(rules: countries.CountryRules) -> list[PlaceEntry | InstitutionEntry]:
    """What `canada/quebec/places` loads."""
    return quebec_places.entries(open_sources(quebec_places), rules)


@pytest.fixture(scope="package")
def places(quebec_entries: list[PlaceEntry | InstitutionEntry]) -> list[PlaceEntry]:
    return [entry for entry in quebec_entries if isinstance(entry, PlaceEntry)]


@pytest.fixture(scope="package")
def find_places(
    places: list[PlaceEntry], rules: countries.CountryRules
) -> Callable[[str, str | None, str | None], list[PlaceEntry]]:
    """The loaded places that go by a name, as the loader finds them for an institution or a
    served place: at the level when one is given, under the parent when one is given, the
    province included."""
    province = PlaceEntry(
        name=quebec_places.PROVINCE,
        level=quebec_places.PROVINCE_LEVEL,
        parent="Canada",
        code=Code(scheme="statcan_sgc", value=quebec_places.PROVINCE_CODE),
        citations={"place": Citation(source="seed", line=1)},
    )
    loaded = [province, *places]
    forms_of = {
        id(entry): rules.naming.forms(entry.name)
        | {form for alias in entry.aliases for form in rules.naming.forms(alias.text)}
        for entry in loaded
    }

    def find(name: str, level: str | None, parent: str | None) -> list[PlaceEntry]:
        forms = rules.naming.forms(name)
        found = [
            entry
            for entry in loaded
            if forms & forms_of[id(entry)] and (level is None or entry.level == level)
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
