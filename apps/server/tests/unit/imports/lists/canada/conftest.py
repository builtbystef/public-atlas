"""What Canada's lists' rule tests share: the country's rules and the cached files of a list
(fetched into the cache when they are not there; skipped when they cannot be). The provincial
packages have conftests of their own for the places their lists attach bodies to."""

from types import ModuleType

import pytest

from public_atlas.config import Settings
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import canada
from public_atlas.modules.imports import files


@pytest.fixture(scope="package")
def rules() -> countries.CountryRules:
    return countries.rules_from_seed(canada.SEED)


def open_sources(module: ModuleType) -> dict[str, files.OpenedFile]:
    cache_dir = Settings().lists_cache_dir
    try:
        return {source.name: files.open_file(source, cache_dir) for source in module.SOURCES}
    except files.ListFileError as exc:
        pytest.skip(f"the list's files are not cached and could not be fetched: {exc}")
