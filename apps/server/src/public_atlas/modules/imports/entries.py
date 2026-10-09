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
    # The government's name; None for a unit nothing governs (a territorial district).
    government: str | None = Field(default=None, min_length=1, max_length=300)
    code: Code
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
        return self

    @property
    def government_citation(self) -> Citation:
        return self.citations.get("government", self.citations["place"])


class InstitutionEntry(BaseModel):
    """A public body under a place. Becomes a verified `institutions` row,
    `institution_served_places` rows and a candidate `homepages` row."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=300)
    aliases: tuple[AliasEntry, ...] = ()
    language: str = "en"
    institution_type: str
    # The name of a loaded or seeded place.
    place: str
    # Which place of that name, when the name alone does not say: its administrative level
    # (the City of Thunder Bay, not the district) and the name of its parent (the City of
    # Hamilton under Ontario, not the township under Northumberland).
    place_level: str | None = None
    place_parent: str | None = None
    # The name of an institution at the place; None defaults to the place's government.
    parent_institution: str | None = None
    served_places: tuple[str, ...] = ()
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
        return self


type Entry = PlaceEntry | InstitutionEntry
