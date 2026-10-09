"""What the United States lists' rule tests share: the country's rules and the cached files of
a list (fetched into the cache when they are not there; skipped when they cannot be). A file
several lists read is opened once for the package."""

from types import ModuleType

import pytest

from public_atlas.config import Settings
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import united_states
from public_atlas.modules.imports import files
from public_atlas.modules.imports.lists.us import (
    government_units,
    municipalities,
    school_districts,
    special_districts,
    states_counties,
)

# By source name, once opened.
_opened: dict[str, files.OpenedFile] = {}


@pytest.fixture(scope="package")
def rules() -> countries.CountryRules:
    return countries.rules_from_seed(united_states.SEED)


def open_sources(module: ModuleType) -> dict[str, files.OpenedFile]:
    cache_dir = Settings().lists_cache_dir
    try:
        for source in module.SOURCES:
            if source.name not in _opened:
                _opened[source.name] = files.open_file(source, cache_dir)
    except files.ListFileError as exc:
        pytest.skip(f"the list's files are not cached and could not be fetched: {exc}")
    return {source.name: _opened[source.name] for source in module.SOURCES}


@pytest.fixture(scope="package")
def states_counties_files() -> dict[str, files.OpenedFile]:
    return open_sources(states_counties)


@pytest.fixture(scope="package")
def municipalities_files() -> dict[str, files.OpenedFile]:
    return open_sources(municipalities)


@pytest.fixture(scope="package")
def government_units_files() -> dict[str, files.OpenedFile]:
    return open_sources(government_units)


@pytest.fixture(scope="package")
def school_districts_files() -> dict[str, files.OpenedFile]:
    return open_sources(school_districts)


@pytest.fixture(scope="package")
def special_districts_files() -> dict[str, files.OpenedFile]:
    return open_sources(special_districts)
