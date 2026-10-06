"""The price list and the cost of one call."""

from decimal import Decimal

from public_atlas.modules.assignments.models import UsageKind
from public_atlas.modules.assignments.pricing import PRICES_FILE, load_prices


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
