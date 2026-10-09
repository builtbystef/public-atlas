"""One module per official list, the only code written to add one, in a tree by country and
region: `canada/ontario/places.py`, `us/municipalities.py`. Each holds `COUNTRY`, `SOURCES`,
`OVERRIDES` and `entries()`, and knows everything about its list and nothing about the
database. A list's name is its path under this package with slashes (`canada/ontario/places`);
`public-atlas load-list <name>` loads one by it. Nothing is registered by hand: `LISTS` is
built by walking the package for modules that define `entries`. Shared readers sit beside the
modules that use them (`canada/statcan.py`) and define no `entries`."""

import importlib
import pkgutil
from types import ModuleType

__all__ = ["LISTS", "list_name"]


def list_name(module_name: str) -> str:
    """A list's name from its module's dotted name: `canada/ontario/places` for
    `public_atlas.modules.imports.lists.canada.ontario.places`. A module outside this package
    (a test's) is named by its last segment."""
    prefix = f"{__name__}."
    if module_name.startswith(prefix):
        return module_name.removeprefix(prefix).replace(".", "/")
    return module_name.rsplit(".", 1)[-1]


def _discover() -> dict[str, ModuleType]:
    found: dict[str, ModuleType] = {}
    for info in pkgutil.walk_packages(__path__, prefix=f"{__name__}."):
        if info.ispkg:
            continue
        module = importlib.import_module(info.name)
        if callable(getattr(module, "entries", None)) and hasattr(module, "SOURCES"):
            found[list_name(info.name)] = module
    return dict(sorted(found.items()))


# By the name the command takes.
LISTS: dict[str, ModuleType] = _discover()
