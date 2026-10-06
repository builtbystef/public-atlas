"""The price list (`prices.toml`, product data) and the cost of one call."""

import logging
import tomllib
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from pathlib import Path

from public_atlas.modules.assignments.models import UsageKind

logger = logging.getLogger(__name__)

PRICES_FILE = Path(__file__).with_name("prices.toml")
MILLION = 1_000_000


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """US dollars per million tokens."""

    input: Decimal
    cached_input: Decimal
    output: Decimal


@dataclass(frozen=True, slots=True)
class Prices:
    models: dict[str, ModelPrice]
    # US dollars per request, by engine.
    searches: dict[str, Decimal]

    def cost(
        self, kind: UsageKind, provider: str, *, units: int, cached_units: int, output_units: int
    ) -> Decimal | None:
        """The cost of one call, or None for a provider the list does not price. For a model,
        `units` is every token (input and output), `cached_units` the input served from the
        cache and `output_units` the output. For a search, `units` is the requests."""
        if kind is UsageKind.SEARCH:
            price = self.searches.get(provider)
            return None if price is None else price * units
        model = self.models.get(provider)
        if model is None:
            return None
        uncached = max(units - output_units - cached_units, 0)
        per_million = (
            uncached * model.input + cached_units * model.cached_input + output_units * model.output
        )
        return per_million / MILLION


@cache
def load_prices(path: Path = PRICES_FILE) -> Prices:
    with path.open("rb") as file:
        raw = tomllib.load(file)
    return Prices(
        models={
            name: ModelPrice(
                input=Decimal(price["input"]),
                cached_input=Decimal(price["cached_input"]),
                output=Decimal(price["output"]),
            )
            for name, price in raw.get("model", {}).items()
        },
        searches={name: Decimal(price["request"]) for name, price in raw.get("search", {}).items()},
    )
