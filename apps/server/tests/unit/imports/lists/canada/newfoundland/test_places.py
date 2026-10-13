"""The Newfoundland and Labrador places list: the counts are pinned, every government is
composed from the census type, and a few places show the rules a count cannot. What every
list's entries must satisfy is checked by the contract test beside the lists."""

from typing import Any

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.canada.newfoundland import places as newfoundland

pytestmark = pytest.mark.lists

MUNICIPALITIES = 277
CITIES = 3
INUIT_COMMUNITY_GOVERNMENTS = 5
DROPPED = {"SNO": 92, "IRI": 3}
QUALIFIED = 6


@pytest.fixture(scope="module")
def opened(sources_of) -> dict[str, files.OpenedFile]:
    return sources_of(newfoundland)


@pytest.fixture(scope="module")
def built(opened) -> tuple[list[PlaceEntry], newfoundland.Notes]:
    return newfoundland.build(opened)


@pytest.fixture(scope="module")
def entries(built) -> list[PlaceEntry]:
    return built[0]


@pytest.fixture(scope="module")
def by_code(entries) -> dict[str, PlaceEntry]:
    return {entry.code.value: entry for entry in entries}


@pytest.fixture(scope="module")
def loaded(loaded_places_of) -> Any:
    return loaded_places_of("CA", ("canada/newfoundland/places",))


def test_the_counts(entries, built):
    notes = built[1]
    assert len(entries) == MUNICIPALITIES
    assert sum(1 for entry in entries if entry.government.startswith("City of")) == CITIES
    assert sum(
        1 for entry in entries if entry.government.endswith("Inuit Community Government")
    ) == (INUIT_COMMUNITY_GOVERNMENTS)
    assert dict(notes.dropped) == DROPPED
    assert len(notes.qualified) == QUALIFIED
    assert len(notes.overrides) == INUIT_COMMUNITY_GOVERNMENTS
    assert all(entry.homepage is None for entry in entries)
    codes = [entry.code.value for entry in entries]
    assert len(set(codes)) == len(codes)


def test_every_government_is_composed_from_the_census_and_names_its_place(
    entries, rules: countries.CountryRules
):
    """No file names the body: the government is the census type around the place's bare name,
    cited where the place is."""
    naming = rules.naming
    for entry in entries:
        assert "government" not in entry.citations
        assert entry.government is not None, entry.name
        bare = newfoundland.bare_name(entry.name)
        assert naming.key(bare) in naming.key(entry.government), entry.name


def test_the_two_seal_coves_stay_two_places(entries, loaded: Any) -> None:
    seal_coves = [entry for entry in entries if entry.name.startswith("Seal Cove")]
    assert [entry.name for entry in seal_coves] == [
        "Seal Cove (Fortune Bay)",
        "Seal Cove (White Bay)",
    ]
    assert all(entry.aliases == () for entry in seal_coves)
    assert loaded.told_apart == []


def test_the_places_that_show_the_rules(by_code):
    assert by_code["1001519"].government == "City of St. John's"
    assert by_code["1011035"].government == "Nain Inuit Community Government"
    charlottetown = by_code["1010013"]
    assert (charlottetown.name, charlottetown.government) == (
        "Charlottetown (Labrador)",
        "Town of Charlottetown",
    )
    assert [alias.text for alias in charlottetown.aliases] == ["Charlottetown"]
    assert by_code["1009011"].government == "Town of Woody Point"
