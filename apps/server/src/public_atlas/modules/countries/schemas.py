"""The shapes of the country tables as the API reads and writes them, and as the seeds are
validated. The schema lives here once: a seed module is a plain dictionary checked by the same
models an edit from the console goes through."""

import re
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# A level's or type's name: a word the agent reads and a row's key.
Name = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")]
# ISO 3166-1 alpha-2.
CountryCode = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
# A registrable name, lower case, no scheme and no path.
DomainName = Annotated[
    str, Field(max_length=253, pattern=r"^([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
]


def compiled(pattern: str | None) -> str | None:
    if pattern is not None:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"not a regular expression: {exc}") from None
    return pattern


class NamingRules(BaseModel):
    """How the country writes its public bodies' names, in its languages. A government's name is
    a place name with a designator around it ("Township of Elmwood", "Elmwood, Township of");
    knowing the designators lets the checks find the place name and tell a township from the
    city of the same name."""

    model_config = ConfigDict(extra="forbid")

    # One group per kind of body, with its word in each language: `[City, Ville]`. A word may be
    # in two groups when a language uses it for both.
    designators: list[list[str]] = []
    # What joins a designator to the place name: "of" in "Township of Elmwood".
    connectors: list[str] = []
    # Words before a body's name that are not part of it: "The".
    leading: list[str] = []
    # Read as "&", so "Elm & Oak" and "Elm and Oak" are one name.
    and_words: list[str] = []


class CountrySettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country_code: CountryCode
    name: str = Field(min_length=1, max_length=100)
    naming_rules: NamingRules = NamingRules()


class AdministrativeLevelInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    # From the top: the country is 1.
    rank: int = Field(ge=1)
    government_institution_type: Name
    # The types to find under a place of this level, the government aside.
    expected_institution_types: list[Name] = []

    @field_validator("expected_institution_types")
    @classmethod
    def no_repeats(cls, value: list[str]) -> list[str]:
        return distinct(value)


class InstitutionTypeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    # Shown to the agent: it is what tells two types apart.
    description: str = Field(min_length=1)


class SourceTypeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    description: str = Field(min_length=1)


class CountryInstitutionTypeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution_type: Name
    expected_source_types: list[Name] = []
    # Searched case-insensitively, e.g. `^(Ministry of |Ministère d)`. A name that fails it is
    # still saved and goes to review.
    name_pattern: str | None = None

    @field_validator("expected_source_types")
    @classmethod
    def no_repeats(cls, value: list[str]) -> list[str]:
        return distinct(value)

    @field_validator("name_pattern")
    @classmethod
    def compiles(cls, value: str | None) -> str | None:
        return compiled(value)


class CountryOutput(BaseModel):
    """One country's five tables, as the console reads them. The global type tables have routes
    of their own."""

    settings: CountrySettingsInput
    administrative_levels: list[AdministrativeLevelInput]
    institution_types: list[CountryInstitutionTypeInput]


# --- Seeds (spec section 5.1) ---


class SharedSeed(BaseModel):
    """What every country starts from: the global types, and the sources expected per type."""

    model_config = ConfigDict(extra="forbid")

    institution_types: list[InstitutionTypeInput]
    source_types: list[SourceTypeInput]
    default_expected_source_types: dict[Name, list[Name]]

    @property
    def institution_type_names(self) -> set[str]:
        return {row.name for row in self.institution_types}

    @property
    def source_type_names(self) -> set[str]:
        return {row.name for row in self.source_types}

    @model_validator(mode="after")
    def consistent(self) -> Self:
        unique_names(self.institution_types, "institution type")
        unique_names(self.source_types, "source type")
        for institution_type, sources in self.default_expected_source_types.items():
            if institution_type not in self.institution_type_names:
                raise ValueError(f"default sources for an unknown type: {institution_type!r}")
            if unknown := set(sources) - self.source_type_names:
                raise ValueError(f"{institution_type} expects unknown sources: {sorted(unknown)}")
        return self


class PlaceSeed(BaseModel):
    """A place the seed creates verified. With a government and domains it is an anchor: the
    only entities trusted without evidence, and where discovery starts."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=300)
    level: Name
    # The name of a place seeded before this one; none for the country itself.
    parent: str | None = None
    # The language of the names, as a BCP 47 tag.
    language: str = "en"
    government: str | None = Field(default=None, min_length=1, max_length=300)
    domains: list[DomainName] = []

    @model_validator(mode="after")
    def domains_need_a_government(self) -> Self:
        if self.domains and self.government is None:
            raise ValueError(f"{self.name} has domains but no government to trust them for")
        return self


class CountrySeed(BaseModel):
    """One country's seed module, validated as a whole."""

    model_config = ConfigDict(extra="forbid")

    settings: CountrySettingsInput
    administrative_levels: list[AdministrativeLevelInput]
    institution_types: list[CountryInstitutionTypeInput]
    platforms: list[DomainName] = []
    places: list[PlaceSeed] = []

    @property
    def institution_type_names(self) -> set[str]:
        return {row.institution_type for row in self.institution_types}

    @model_validator(mode="after")
    def consistent(self) -> Self:
        unique_names(self.administrative_levels, "administrative level")
        if len(self.institution_type_names) != len(self.institution_types):
            raise ValueError("an institution type is listed twice")
        if len(set(self.platforms)) != len(self.platforms):
            raise ValueError("a platform is listed twice")
        self._check_levels()
        self._check_places()
        return self

    def _check_levels(self) -> None:
        for level in self.administrative_levels:
            expected = [level.government_institution_type, *level.expected_institution_types]
            if unknown := set(expected) - self.institution_type_names:
                raise ValueError(
                    f"level {level.name} expects types the country does not use: {sorted(unknown)}"
                )

    def _check_places(self) -> None:
        """Each place is seeded once, at a known level, after a parent above it."""
        ranks = {level.name: level.rank for level in self.administrative_levels}
        seen: dict[str, PlaceSeed] = {}
        for place in self.places:
            if place.level not in ranks:
                raise ValueError(f"{place.name} is at an unknown level: {place.level!r}")
            if place.name in seen:
                raise ValueError(f"{place.name} is seeded twice")
            if place.parent is not None:
                if place.parent not in seen:
                    raise ValueError(f"{place.name}'s parent is not seeded before it")
                if ranks[seen[place.parent].level] >= ranks[place.level]:
                    raise ValueError(f"{place.name}'s parent is not above it")
            seen[place.name] = place

    def check_against(self, shared: SharedSeed) -> None:
        """The types the country uses, and the sources it expects, are global ones."""
        if unknown := self.institution_type_names - shared.institution_type_names:
            raise ValueError(f"unknown institution types: {sorted(unknown)}")
        for row in self.institution_types:
            if unknown := set(row.expected_source_types) - shared.source_type_names:
                raise ValueError(
                    f"{row.institution_type} expects unknown sources: {sorted(unknown)}"
                )


def distinct(values: list[str]) -> list[str]:
    if len(set(values)) != len(values):
        raise ValueError("a name is listed twice")
    return values


def unique_names(rows: list[Any], what: str) -> None:
    names = [row.name for row in rows]
    if len(set(names)) != len(names):
        raise ValueError(f"an {what} is listed twice")
