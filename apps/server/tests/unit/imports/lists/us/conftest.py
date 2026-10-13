"""What the United States lists' rule tests share: the country's rules and the places the two
places lists load, which the other lists attach their bodies to, looked up as the loader does.
A list's files come from the fixtures every list's tests share."""

from typing import Any

import pytest

from public_atlas.modules.countries import service as countries

PLACES = ("us/states_counties", "us/municipalities")


@pytest.fixture(scope="package")
def rules(rules_for) -> countries.CountryRules:
    return rules_for("US")


@pytest.fixture(scope="package")
def loaded(loaded_places_of) -> Any:
    """The seed's anchors, the states and counties, then the municipalities, as the loader
    finds them."""
    return loaded_places_of("US", PLACES)
