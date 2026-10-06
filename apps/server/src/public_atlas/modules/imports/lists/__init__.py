"""One module per official list, the only code written to add one. Each holds `COUNTRY`,
`SOURCES`, `OVERRIDES` and `entries()`, and knows everything about its list and nothing about
the database. `public-atlas load-list <name>` loads one by the name it is listed under here."""

from types import ModuleType

from public_atlas.modules.imports.lists import ontario_places

# By the name the command takes.
LISTS: dict[str, ModuleType] = {"ontario_places": ontario_places}

__all__ = ["LISTS"]
