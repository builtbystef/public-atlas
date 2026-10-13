"""What the Ontario lists' rule tests share: the places the places list loads, which the other
lists attach their bodies to, and the lookup that finds a place as the loader does. The
country's rules and the files of a list come from the fixtures every list's tests share."""

from collections.abc import Callable
from typing import Any

import pytest

from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.canada.ontario import places as ontario_places

ONTARIO = ("canada/ontario/places",)


@pytest.fixture(scope="package")
def places(entries_of) -> list[PlaceEntry]:
    """What `canada/ontario/places` loads."""
    return [entry for entry in entries_of(ONTARIO[0]) if isinstance(entry, PlaceEntry)]


@pytest.fixture(scope="package")
def loaded(loaded_places_of) -> Any:
    """The seed's anchors and the places list's places, as the loader finds them."""
    return loaded_places_of("CA", ONTARIO)


@pytest.fixture(scope="package")
def find_places(loaded: Any) -> Callable[[str, str | None, str | None], list[PlaceEntry]]:
    """The loaded places that go by a name, as the loader finds them for an institution: at the
    level when one is given, under the parent when one is given, the province included."""
    return loaded.find


@pytest.fixture(scope="package")
def municipality_names(places: list[PlaceEntry]) -> frozenset[str]:
    return frozenset(entry.name for entry in places if entry.level == ontario_places.MUNICIPALITY)


@pytest.fixture(scope="package")
def region_names(places: list[PlaceEntry]) -> frozenset[str]:
    return frozenset(entry.name for entry in places if entry.level == ontario_places.REGION)
