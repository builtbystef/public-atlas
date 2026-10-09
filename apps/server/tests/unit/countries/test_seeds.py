"""The seed modules pass the countries API's models, and a wrong one is refused."""

import copy

import pytest
from pydantic import ValidationError

from public_atlas.modules.countries import service
from public_atlas.modules.countries.schemas import CountrySeed, SharedSeed
from public_atlas.modules.countries.seeds import SEEDS, canada, shared, united_states


def test_the_shared_seed_validates():
    seed = SharedSeed.model_validate(shared.SEED)
    assert "other" in seed.institution_type_names
    assert seed.default_expected_source_types.keys() == seed.institution_type_names


def test_the_canada_seed_validates_against_the_shared_seed():
    shared_seed, seed = service.validate(canada.SEED)
    assert seed.settings.country_code == "CA"
    assert [level.rank for level in seed.administrative_levels] == [1, 2, 3, 4]
    # A park district is the United States' alone.
    assert seed.institution_type_names < shared_seed.institution_type_names
    assert shared_seed.institution_type_names - seed.institution_type_names == {"park_district"}
    ontario = next(place for place in seed.places if place.name == "Ontario")
    assert ontario.government == "Government of Ontario"
    assert ontario.domains == ["ontario.ca", "gov.on.ca"]


def test_the_canada_seed_anchors_the_federal_and_every_provincial_government():
    _, seed = service.validate(canada.SEED)
    country = seed.places[0]
    assert (country.name, country.level, country.government) == (
        "Canada",
        "country",
        "Government of Canada",
    )
    assert country.domains == ["canada.ca", "gc.ca"]
    provinces = [place for place in seed.places if place.level == "province_territory"]
    assert len(provinces) == 13
    assert all(place.parent == "Canada" for place in provinces)
    assert all(place.government and place.domains for place in provinces)
    quebec = next(place for place in provinces if place.name == "Quebec")
    assert (quebec.government, quebec.domains) == (
        "Gouvernement du Québec",
        ["quebec.ca", "gouv.qc.ca"],
    )
    domains = [domain for place in seed.places for domain in place.domains]
    assert len(set(domains)) == len(domains)


def test_every_registered_seed_validates():
    assert set(SEEDS) == {"canada", "united_states"}
    for name, seed in SEEDS.items():
        assert service.validate(seed)[1].settings.name, name


def test_the_united_states_seed_has_four_levels_and_uses_the_park_district():
    shared_seed, seed = service.validate(united_states.SEED)
    assert seed.settings.country_code == "US"
    assert [(level.name, level.rank) for level in seed.administrative_levels] == [
        ("country", 1),
        ("state", 2),
        ("county", 3),
        ("municipality", 4),
    ]
    by_name = {level.name: level for level in seed.administrative_levels}
    assert by_name["county"].government_institution_type == "regional_government"
    assert by_name["municipality"].government_institution_type == "municipal_government"
    assert set(by_name["county"].expected_institution_types) == set(united_states.LOCAL_TYPES)
    assert by_name["municipality"].expected_institution_types == united_states.LOCAL_TYPES
    assert "park_district" in seed.institution_type_names
    assert "ministry" not in seed.institution_type_names
    assert seed.institution_type_names < shared_seed.institution_type_names
    assert "legistar.com" in seed.platforms
    assert "youtube.com" in seed.platforms


def test_the_united_states_seed_anchors_the_federal_government_and_every_state():
    _, seed = service.validate(united_states.SEED)
    country = seed.places[0]
    assert (country.name, country.level, country.government, country.domains) == (
        "United States",
        "country",
        "Government of the United States",
        ["usa.gov"],
    )
    states = [place for place in seed.places if place.level == "state"]
    assert len(states) == 52
    assert all(place.parent == "United States" for place in states)
    assert all(place.government and place.domains for place in states)
    by_name = {place.name: place for place in states}
    assert by_name["Kentucky"].government == "Commonwealth of Kentucky"
    assert by_name["Ohio"].government == "State of Ohio"
    assert by_name["District of Columbia"].government == ("Government of the District of Columbia")
    assert by_name["Puerto Rico"].domains == ["pr.gov"]
    assert sum(1 for place in states if (place.government or "").startswith("Commonwealth")) == 5
    domains = [domain for place in seed.places for domain in place.domains]
    assert len(set(domains)) == len(domains)
    # Checked against the .gov registry's "State or territory" rows: every anchor is a .gov.
    assert all(domain.endswith(".gov") for domain in domains)


def test_the_united_states_naming_rules_tell_a_town_from_the_village_inside_it():
    rules = service.rules_from_seed(united_states.SEED)
    naming = rules.naming
    assert naming.designators_differ(["Town of Hamburg"], ["Village of Hamburg"])
    assert not naming.designators_differ(["Town of Hamburg"], ["Hamburg town"])
    assert naming.core("City of Springfield") == naming.core("Springfield city") == "springfield"
    assert naming.core("City and County of Denver") == "denver"
    assert naming.core("Lexington-Fayette Urban County Government") == "lexington fayette"
    assert naming.core("Cook County") == "cook"
    assert naming.key("District of Columbia") in naming.key(
        "Government of the District of Columbia"
    )
    assert naming.forms("Washington County") & naming.forms("Washington")


def test_a_ministry_name_pattern_is_a_regular_expression():
    seed = CountrySeed.model_validate(canada.SEED)
    ministry = next(row for row in seed.institution_types if row.institution_type == "ministry")
    assert ministry.name_pattern is not None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        pytest.param(
            lambda s: s["administrative_levels"][0]["expected_institution_types"].append("zoo"),
            "zoo",
            id="a level expecting a type the country does not use",
        ),
        pytest.param(
            lambda s: s["places"].append({"name": "Nowhere", "level": "state"}),
            "unknown level",
            id="a place at an unknown level",
        ),
        pytest.param(
            lambda s: s["places"].append({"name": "Ontario", "level": "region"}),
            "seeded twice",
            id="a place seeded twice",
        ),
        pytest.param(
            lambda s: s["places"][1].update(parent="Ontario", name="Toronto"),
            "not seeded before",
            id="a parent seeded later",
        ),
        pytest.param(
            lambda s: s["places"][1].update(level="country"),
            "not above",
            id="a parent not above its child",
        ),
        pytest.param(
            lambda s: s["places"][1].update(government=None),
            "no government",
            id="domains without a government",
        ),
        pytest.param(
            lambda s: s["platforms"].append("youtube.com"),
            "listed twice",
            id="a platform listed twice",
        ),
        pytest.param(
            lambda s: s["platforms"].append("http://youtube.com"),
            "pattern",
            id="a platform that is not a domain name",
        ),
        pytest.param(
            lambda s: s["institution_types"][0].update(name_pattern="("),
            "regular expression",
            id="a name pattern that does not compile",
        ),
        pytest.param(
            lambda s: s["settings"].update(country_code="CAN"),
            "pattern",
            id="a country code that is not two letters",
        ),
    ],
)
def test_a_wrong_seed_is_refused(change, message):
    seed = copy.deepcopy(canada.SEED)
    change(seed)
    with pytest.raises(ValidationError, match=message):
        CountrySeed.model_validate(seed)


def test_a_type_the_shared_seed_lacks_is_refused():
    seed = copy.deepcopy(canada.SEED)
    seed["institution_types"].append({"institution_type": "zoo", "expected_source_types": []})
    with pytest.raises(ValueError, match="unknown institution types"):
        service.validate(seed)


def test_a_source_the_shared_seed_lacks_is_refused():
    seed = copy.deepcopy(canada.SEED)
    seed["institution_types"][0]["expected_source_types"].append("gossip")
    with pytest.raises(ValueError, match="gossip"):
        service.validate(seed)
