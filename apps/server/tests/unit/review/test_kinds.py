"""Kinds: the shared question an item asks, from its rule and its facts."""

from public_atlas.modules.review.service import Rule, kind_of, type_slug


def test_type_slug():
    assert type_slug("Housing Corporation") == "housing_corporation"
    assert type_slug("  port / authority! ") == "port_authority"
    assert type_slug("311 service") == "type_311_service"
    assert len(type_slug("x" * 100)) == 64


def test_kind_of():
    assert kind_of(Rule.TYPE_LEVEL, {"institution_type": "library", "level": "region"}) == (
        "type_level:library@region"
    )
    assert kind_of(Rule.NEW_TYPE, {"suggested_type": "Housing Corp"}) == "new_type:housing_corp"
    assert kind_of(Rule.NAME_PATTERN, {"institution_type": "ministry"}) is None
    assert kind_of("something_new", {}) is None
