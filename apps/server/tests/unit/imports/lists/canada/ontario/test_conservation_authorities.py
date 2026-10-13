"""The conservation authorities list: the count is pinned, every authority is the layer's
legal name at a municipality, and a few rows show the rules a count cannot. What every list's
entries must satisfy is checked by the contract test beside the lists."""

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import InstitutionEntry
from public_atlas.modules.imports.lists.canada.ontario import conservation_authorities

pytestmark = pytest.mark.lists

AUTHORITIES = 36
# Authorities whose common name is not their legal name, punctuation aside.
COMMON_NAMES = 13


@pytest.fixture(scope="module")
def opened(sources_of) -> dict[str, files.OpenedFile]:
    return sources_of(conservation_authorities)


@pytest.fixture(scope="module")
def entries(
    opened: dict[str, files.OpenedFile], rules: countries.CountryRules
) -> list[InstitutionEntry]:
    return conservation_authorities.entries(opened, rules)


@pytest.fixture(scope="module")
def by_name(entries: list[InstitutionEntry]) -> dict[str, InstitutionEntry]:
    return {entry.name: entry for entry in entries}


def test_the_counts(entries: list[InstitutionEntry], opened: dict[str, files.OpenedFile]):
    records = conservation_authorities.read_layer(opened[conservation_authorities.LAYER.name])
    assert len(records) == AUTHORITIES
    assert len(entries) == AUTHORITIES
    assert sum(1 for entry in entries if entry.aliases) == COMMON_NAMES
    directory = opened[conservation_authorities.DIRECTORY.name]
    assert (
        sum(
            1
            for row in directory.rows
            if row["Institution type"] == conservation_authorities.DIRECTORY_TYPE
        )
        == AUTHORITIES
    )
    names = [entry.name for entry in entries]
    assert len(set(names)) == len(names)


def test_every_authority_is_the_layers_legal_name_at_a_municipality(
    entries: list[InstitutionEntry], opened: dict[str, files.OpenedFile]
):
    layer = opened[conservation_authorities.LAYER.name]
    for entry in entries:
        assert entry.institution_type == "conservation_authority"
        assert entry.name.endswith("Conservation Authority")
        citation = entry.citations["institution"]
        assert citation.source == conservation_authorities.LAYER.name
        assert layer.line(citation.line) == f"LEGAL_NAME: {entry.name}"
        assert entry.homepage is None
        assert entry.parent_institution is None
        assert entry.served_places == ()
        assert entry.place_level == "municipality"


def test_the_rows_that_show_the_rules(by_name: dict[str, InstitutionEntry]):
    nickel = by_name["Nickel District Conservation Authority"]
    assert [alias.text for alias in nickel.aliases] == ["Conservation Sudbury"]
    assert nickel.place == "Greater Sudbury"
    halton = by_name["Halton Region Conservation Authority"]
    assert [alias.text for alias in halton.aliases] == ["Conservation Halton"]
    assert halton.place == "Burlington"
    # A common name that differs by punctuation alone is no alias.
    assert by_name["Sault Ste. Marie Region Conservation Authority"].aliases == ()
    assert by_name["Toronto and Region Conservation Authority"].aliases == ()
    assert by_name["Toronto and Region Conservation Authority"].place == "Toronto"
    hamilton = by_name["Hamilton Region Conservation Authority"]
    assert (hamilton.place, hamilton.place_parent) == ("Hamilton", "Ontario")
    assert by_name["Lower Trent Conservation Authority"].place == "Quinte West"
    assert by_name["South Nation River Conservation Authority"].place == "North Stormont"
    assert by_name["Mississippi Valley Conservation Authority"].place == "Lanark Highlands"
    assert by_name["Rideau Valley Conservation Authority"].place == "Ottawa"
    assert by_name["Cataraqui Region Conservation Authority"].place == "Kingston"
    assert by_name["Maitland Valley Conservation Authority"].place == "Howick"
    assert by_name["Nottawasaga Valley Conservation Authority"].place == "Essa"
    assert by_name["Crowe Valley Conservation Authority"].place == "Marmora and Lake"
    assert by_name["Essex Region Conservation Authority"].place == "Essex"
    assert by_name["Kawartha Region Conservation Authority"].place == "Kawartha Lakes"


def test_the_overrides_apply(by_name: dict[str, InstitutionEntry]):
    """An override's place is the entry's; the directory's wording of a name is read as the
    layer's legal name."""
    assert by_name["Long Point Region Conservation Authority"].place == "Tillsonburg"
    for name, fields in conservation_authorities.OVERRIDES.items():
        assert by_name[name].place == fields["place"]
    for wording, legal in conservation_authorities.DIRECTORY_NAMES.items():
        assert legal in by_name
        assert wording not in by_name
