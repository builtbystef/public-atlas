"""Newfoundland and Labrador's places from Statistics Canada's 2021 Census: the 277
municipalities (3 cities, 269 towns and the 5 Inuit community governments of Nunatsiavut),
each with its code, its 2021 population and its government's composed name. The province is
single-tier: every municipality sits under Newfoundland and Labrador, and a census division is
only a census unit.

The census population table gives every unit's code, names and population and the geographic
attribute file says what each unit is (`canada/statcan.py`, shared with every province). The
province's *Directory of Towns, Inuit Community Governments and Cities* is a PDF whose table
the parser renders as one line per page (table structure is off, spec section 8.3), so no row
can cite its own municipality and the directory is not a source yet; it names no websites. The
rules:

- A city (`CY`) or a town (`T`) is a municipality named as the census names it. The
  government's name is composed from the type: "City of St. John's", "Town of Gander". The
  five Inuit community governments the census types as towns are named "Nain Inuit Community
  Government" and so on, by `OVERRIDES`.
- Where the census qualifies a name to tell it from another ("Charlottetown (Labrador)",
  "Woody Point, Bonne Bay", "Seal Cove (Fortune Bay)"), the qualified name is the place's, the
  bare name is an alias unless two municipalities share it (the two Seal Coves), and the
  government is composed from the bare name.
- Subdivisions of unorganized areas and Indian reserves are not governments and are left out.
- No website is loaded: `find_homepage` finds them.
"""

import logging
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.files import OpenedFile
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.statcan import (
    ATTRIBUTES,
    POPULATION,
    Draft,
    census_name,
    composed_government,
)

if TYPE_CHECKING:
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = statcan.COUNTRY
PROVINCE = "Newfoundland and Labrador"
PROVINCE_CODE = "10"
NEWFOUNDLAND = statcan.Province(PROVINCE_CODE)
SOURCES = (POPULATION, ATTRIBUTES)

MUNICIPAL_TYPES = NEWFOUNDLAND.municipal_types
DROPPED_TYPES = NEWFOUNDLAND.dropped_types
# A qualifier the census adds to a name: ", Labrador", " (Fortune Bay)".
_QUALIFIER = re.compile(r"\s*(?:,\s*[^,()]+|\([^()]+\))$")
INUIT_COMMUNITY_GOVERNMENT = "Inuit Community Government"

# Hand corrections keyed by census code, each with its reason: `government`, the name of a
# government the census type does not compose.
OVERRIDES: dict[str, dict[str, str]] = {
    code: {
        "government": f"{name} {INUIT_COMMUNITY_GOVERNMENT}",
        "reason": "an Inuit community government under the Labrador Inuit Land Claims "
        "Agreement, which the census types as a town",
    }
    for code, name in (
        ("1011035", "Nain"),
        ("1011030", "Hopedale"),
        ("1011020", "Makkovik"),
        ("1011015", "Postville"),
        ("1011010", "Rigolet"),
    )
}


@dataclass
class Notes:
    dropped: Counter[str] = field(default_factory=Counter)
    qualified: list[str] = field(default_factory=list)
    overrides: list[str] = field(default_factory=list)

    def log(self) -> None:
        for type_, count in sorted(self.dropped.items()):
            logger.info(
                "left out %d %s subdivisions (%s)", count, DROPPED_TYPES.get(type_, type_), type_
            )
        for line in self.qualified:
            logger.info("qualified census name: %s", line)
        for line in self.overrides:
            logger.info("override: %s", line)


def bare_name(name: str) -> str:
    """The name without the census's qualifier: "Charlottetown" for "Charlottetown
    (Labrador)"."""
    return _QUALIFIER.sub("", name).strip()


def build(files: Mapping[str, OpenedFile]) -> tuple[list[PlaceEntry], Notes]:
    census = NEWFOUNDLAND.read(files)
    notes = Notes()
    found = []
    # The loader finds a place by its aliases too: the two Seal Coves keep their qualified
    # names and no bare alias, or the second would be read as the first.
    bare_names = Counter(bare_name(census_name(unit)) for unit in census.municipalities)
    for unit in census.subdivisions:
        if unit.type_ not in MUNICIPAL_TYPES:
            notes.dropped[unit.type_] += 1
            continue
        name = census_name(unit)
        bare = bare_name(name)
        draft = Draft(unit=unit, name=name, parent=PROVINCE)
        if bare != name:
            notes.qualified.append(f"{unit.code} {name} -> {bare}")
            if bare_names[bare] == 1:
                draft.alias(bare)
        draft.government = composed_government(NEWFOUNDLAND, unit, bare)
        fields = OVERRIDES.get(unit.code)
        if fields is not None:
            if bare_name(bare) != fields["government"].removesuffix(
                f" {INUIT_COMMUNITY_GOVERNMENT}"
            ):
                raise ValueError(
                    f"override {unit.code} names {fields['government']!r}, not {name!r}"
                )
            draft.government = fields["government"]
            notes.overrides.append(f"{unit.code} {name}: {fields['reason']}")
        found.append(draft.entry())
    return sorted(found, key=lambda entry: entry.name), notes


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[PlaceEntry]:
    """Newfoundland and Labrador's 277 municipalities, under the province."""
    del rules
    found, notes = build(files)
    notes.log()
    return found
