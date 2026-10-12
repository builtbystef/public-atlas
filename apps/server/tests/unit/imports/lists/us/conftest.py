"""What the United States lists' rule tests share: the country's rules and the files of a
list, from the fixtures every list's tests share. A file several lists read is opened once for
the package."""

from collections.abc import Callable
from types import ModuleType

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import united_states
from public_atlas.modules.imports import files
from public_atlas.modules.imports.lists.us import (
    federal,
    government_units,
    municipalities,
    school_districts,
    special_districts,
    states_counties,
    transit,
    universities,
)

# By source name, once opened.
_opened: dict[str, files.OpenedFile] = {}


@pytest.fixture(scope="package")
def rules() -> countries.CountryRules:
    return countries.rules_from_seed(united_states.SEED)


def open_sources(
    module: ModuleType, open_list_file: Callable[[files.ListFile], files.OpenedFile]
) -> dict[str, files.OpenedFile]:
    for source in module.SOURCES:
        if source.name not in _opened:
            _opened[source.name] = open_list_file(source)
    return {source.name: _opened[source.name] for source in module.SOURCES}


@pytest.fixture(scope="package")
def states_counties_files(open_list_file) -> dict[str, files.OpenedFile]:
    return open_sources(states_counties, open_list_file)


@pytest.fixture(scope="package")
def municipalities_files(open_list_file) -> dict[str, files.OpenedFile]:
    return open_sources(municipalities, open_list_file)


@pytest.fixture(scope="package")
def government_units_files(open_list_file) -> dict[str, files.OpenedFile]:
    return open_sources(government_units, open_list_file)


@pytest.fixture(scope="package")
def school_districts_files(open_list_file) -> dict[str, files.OpenedFile]:
    return open_sources(school_districts, open_list_file)


@pytest.fixture(scope="package")
def special_districts_files(open_list_file) -> dict[str, files.OpenedFile]:
    return open_sources(special_districts, open_list_file)


@pytest.fixture(scope="package")
def federal_files(open_list_file) -> dict[str, files.OpenedFile]:
    return open_sources(federal, open_list_file)


@pytest.fixture(scope="package")
def universities_files(open_list_file) -> dict[str, files.OpenedFile]:
    return open_sources(universities, open_list_file)


@pytest.fixture(scope="package")
def transit_files(open_list_file) -> dict[str, files.OpenedFile]:
    return open_sources(transit, open_list_file)
