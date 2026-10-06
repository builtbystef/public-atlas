"""The five country tables (spec section 4.4). Levels are per country, types are global, and a
country's use of a type is per country. The type tables use the type's name as the primary key,
so rows elsewhere read as words and a rename cascades."""

from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from public_atlas.db.base import Base

# ISO 3166-1 alpha-2, as in `places.country_code`.
COUNTRY_CODE_LENGTH = 2


class CountrySettings(Base):
    """Configuration only: the country as a place is a normal row in `places`."""

    __tablename__ = "country_settings"

    country_code: Mapped[str] = mapped_column(String(COUNTRY_CODE_LENGTH), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    # A rule set, not rows: designators, connectors, leading words and and-words
    # (`schemas.NamingRules`).
    naming_rules: Mapped[dict[str, Any]] = mapped_column(JSONB)


class InstitutionType(Base):
    """Global: one `hospital` for every country."""

    __tablename__ = "institution_types"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    # Shown to the agent: it is what tells two types apart.
    description: Mapped[str] = mapped_column(Text)


class SourceType(Base):
    __tablename__ = "source_types"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    description: Mapped[str] = mapped_column(Text)


class AdministrativeLevel(Base):
    """One level of a country's hierarchy. No parent table: a place's parent must have a lower
    rank than the place's own level, which lets a municipality sit under a region or directly
    under the province."""

    __tablename__ = "administrative_levels"

    country_code: Mapped[str] = mapped_column(
        ForeignKey("country_settings.country_code"), primary_key=True
    )
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    # From the top: the country is 1.
    rank: Mapped[int]
    # The type of this level's government institution.
    government_institution_type: Mapped[str] = mapped_column(
        ForeignKey("institution_types.name", onupdate="CASCADE")
    )
    # The checklist for `find_institutions` at a place of this level. Validated by the API against
    # `institution_types`, not by a foreign key.
    expected_institution_types: Mapped[list[str]] = mapped_column(ARRAY(Text))


class CountryInstitutionType(Base):
    """How this country uses a type: which sources to expect for it and what its names look
    like. The rows also say which types the country uses at all."""

    __tablename__ = "country_institution_types"

    country_code: Mapped[str] = mapped_column(
        ForeignKey("country_settings.country_code"), primary_key=True
    )
    institution_type: Mapped[str] = mapped_column(
        ForeignKey("institution_types.name", onupdate="CASCADE"), primary_key=True
    )
    # The checklist for `find_sources` at an institution of this type. Validated by the API
    # against `source_types`.
    expected_source_types: Mapped[list[str]] = mapped_column(ARRAY(Text))
    # Searched case-insensitively. A name that misses it is saved and sent to review.
    name_pattern: Mapped[str | None] = mapped_column(Text)
