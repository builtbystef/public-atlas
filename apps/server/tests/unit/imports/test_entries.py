"""The entry models refuse a fact with no citation."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.imports.entries import (
    Citation,
    Code,
    Figure,
    InstitutionEntry,
    PlaceEntry,
)

PLACE = Citation(source="register", line=12)
DIRECTORY = Citation(source="directory", line=3)
CODE = Code(scheme=IdentifierScheme.STATCAN_SGC, value="3501")


def place(**changes: object) -> PlaceEntry:
    fields: dict[str, object] = {
        "name": "Elmwood",
        "level": "municipality",
        "parent": "Ontario",
        "government": "Township of Elmwood",
        "code": CODE,
        "citations": {"place": PLACE},
    }
    return PlaceEntry.model_validate({**fields, **changes})


def test_a_place_entry_with_the_place_cited_is_enough():
    entry = place()
    assert entry.government_citation == PLACE
    assert entry.figures == ()
    assert entry.homepage is None


def test_the_governments_citation_is_its_own_when_given():
    entry = place(citations={"place": PLACE, "government": DIRECTORY})
    assert entry.government_citation == DIRECTORY


def test_a_figure_carries_its_own_citation():
    figure = Figure(name=MetricName.POPULATION, year=2021, value=Decimal(1200), citation=PLACE)
    assert place(figures=(figure,)).figures[0].value == 1200


def test_a_homepage_needs_a_citation_a_scheme_and_a_government():
    entry = place(homepage="https://elmwood.ca/", citations={"place": PLACE, "homepage": DIRECTORY})
    assert entry.homepage == "https://elmwood.ca/"
    with pytest.raises(ValidationError, match="homepage with no citation"):
        place(homepage="https://elmwood.ca/")
    with pytest.raises(ValidationError, match="not a URL"):
        place(homepage="elmwood.ca", citations={"place": PLACE, "homepage": DIRECTORY})
    with pytest.raises(ValidationError, match="no government"):
        place(
            government=None,
            homepage="https://elmwood.ca/",
            citations={"place": PLACE, "homepage": DIRECTORY},
        )


def test_a_place_holds_one_code_per_scheme():
    further = Code(scheme=IdentifierScheme.CENSUS_GID, value="01100100100000")
    assert place(codes=(further,)).codes == (further,)
    with pytest.raises(ValidationError, match="two codes in one scheme"):
        place(codes=(Code(scheme=IdentifierScheme.STATCAN_SGC, value="3502"),))


def test_an_institution_holds_codes_and_a_suggested_type_only_when_other():
    code = Code(scheme=IdentifierScheme.NCES, value="0100005")
    entry = InstitutionEntry(
        name="Elmwood Drainage District",
        institution_type="other",
        suggested_type="drainage",
        codes=(code,),
        place="Elmwood",
        citations={"institution": DIRECTORY},
    )
    assert entry.codes == (code,)
    assert entry.suggested_type == "drainage"
    with pytest.raises(ValidationError, match="belongs to a body of type 'other'"):
        InstitutionEntry(
            name="Elmwood Fire District",
            institution_type="fire_service",
            suggested_type="fire",
            place="Elmwood",
            citations={"institution": DIRECTORY},
        )
    with pytest.raises(ValidationError, match="two codes in one scheme"):
        InstitutionEntry(
            name="Elmwood Fire District",
            institution_type="fire_service",
            codes=(code, Code(scheme=IdentifierScheme.NCES, value="0100006")),
            place="Elmwood",
            citations={"institution": DIRECTORY},
        )


def test_a_place_must_be_cited():

    with pytest.raises(ValidationError, match="no citation for the place"):
        place(citations={"government": DIRECTORY})
    with pytest.raises(ValidationError, match="line"):
        Citation(source="register", line=0)


def test_an_institution_entry_must_be_cited():
    entry = InstitutionEntry(
        name="Elmwood Public Library",
        institution_type="library",
        place="Elmwood",
        citations={"institution": DIRECTORY},
    )
    assert entry.parent_institution is None
    with pytest.raises(ValidationError, match="no citation for the institution"):
        InstitutionEntry(name="X", institution_type="library", place="Elmwood", citations={})
