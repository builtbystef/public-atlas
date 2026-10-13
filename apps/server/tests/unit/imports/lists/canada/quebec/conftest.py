"""What the Quebec lists' rule tests share: the places the places list loads, which the other
lists attach their bodies to, and the lookup that finds a place as the loader does. The
country's rules and the files of a list come from the fixtures every list's tests share."""

from collections.abc import Callable
from typing import Any

import pytest

from public_atlas.modules.imports.entries import Entry, PlaceEntry

QUEBEC = ("canada/quebec/places",)


@pytest.fixture(scope="package")
def quebec_entries(entries_of) -> list[Entry]:
    """What `canada/quebec/places` loads."""
    return entries_of(QUEBEC[0])


@pytest.fixture(scope="package")
def places(quebec_entries: list[Entry]) -> list[PlaceEntry]:
    return [entry for entry in quebec_entries if isinstance(entry, PlaceEntry)]


@pytest.fixture(scope="package")
def loaded(loaded_places_of) -> Any:
    """The seed's anchors and the places list's places, as the loader finds them."""
    return loaded_places_of("CA", QUEBEC)


@pytest.fixture(scope="package")
def find_places(loaded: Any) -> Callable[[str, str | None, str | None], list[PlaceEntry]]:
    """The loaded places that go by a name, as the loader finds them for an institution or a
    served place: at the level when one is given, under the parent when one is given, the
    province included."""
    return loaded.find
