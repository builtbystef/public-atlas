"""Canada's naming rules find the place name inside a government's name and tell two bodies
apart."""

import pytest

from public_atlas.modules.countries.naming import Naming
from public_atlas.modules.countries.schemas import NamingRules
from public_atlas.modules.countries.seeds import canada


@pytest.fixture(scope="module")
def naming() -> Naming:
    return Naming(NamingRules.model_validate(canada.SETTINGS["naming_rules"]))


def test_designators_find_the_place_name(naming: Naming):
    for written in (
        "Township of Elmwood",
        "Elmwood Township",
        "Elmwood, Township of",
        "The Corporation of the Township of Elmwood",
    ):
        assert naming.core(written) == "elmwood"
    assert naming.core("Elmwood, Regional Municipality of") == "elmwood"
    assert naming.core("Elmwood, Ville de") == "elmwood"
    assert naming.core("Elm/Oak, Municipality of") == "elm oak"
    assert naming.core("Elmwood") == "elmwood"
    assert naming.core("United Counties of Stormont, Dundas and Glengarry") == (
        "stormont, dundas & glengarry"
    )


def test_a_two_word_designator_is_one_designator(naming: Naming):
    assert naming.designators_in("Elmwood, Regional Municipality of") == naming.designators_in(
        "Municipalité régionale de Elmwood"
    )


def test_designators_tell_two_bodies_apart(naming: Naming):
    # A city and a township with one place name are two bodies; "Ville" is a city or a town; a
    # bare name says nothing.
    assert naming.designators_differ(["Township of Elmwood", "Elmwood"], ["Elmwood, City of"])
    assert not naming.designators_differ(["Town of Elmwood"], ["Elmwood, Ville de"])
    assert not naming.designators_differ(["Elmwood"], ["City of Elmwood"])


def test_the_and_words_are_one_word(naming: Naming):
    assert naming.key("Elm & Oak") == naming.key("Elm and Oak") == naming.key("Elm et Oak")


def test_a_lists_inverted_form_is_written_out(naming: Naming):
    assert naming.written_forms("Kingston, City of") == ["City of Kingston", "Kingston"]
    assert naming.written_forms("Stormont, Dundas and Glengarry, United Counties of") == [
        "United Counties of Stormont, Dundas and Glengarry",
        "Stormont, Dundas and Glengarry",
    ]
    assert naming.written_forms("Elmwood, Township of Elmwood") == [
        "Township of Elmwood",
        "Elmwood",
    ]
    assert naming.written_forms("Haldimand County") == ["Haldimand County"]
    assert naming.written_forms("  Government  of Ontario ") == ["Government of Ontario"]


def test_every_spelling_of_a_name_meets_on_a_form(naming: Naming):
    spellings = (
        "City of Elmwood",
        "Elmwood, City of",
        "Elmwood",
        "The Corporation of the City of Elmwood",
        "Elmwood City",
    )
    forms = [naming.forms(spelling) for spelling in spellings]
    assert all("elmwood" in found for found in forms)
    assert not naming.forms("Oakville") & naming.forms("Elmwood")
