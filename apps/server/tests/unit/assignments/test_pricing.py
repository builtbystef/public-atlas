"""The price list and the cost of one call."""

from decimal import Decimal

from public_atlas.modules.assignments.models import UsageKind
from public_atlas.modules.assignments.pricing import (
    PRICES_FILE,
    ModelPrice,
    Prices,
    load_prices,
)

# A price list of the test's own, so the arithmetic is pinned apart from `prices.toml`: $2 per
# million uncached input tokens, $0.10 per million cached, $10 per million output.
BY_HAND = Prices(
    models={"m": ModelPrice(input=Decimal(2), cached_input=Decimal("0.1"), output=Decimal(10))},
    searches={"s": Decimal("0.005")},
)


def model_cost(units: int, cached: int, output: int) -> Decimal | None:
    return BY_HAND.cost(UsageKind.MODEL, "m", units=units, cached_units=cached, output_units=output)


def test_the_price_list_is_a_data_file_with_the_models_the_agent_runs_on():
    prices = load_prices()
    assert PRICES_FILE.name == "prices.toml"
    assert "gpt-6-luna" in prices.models
    assert prices.searches["brave"] == Decimal("0.005")


def test_a_model_call_is_priced_by_its_uncached_cached_and_output_tokens():
    prices = load_prices()
    # 1,000,000 tokens: 700,000 uncached input, 200,000 cached input, 100,000 output.
    cost = prices.cost(
        UsageKind.MODEL, "gpt-6-luna", units=1_000_000, cached_units=200_000, output_units=100_000
    )
    assert cost == Decimal("0.70") * Decimal("0.10") + Decimal("0.2") * Decimal("0.01") + Decimal(
        "0.1"
    ) * Decimal("0.50")


def test_a_search_is_priced_per_request_and_an_unknown_provider_has_no_price():
    prices = load_prices()
    assert prices.cost(UsageKind.SEARCH, "brave", units=3, cached_units=0, output_units=0) == (
        Decimal("0.015")
    )
    assert prices.cost(UsageKind.SEARCH, "duck", units=1, cached_units=0, output_units=0) is None
    assert prices.cost(UsageKind.MODEL, "gpt-9", units=1, cached_units=0, output_units=0) is None


def test_cached_tokens_are_never_charged_twice():
    """`units` counts every token; the cached input and the output are priced at their own
    rates and only the rest at the input rate, so an all-cached call costs the cached price
    alone, a call whose cached and output tokens account for every token has no uncached
    input to charge, and a call of no tokens costs nothing."""
    # A million input tokens, every one served from the cache: $0.10, not $2.10.
    assert model_cost(1_000_000, 1_000_000, 0) == Decimal("0.1")
    # 90 cached plus 20 output is more than the 100 reported: nothing is uncached.
    assert model_cost(100, 90, 20) == (Decimal(90) * Decimal("0.1") + Decimal(20) * Decimal(10)) / (
        Decimal(1_000_000)
    )
    assert model_cost(100, 90, 20) == Decimal("0.000209")
    # 100 input of which 30 cached, and 20 output: 70 uncached.
    assert model_cost(120, 30, 20) == Decimal("0.000343")
    assert model_cost(0, 0, 0) == Decimal(0)
    assert BY_HAND.cost(UsageKind.SEARCH, "s", units=0, cached_units=0, output_units=0) == (
        Decimal(0)
    )
