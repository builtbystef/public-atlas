"""`CountryRules`: what the country tables say, read once at the start of an assignment or a
load, so an edit made in the console takes effect on the next one. Levels and ranks, the types
expected at each level, the sources expected for each type in this country, the naming rules
and the platforms."""

import re
from dataclasses import dataclass
from functools import cached_property

from public_atlas.modules.countries.naming import Naming
from public_atlas.modules.countries.schemas import (
    AdministrativeLevelInput,
    CountryInstitutionTypeInput,
    CountrySettingsInput,
    InstitutionTypeInput,
    SourceTypeInput,
)


@dataclass(frozen=True, slots=True)
class Level:
    name: str
    # From the top: the country is 1.
    rank: int
    government_institution_type: str
    expected_institution_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TypeUse:
    """How this country uses an institution type."""

    institution_type: str
    expected_source_types: tuple[str, ...]
    name_pattern: re.Pattern[str] | None


@dataclass(frozen=True)
class CountryRules:
    country_code: str
    name: str
    naming: Naming
    # By level name, ranks ascending.
    levels: dict[str, Level]
    # Global: every type's description, by name.
    institution_types: dict[str, str]
    source_types: dict[str, str]
    # The types this country uses, by name.
    uses: dict[str, TypeUse]
    # Domains anyone can publish on: fetchable, never trusted.
    platforms: tuple[str, ...]

    def level(self, name: str) -> Level:
        try:
            return self.levels[name]
        except KeyError:
            raise ValueError(f"{self.name} has no administrative level {name!r}") from None

    def rank_of(self, level: str) -> int:
        return self.level(level).rank

    def government_type(self, level: str) -> str:
        return self.level(level).government_institution_type

    def expected_institution_types(self, level: str) -> list[str]:
        """The checklist for `find_institutions` at a place of this level."""
        return list(self.level(level).expected_institution_types)

    def expected_source_types(self, institution_type: str) -> list[str]:
        """The checklist for `find_sources` at an institution of this type; empty for a type the
        country does not use."""
        use = self.uses.get(institution_type)
        return list(use.expected_source_types) if use is not None else []

    def can_nest(self, parent_level: str, level: str) -> bool:
        """A place's parent must sit at a lower rank than the place's own level."""
        return self.rank_of(parent_level) < self.rank_of(level)

    def levels_above(self, level: str) -> list[str]:
        """The levels a place of `level` may have its parent at, top-down."""
        rank = self.rank_of(level)
        return [name for name, found in self.levels.items() if found.rank < rank]

    def levels_below(self, level: str) -> list[str]:
        rank = self.rank_of(level)
        return [name for name, found in self.levels.items() if found.rank > rank]

    def name_mismatch(self, institution_type: str, name: str) -> str | None:
        """Why `name` does not look like a body of this type, or None when it does, when the
        type has no pattern, or when the type is unknown."""
        use = self.uses.get(institution_type)
        if use is None or use.name_pattern is None or use.name_pattern.search(name):
            return None
        return (
            f"{name!r} does not look like a {institution_type.replace('_', ' ')}'s name: "
            f"expected {use.name_pattern.pattern!r}"
        )

    def is_platform(self, host: str) -> bool:
        """Whether `host` is a platform or sits under one."""
        host = host.lower()
        return any(host == name or host.endswith(f".{name}") for name in self.platforms)

    @cached_property
    def levels_by_rank(self) -> list[Level]:
        return sorted(self.levels.values(), key=lambda level: level.rank)


def build_rules(  # noqa: PLR0913 - one argument per table
    *,
    settings: CountrySettingsInput,
    administrative_levels: list[AdministrativeLevelInput],
    country_institution_types: list[CountryInstitutionTypeInput],
    institution_types: list[InstitutionTypeInput],
    source_types: list[SourceTypeInput],
    platforms: list[str],
) -> CountryRules:
    """The rules from the tables' rows, or from a seed's validated input: the shapes are one."""
    levels = sorted(administrative_levels, key=lambda level: level.rank)
    return CountryRules(
        country_code=settings.country_code,
        name=settings.name,
        naming=Naming(settings.naming_rules),
        levels={
            level.name: Level(
                name=level.name,
                rank=level.rank,
                government_institution_type=level.government_institution_type,
                expected_institution_types=tuple(level.expected_institution_types),
            )
            for level in levels
        },
        institution_types={row.name: row.description for row in institution_types},
        source_types={row.name: row.description for row in source_types},
        uses={
            row.institution_type: TypeUse(
                institution_type=row.institution_type,
                expected_source_types=tuple(row.expected_source_types),
                name_pattern=(
                    re.compile(row.name_pattern, re.IGNORECASE)
                    if row.name_pattern is not None
                    else None
                ),
            )
            for row in country_institution_types
        },
        platforms=tuple(sorted(platforms)),
    )
