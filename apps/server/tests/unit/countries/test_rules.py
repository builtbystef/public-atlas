"""The `CountryRules` object answers the agent's and the loader's questions from the tables'
shapes; here, from the seed."""

import pytest

from public_atlas.modules.countries import service
from public_atlas.modules.countries.seeds import canada, shared


@pytest.fixture(scope="module")
def rules() -> service.CountryRules:
    return service.rules_from_seed(canada.SEED)


def test_levels_and_ranks(rules: service.CountryRules):
    assert [level.name for level in rules.levels_by_rank] == [
        "country",
        "province_territory",
        "region",
        "municipality",
    ]
    assert rules.rank_of("region") == 3
    assert rules.government_type("municipality") == "municipal_government"
    assert rules.can_nest("province_territory", "municipality")
    assert rules.can_nest("region", "municipality")
    assert not rules.can_nest("municipality", "region")
    assert rules.levels_above("municipality") == ["country", "province_territory", "region"]
    assert rules.levels_below("province_territory") == ["region", "municipality"]
    with pytest.raises(ValueError, match="no administrative level 'planet'"):
        rules.rank_of("planet")


def test_checklists(rules: service.CountryRules):
    assert "library" in rules.expected_institution_types("municipality")
    assert "ministry" not in rules.expected_institution_types("municipality")
    assert rules.expected_source_types("library") == [
        "procurement",
        "tender",
        "budget",
        "board_meeting",
    ]
    assert rules.expected_source_types("hospital") == shared.CAMPUS_SOURCES
    # A type the country does not use expects nothing.
    assert rules.expected_source_types("zoo") == []
    assert rules.institution_types["hospital"] == "A public hospital or hospital network"
    assert "tender" in rules.source_types


def test_name_patterns(rules: service.CountryRules):
    assert rules.name_mismatch("ministry", "Ministry of Transportation") is None
    assert rules.name_mismatch("ministry", "Ministère des Transports") is None
    assert rules.name_mismatch("ministry", "ministry of health") is None
    reason = rules.name_mismatch("ministry", "Transportation")
    assert reason is not None
    assert "'Transportation' does not look like a ministry's name" in reason
    # A type with no pattern, or an unknown one, says nothing.
    assert rules.name_mismatch("agency", "Metrolinx") is None
    assert rules.name_mismatch("nope", "Anything") is None


def test_platforms_cover_their_subdomains(rules: service.CountryRules):
    assert rules.is_platform("youtube.com")
    assert rules.is_platform("toronto.bidsandtenders.ca")
    assert not rules.is_platform("toronto.ca")
    assert not rules.is_platform("notyoutube.com")


def test_naming_comes_from_the_settings(rules: service.CountryRules):
    assert rules.country_code == "CA"
    assert rules.naming.core("Township of Elmwood") == "elmwood"
