"""The records a list module returns (spec section 5.2). They exist only while the loader runs:
the loader turns each into rows, with a citation per fact becoming an evidence row that quotes
the list's own line."""

from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from public_atlas.modules.graph.models import IdentifierScheme, MetricName

# A line of a source's text, counted from 1; line 1 is a table's header.
LineNumber = int

type Fact = Literal["place", "government", "institution", "homepage"]


class Citation(BaseModel):
    """Which source and which line a fact came from."""

    model_config = ConfigDict(frozen=True)

    # One of the list module's `SOURCES`, by name.
    source: str = Field(min_length=1)
    line: LineNumber = Field(ge=1)


class Code(BaseModel):
    """A code in an outside scheme."""

    model_config = ConfigDict(frozen=True)

    scheme: IdentifierScheme
    value: str = Field(min_length=1, max_length=64)


class Figure(BaseModel):
    """A metric's value for a year, with the line that gives it."""

    model_config = ConfigDict(frozen=True)

    name: MetricName
    year: int
    value: Decimal
    citation: Citation


class AliasEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1, max_length=300)
    # BCP 47.
    language: str = "en"
    is_acronym: bool = False


class PlaceEntry(BaseModel):
    """A place with its government. Becomes a verified `places` row, its government's
    `institutions` row, an `identifiers` row, `metrics` rows, and a candidate `homepages` row
    for the government when the list links one."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=300)
    aliases: tuple[AliasEntry, ...] = ()
    language: str = "en"
    level: str
    # The name of a place at a higher level, loaded or seeded; None only for a country itself.
    parent: str | None
    # Which place of that name, when the name alone does not say: its administrative level (the
    # state of Washington, not a county of that name) and the name of its own parent (Washington
    # County under Pennsylvania, not the thirty others).
    parent_level: str | None = None
    parent_parent: str | None = None
    # The government's name; None for a unit nothing governs (a territorial district).
    government: str | None = Field(default=None, min_length=1, max_length=300)
    # The code the place is found by, and its codes in other schemes, stored beside it.
    code: Code
    codes: tuple[Code, ...] = ()

    figures: tuple[Figure, ...] = ()
    # The government's official page, as the list links it.
    homepage: str | None = None
    # `place` is required and stands in for `government` when that is not given; `homepage` is
    # required when a homepage is.
    citations: dict[Fact, Citation]

    @model_validator(mode="after")
    def cited(self) -> Self:
        if "place" not in self.citations:
            raise ValueError(f"{self.name}: no citation for the place")
        if self.homepage is not None and "homepage" not in self.citations:
            raise ValueError(f"{self.name}: a homepage with no citation")
        if self.homepage is not None and not self.homepage.startswith(("http://", "https://")):
            raise ValueError(f"{self.name}: homepage is not a URL: {self.homepage!r}")
        if self.homepage is not None and self.government is None:
            raise ValueError(f"{self.name}: a homepage but no government to claim it")
        one_per_scheme(self.name, (self.code, *self.codes))
        return self

    @property
    def government_citation(self) -> Citation:
        return self.citations.get("government", self.citations["place"])


def one_per_scheme(name: str, codes: tuple[Code, ...]) -> None:
    """An entry holds one code per scheme, as a row does."""
    schemes = [code.scheme for code in codes]
    if len(set(schemes)) != len(schemes):
        raise ValueError(f"{name}: two codes in one scheme")


class ServedPlace(BaseModel):
    """A place a multi-place body serves, said as the entry's own place is: by name, and by
    level and parent when the name alone does not say which (the Town of Cochrane, not the
    district; the City of Hamilton, not the township)."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=300)
    level: str | None = None
    parent: str | None = None


class InstitutionEntry(BaseModel):
    """A public body under a place. Becomes a verified `institutions` row,
    `institution_served_places` rows and a candidate `homepages` row."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=300)
    aliases: tuple[AliasEntry, ...] = ()
    language: str = "en"
    institution_type: str
    # For a body of type `other`: the type the list suggests, in the list's own words (the
    # function the Census of Governments gives a district), for the reviewer.
    suggested_type: str | None = Field(default=None, min_length=1, max_length=300)
    # The body's codes in outside schemes: it is found by them before its name, and they are
    # stored.
    codes: tuple[Code, ...] = ()
    # The name of a loaded or seeded place.
    place: str

    # Which place of that name, when the name alone does not say: its administrative level
    # (the City of Thunder Bay, not the district) and the name of its parent (the City of
    # Hamilton under Ontario, not the township under Northumberland).
    place_level: str | None = None
    place_parent: str | None = None
    # The name of an institution at the place; None defaults to the place's government.
    parent_institution: str | None = None
    served_places: tuple[ServedPlace, ...] = ()
    homepage: str | None = None
    citations: dict[Fact, Citation]

    @model_validator(mode="after")
    def cited(self) -> Self:
        if "institution" not in self.citations:
            raise ValueError(f"{self.name}: no citation for the institution")
        if self.homepage is not None and "homepage" not in self.citations:
            raise ValueError(f"{self.name}: a homepage with no citation")
        if self.homepage is not None and not self.homepage.startswith(("http://", "https://")):
            raise ValueError(f"{self.name}: homepage is not a URL: {self.homepage!r}")
        if self.suggested_type is not None and self.institution_type != "other":
            raise ValueError(f"{self.name}: a suggested type belongs to a body of type 'other'")
        one_per_scheme(self.name, self.codes)
        return self


type Entry = PlaceEntry | InstitutionEntry
