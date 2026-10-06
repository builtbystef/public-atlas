"""The seeds: Python modules of plain dictionaries, validated by `schemas.py` and written by
`service.seed`. `shared.py` is what every country starts from; one module per country holds
the rest. `public-atlas seed <name>` fills the tables, and from then on the tables are the
truth."""

from typing import Any

from public_atlas.modules.countries.seeds import canada

# By the name the command takes.
SEEDS: dict[str, dict[str, Any]] = {"canada": canada.SEED}

__all__ = ["SEEDS"]
