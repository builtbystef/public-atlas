"""The United States' states and county equivalents from the Census Bureau's Vintage 2025
population estimates (SUB-EST2025), each with its FIPS code, its 2025 population and its
government's name; and Puerto Rico's 78 municipios from the 2026 Gazetteer and the Puerto Rico
estimates table, since SUB-EST2025 leaves Puerto Rico out. The files and their readers are
shared with the municipalities list (`us/census.py`); the rules below are this list's:

- A state row (summary level 040) is the state the seed anchored, named as the census names it:
  the list adds its code and its population. The 51 rows are the fifty states and the District
  of Columbia. Puerto Rico's code is its FIPS state code and its population the estimates
  table's own row.
- A county row (050) is a county place when its functional status says it is a government (A,
  B or C; `census.ACTIVE`). An A or B county's government is named as the census names the
  unit ("Cook County", "Orleans Parish", "Fairbanks North Star Borough"); the 2020 code file
  gives its class, which the rule test pins. A county consolidated with its city (C, 33: San
  Francisco, Denver, Philadelphia, the five boroughs of New York, Marion County around
  Indianapolis...) is a place with no government: the consolidated government is the city's,
  loaded by the municipalities list on the municipality inside the county, and the places still
  incorporated inside (Jacksonville Beach in Duval County) sit under the county. East Baton
  Rouge and Lafayette parishes (B) keep their governments beside their cities'.
- Rows the status drops: F (42: the District's county row and the 41 independent cities, which
  the municipalities list loads under their state), G (Kalawao County, which the state health
  department administers), N (23: Connecticut's nine planning regions, nine Massachusetts
  counties and Rhode Island's five) and S (11: the census areas of Alaska's Unorganized
  Borough). A municipality inside one sits under its state.
- Honolulu County (15003) is promoted: it is the one county whose government is the municipal
  government of the whole county with no place row of its own (Urban Honolulu is a census
  designated place), so it is loaded at the municipality level under Hawaii as the City and
  County of Honolulu. The override carries it.
- A Puerto Rico municipio is both the county equivalent and the municipal government: loaded at
  the municipality level under Puerto Rico with its county code, named from the Gazetteer
  ("Adjuntas Municipio" is the place Adjuntas and the Municipality of Adjuntas, with the
  Spanish name as an alias) and with its population from the estimates table.

A state's places sit under it by name and level; a county's name is not unique across states
(thirty Washington Counties), so the municipalities list names a county parent with its state.
"""

import logging
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from public_atlas.modules.countries.service import CountryRules
from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.imports.entries import AliasEntry, Citation, Code, Figure, PlaceEntry
from public_atlas.modules.imports.files import ListFileError, OpenedFile
from public_atlas.modules.imports.lists.us import census
from public_atlas.modules.imports.lists.us.census import (
    COUNTRY_LEVEL,
    COUNTRY_NAME,
    COUNTY_CODES,
    COUNTY_LEVEL,
    GAZETTEER_COUNTIES,
    MUNICIPALITY_LEVEL,
    PUERTO_RICO,
    PUERTO_RICO_CODE,
    PUERTO_RICO_POPULATION,
    STATE_LEVEL,
    SUB_EST,
    SUMLEV_COUNTY,
    SUMLEV_STATE,
    Estimates,
    Unit,
)

logger = logging.getLogger(__name__)

COUNTRY = "US"
SOURCES = (SUB_EST, COUNTY_CODES, GAZETTEER_COUNTIES, PUERTO_RICO_POPULATION)
CONSOLIDATED = "C"
# The Gazetteer's state column and the suffix of its Puerto Rico names.
PUERTO_RICO_USPS = "PR"
MUNICIPIO = " Municipio"

# Hand corrections, keyed by FIPS code, each with its reason. Fields: `level` (the level the
# unit is loaded at), `government` (the government's name when the census name is not it).
OVERRIDES: dict[str, dict[str, str]] = {
    "15003": {
        "level": MUNICIPALITY_LEVEL,
        "government": "City and County of Honolulu",
        "reason": (
            "Honolulu County's government is the municipal government of the whole county and "
            "the census has no place row for it (Urban Honolulu is a CDP): loaded as a "
            "municipality under Hawaii"
        ),
    },
}
# The counties loaded at the municipality level, which the municipalities list must not name as
# a parent.
PROMOTED_COUNTIES = frozenset(
    code for code, fields in OVERRIDES.items() if fields.get("level") == MUNICIPALITY_LEVEL
)


@dataclass
class Notes:
    """What the build dropped, left without a government or corrected, logged for the operator
    and pinned by the rule test."""

    # Counties by their 2020 class and functional status.
    classes: Counter[tuple[str, str]] = field(default_factory=Counter)
    # The county rows dropped, by functional status.
    dropped: dict[str, list[str]] = field(default_factory=dict)
    # The counties loaded with no government, consolidated with their city.
    consolidated: list[str] = field(default_factory=list)
    overrides: list[str] = field(default_factory=list)

    def log(self) -> None:
        for status, names in sorted(self.dropped.items()):
            logger.info(
                "left out %d county rows (%s): %s",
                len(names),
                census.FUNCTIONAL_STATUS.get(status, status),
                ", ".join(names),
            )
        for name in self.consolidated:
            logger.info("no government of its own for %s: consolidated with its city", name)
        for line in self.overrides:
            logger.info("override: %s", line)


def _state_entry(unit: Unit) -> PlaceEntry:
    return PlaceEntry(
        name=unit.name,
        level=STATE_LEVEL,
        parent=COUNTRY_NAME,
        parent_level=COUNTRY_LEVEL,
        government=census.state_government(unit.name),
        code=Code(scheme=IdentifierScheme.FIPS, value=unit.fips),
        figures=(unit.figure,),
        citations={"place": unit.citation},
    )


def _puerto_rico_entry(populations: Mapping[str, tuple[int, int]]) -> PlaceEntry:
    population, line = populations[PUERTO_RICO]
    citation = Citation(source=PUERTO_RICO_POPULATION.name, line=line)
    return PlaceEntry(
        name=PUERTO_RICO,
        level=STATE_LEVEL,
        parent=COUNTRY_NAME,
        parent_level=COUNTRY_LEVEL,
        government=census.state_government(PUERTO_RICO),
        code=Code(scheme=IdentifierScheme.FIPS, value=PUERTO_RICO_CODE),
        figures=(
            Figure(
                name=MetricName.POPULATION,
                year=census.ESTIMATES_YEAR,
                value=Decimal(population),
                citation=citation,
            ),
        ),
        citations={"place": citation},
    )


def _county_entry(unit: Unit, notes: Notes) -> PlaceEntry:
    fields = OVERRIDES.get(unit.fips, {})
    level = fields.get("level", COUNTY_LEVEL)
    if "government" in fields:
        government: str | None = fields["government"]
    elif unit.funcstat == CONSOLIDATED:
        government = None
        notes.consolidated.append(f"{unit.fips} {unit.name}, {unit.state_name}")
    else:
        government = unit.name
    if fields:
        notes.overrides.append(f"{unit.fips} {unit.name}: {fields['reason']}")
    return PlaceEntry(
        name=unit.name,
        level=level,
        parent=unit.state_name,
        parent_level=STATE_LEVEL,
        government=government,
        code=Code(scheme=IdentifierScheme.FIPS, value=unit.fips),
        figures=(unit.figure,),
        citations={"place": unit.citation},
    )


def _municipio_entries(
    gazetteer: OpenedFile, populations: Mapping[str, tuple[int, int]]
) -> list[PlaceEntry]:
    entries = []
    for row in gazetteer.rows:
        if row["USPS"] != PUERTO_RICO_USPS:
            continue
        census_name = row["NAME"]
        if not census_name.endswith(MUNICIPIO):
            raise ListFileError(f"{GAZETTEER_COUNTIES.name}: not a municipio: {census_name!r}")
        if census_name not in populations:
            raise ListFileError(f"{PUERTO_RICO_POPULATION.name}: no row for {census_name!r}")
        name = census_name.removesuffix(MUNICIPIO)
        population, population_line = populations[census_name]
        place = Citation(source=GAZETTEER_COUNTIES.name, line=row.line)
        entries.append(
            PlaceEntry(
                name=name,
                aliases=(AliasEntry(text=f"Municipio de {name}", language="es"),),
                level=MUNICIPALITY_LEVEL,
                parent=PUERTO_RICO,
                parent_level=STATE_LEVEL,
                government=f"Municipality of {name}",
                code=Code(scheme=IdentifierScheme.FIPS, value=row["GEOID"]),
                figures=(
                    Figure(
                        name=MetricName.POPULATION,
                        year=census.ESTIMATES_YEAR,
                        value=Decimal(population),
                        citation=Citation(source=PUERTO_RICO_POPULATION.name, line=population_line),
                    ),
                ),
                citations={"place": place},
            )
        )
    return entries


def build(files: Mapping[str, OpenedFile]) -> tuple[list[PlaceEntry], Notes]:
    """The entries and the notes of the build."""
    estimates = Estimates(files[SUB_EST.name])
    classes = census.read_classes(files[COUNTY_CODES.name], "STATEFP", "COUNTYFP")
    populations = census.puerto_rico_populations(files[PUERTO_RICO_POPULATION.name])
    notes = Notes()
    states = [_state_entry(unit) for unit in estimates.units(SUMLEV_STATE)]
    states.append(_puerto_rico_entry(populations))
    counties: list[PlaceEntry] = []
    for unit in estimates.units(SUMLEV_COUNTY):
        notes.classes[classes.get((unit.state, unit.county), "?"), unit.funcstat] += 1
        if not unit.active:
            notes.dropped.setdefault(unit.funcstat, []).append(
                f"{unit.fips} {unit.name}, {unit.state_name}"
            )
            continue
        counties.append(_county_entry(unit, notes))
    municipios = _municipio_entries(files[GAZETTEER_COUNTIES.name], populations)
    return [*states, *counties, *municipios], notes


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[PlaceEntry]:
    """The states, the county equivalents that are governments or hold one, and Puerto Rico's
    municipios."""
    del rules  # The names are composed by the census kind alone.
    found, notes = build(files)
    notes.log()
    return found
