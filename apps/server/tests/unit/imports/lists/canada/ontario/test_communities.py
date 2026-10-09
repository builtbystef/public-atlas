"""The community map names only municipalities the places list loads, and reads a city the
way the lists write it."""

from public_atlas.modules.imports.lists.canada.ontario import communities


def test_every_community_lies_in_a_loaded_place(
    municipality_names: frozenset[str], region_names: frozenset[str]
):
    for community, municipality in communities.COMMUNITIES.items():
        assert municipality in municipality_names, community
        # A community that is a municipality itself needs no row; one named like a county or
        # district (Simcoe, Sudbury) is the point of the map.
        assert community not in municipality_names, community
    for community, district in communities.UNORGANIZED.items():
        # A district, which may share its name with a municipality.
        assert district in region_names, community
        assert community not in municipality_names, community
    for municipality in communities.NAMESAKES:
        assert municipality in municipality_names


def test_a_city_is_read_as_the_lists_write_it():
    municipality = communities.MUNICIPALITY
    assert communities.location_of("Almonte") == communities.Location("Mississippi Mills")
    assert communities.location_of("THUNDER BAY") == communities.Location("THUNDER BAY")
    assert communities.location_of("Hamilton,") == communities.Location(
        "Hamilton", municipality, "Ontario"
    )
    assert communities.location_of("Barry\u2019s Bay") == communities.Location("Madawaska Valley")
    assert communities.location_of("north york") == communities.Location("Toronto")
    assert communities.location_of("Sudbury") == communities.Location("Greater Sudbury")
    assert communities.location_of("Moose Factory") == communities.Location(
        "Cochrane", communities.REGION, "Ontario"
    )
