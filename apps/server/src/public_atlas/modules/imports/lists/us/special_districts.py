"""The United States' special districts from the 2022 Census of Governments' list of government
units (the Special District sheet, 39,555 rows): the independent fire, water, sewer, transit,
library, hospital, park, housing and other districts, each typed by the function the census
gives it, attached to its county, with its Census of Governments id in `census_gid` and its
website as a candidate homepage. The rules:

- The function (`FUNCTION_NAME`) gives the type: fire protection (24, and 96 with water supply)
  is `fire_service`; water supply, sewerage, electric power, gas supply, solid waste and the
  combined utilities (91, 80, 92, 93, 81, 98, 97) are `public_utility`; mass transit (94) is
  `transit_agency`; libraries (52) `library`; hospitals (40) `hospital`; parks and recreation
  and other natural resources (61, 59) `park_district`; housing, airports, ports, parking and
  industrial development (50, 01, 87, 60, 41) `municipal_corporation`; police protection (62)
  `police_service`. Every other function (cemeteries, drainage, flood control, irrigation, soil
  and water conservation, highways, health, correctional, welfare, education, mortgage credit,
  the single- and multi-function districts the census does not name) is `other` with the
  function's words as the suggested type, for the reviewer.
- An inactive row (`IS_ACTIVE` N) is left out and counted. A row with no Census of Governments
  id (a unit added after the ids were assigned) is loaded with no identifier and counted.
- The place is the district's county when it is a loaded place; else the loaded municipality
  under the state the county row or the address city names; else the state (`us/loaded.py`).
- The sheet writes names in capitals; `governments.title_case` recases them ("Prattville
  Housing Authority", "Harris County MUD 400").
- The website is the row's, cleaned (`governments.website`).
"""

import logging
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field

from public_atlas.modules.countries.service import CountryRules
from public_atlas.modules.graph.models import IdentifierScheme
from public_atlas.modules.imports.entries import Citation, Code, Fact, InstitutionEntry
from public_atlas.modules.imports.files import OpenedFile
from public_atlas.modules.imports.lists.us import governments
from public_atlas.modules.imports.lists.us.census import SUB_EST, Estimates
from public_atlas.modules.imports.lists.us.governments import GOVT_UNITS, SPECIAL_DISTRICT
from public_atlas.modules.imports.lists.us.loaded import Places

logger = logging.getLogger(__name__)

COUNTRY = "US"
SOURCES = (GOVT_UNITS, SUB_EST)
OTHER = "other"
# The type of each function, by the function's code.
FUNCTIONS: dict[str, str] = {
    "24": "fire_service",
    "96": "fire_service",
    "91": "public_utility",
    "80": "public_utility",
    "92": "public_utility",
    "93": "public_utility",
    "81": "public_utility",
    "98": "public_utility",
    "97": "public_utility",
    "94": "transit_agency",
    "52": "library",
    "40": "hospital",
    "61": "park_district",
    "59": "park_district",
    "50": "municipal_corporation",
    "01": "municipal_corporation",
    "87": "municipal_corporation",
    "60": "municipal_corporation",
    "41": "municipal_corporation",
    "62": "police_service",
}

# Hand corrections keyed by the district's name, each with its reason. None are needed yet.
OVERRIDES: dict[str, dict[str, str]] = {}


@dataclass
class Notes:
    """What the build typed, placed or left out, logged for the operator and pinned by the
    rule test."""

    # Loaded districts by type.
    typed: Counter[str] = field(default_factory=Counter)
    # Districts of type other by their suggested type.
    suggested: Counter[str] = field(default_factory=Counter)
    # Districts by the level of their place.
    placed: Counter[str] = field(default_factory=Counter)
    inactive: int = 0
    no_id: int = 0
    websites: int = 0

    def log(self) -> None:
        for institution_type, count in sorted(self.typed.items()):
            logger.info("%d districts typed %s", count, institution_type)
        for suggested, count in sorted(self.suggested.items()):
            logger.info("%d districts of type other: %s", count, suggested)
        for level, count in sorted(self.placed.items()):
            logger.info("%d districts at a %s", count, level)
        logger.info(
            "left out %d inactive rows; %d districts have no Census of Governments id; %d have "
            "a website",
            self.inactive,
            self.no_id,
            self.websites,
        )


def function_type(function: str) -> tuple[str, str | None]:
    """The type of a function ("24 - LOCAL FIRE PROTECTION"), and the suggested type for one
    typed other ("cemeteries")."""
    code, _, words = function.partition(" - ")
    institution_type = FUNCTIONS.get(code, OTHER)
    if institution_type != OTHER:
        return institution_type, None
    return OTHER, " ".join(words.split()).lower()


def build(
    files: Mapping[str, OpenedFile], rules: CountryRules
) -> tuple[list[InstitutionEntry], Notes]:
    """The entries and the notes of the build."""
    notes = Notes()
    places = Places(Estimates(files[SUB_EST.name]), rules.naming)
    found: list[InstitutionEntry] = []
    for unit in governments.read_units(files[GOVT_UNITS.name], SPECIAL_DISTRICT):
        if not unit.active:
            notes.inactive += 1
            continue
        institution_type, suggested_type = function_type(unit.function)
        place = places.attach(
            unit.fips_state, unit.fips_county, city=governments.title_case(unit.city)
        )
        if place is None:
            raise ValueError(f"{GOVT_UNITS.name}: no state for {unit.name} ({unit.state})")
        notes.typed[institution_type] += 1
        if suggested_type is not None:
            notes.suggested[suggested_type] += 1
        notes.placed[place.level] += 1
        codes: tuple[Code, ...] = ()
        if unit.gid is not None:
            codes = (Code(scheme=IdentifierScheme.CENSUS_GID, value=unit.gid),)
        else:
            notes.no_id += 1
        citation = Citation(source=GOVT_UNITS.name, line=unit.line)
        citations: dict[Fact, Citation] = {"institution": citation}
        if unit.website is not None:
            citations["homepage"] = citation
            notes.websites += 1
        found.append(
            InstitutionEntry(
                name=governments.title_case(unit.name),
                institution_type=institution_type,
                suggested_type=suggested_type,
                codes=codes,
                place=place.name,
                place_level=place.level,
                place_parent=place.parent,
                homepage=unit.website,
                citations=citations,
            )
        )
    return found, notes


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[InstitutionEntry]:
    """Every active district, in the sheet's order."""
    found, notes = build(files, rules)
    notes.log()
    return found
