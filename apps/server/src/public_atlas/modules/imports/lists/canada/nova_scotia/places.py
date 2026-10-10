"""Nova Scotia's places from Statistics Canada's 2021 Census and GeoNOVA's *Municipality
Boundaries* layer on the province's open data portal: the 49 municipalities, each with its
code, its 2021 population and its government's legal name. The province is single-tier: every
municipality sits under Nova Scotia, and a county is only a census unit.

The census population table gives every unit's code, names and population and the geographic
attribute file says what each unit is (`canada/statcan.py`, shared with every province). The
GeoNOVA layer is read through the portal's Socrata API for four fields and no geometry: the
legal name (`fullname`), the short name, the kind of municipality (`featdesc`) and the county.
The rules:

- A town (`T`), a district municipality (`MD`) and a regional municipality (`RGM`, and the
  census's `RM` for West Hants) are subdivisions of their own, matched to the layer's row by
  name and kind: the four names a district and a town share (Digby, Lunenburg, Shelburne,
  Yarmouth) are told apart by the kind, and the loader tells the two places apart by the
  designators in their governments' names.
- The nine county municipalities (Annapolis, Antigonish, Colchester, Cumberland, Inverness,
  Kings, Pictou, Richmond, Victoria) have no subdivision of their own: each is counted as two to
  four "subdivisions of county municipality" (`SC`) inside a county division that also holds the
  towns. The municipality takes its division's code, the division's line as its citation and
  the population summed over its `SC` parts; the towns inside the county sit under the province
  like every other municipality.
- The government's name is the layer's legal name ("Municipality of the County of Kings",
  "Region of Queens Municipality", "West Hants Regional Municipality"); the place keeps the
  census's name.
- Indian reserves are not governments and are left out. The layer has no websites:
  `find_homepage` finds them.
"""

import logging
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.files import Format, ListFile, ListFileError, OpenedFile
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.statcan import (
    ATTRIBUTES,
    POPULATION,
    Census,
    Citation,
    Counted,
    Draft,
    census_name,
)

if TYPE_CHECKING:
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = statcan.COUNTRY
PROVINCE = "Nova Scotia"
PROVINCE_CODE = "12"
NOVA_SCOTIA = statcan.Province(PROVINCE_CODE)

MUNICIPALITIES = ListFile(
    name="geonova_municipalities",
    title=(
        "GeoNOVA, Nova Scotia Municipality Boundaries (data.novascotia.ca dataset 7bqh-hssn): "
        "the legal name, short name, kind and county of each municipality, without geometry"
    ),
    url=(
        "https://data.novascotia.ca/resource/7bqh-hssn.json"
        "?$select=fullname,name,featdesc,county&$order=fullname&$limit=1000"
    ),
    sha256="d5f1d814a5742afc0be46bf52f02d8a34996c56d514f182afe7e06610b8dc67c",
    format=Format.JSON,
)
SOURCES = (POPULATION, ATTRIBUTES, MUNICIPALITIES)

MUNICIPAL_TYPES = NOVA_SCOTIA.municipal_types
DROPPED_TYPES = NOVA_SCOTIA.dropped_types
# The layer's kinds, with the census subdivision types each answers to. A county municipality
# answers to no subdivision: it is built from its division's `SC` parts.
KINDS: dict[str, tuple[str, ...]] = {
    "Town": ("T",),
    "Municipal District": ("MD",),
    "Regional Municipality": ("RGM", "RM"),
}
COUNTY = "Municipal County"
COUNTY_PART = "SC"
COUNTY_DIVISION = "CTY"

# No hand corrections: the layer and the census agree on every municipality.
OVERRIDES: dict[str, dict[str, str]] = {}


@dataclass(frozen=True)
class Row:
    legal_name: str
    name: str
    kind: str
    county: str
    line: int


def read_rows(opened: OpenedFile) -> list[Row]:
    """The layer's records, one per line of the stored text."""
    if not isinstance(opened.document, list):
        raise ListFileError(f"{MUNICIPALITIES.name}: expected a list of records")
    return [
        Row(
            legal_name=" ".join(record["fullname"].split()),
            name=" ".join(record["name"].split()),
            kind=record["featdesc"],
            county=record["county"],
            line=line,
        )
        for line, record in enumerate(opened.document, 1)
    ]


@dataclass
class Notes:
    dropped: Counter[str] = field(default_factory=Counter)
    # Each county municipality with the parts summed into it.
    counties: list[str] = field(default_factory=list)

    def log(self) -> None:
        for type_, count in sorted(self.dropped.items()):
            logger.info(
                "left out %d %s subdivisions (%s)", count, DROPPED_TYPES.get(type_, type_), type_
            )
        for line in self.counties:
            logger.info("county municipality built from its parts: %s", line)


def _matches(row: Row, unit: Counted) -> bool:
    return census_name(unit).casefold() == row.name.casefold() and unit.type_ in KINDS[row.kind]


def build(files: Mapping[str, OpenedFile]) -> tuple[list[PlaceEntry], Notes]:
    census = NOVA_SCOTIA.read(files)
    rows = read_rows(files[MUNICIPALITIES.name])
    notes = Notes()
    found: list[PlaceEntry] = []
    taken: set[str] = set()
    for row in rows:
        citation = Citation(source=MUNICIPALITIES.name, line=row.line)
        if row.kind == COUNTY:
            draft = _county(census, row, notes)
        else:
            units = [unit for unit in census.municipalities if _matches(row, unit)]
            if len(units) != 1:
                raise ListFileError(
                    f"{MUNICIPALITIES.name}: {len(units)} census subdivisions answer to "
                    f"{row.legal_name!r} ({row.kind})"
                )
            draft = Draft(unit=units[0], name=census_name(units[0]), parent=PROVINCE)
        draft.government = row.legal_name
        draft.government_citation = citation
        taken.add(draft.unit.code)
        found.append(draft.entry())
    for unit in census.municipalities:
        if unit.code not in taken:
            raise ListFileError(
                f"{MUNICIPALITIES.name}: no row for census municipality {unit.code} "
                f"{unit.names[0]} ({unit.type_})"
            )
    for type_, count in census.dropped().items():
        if type_ != COUNTY_PART:
            notes.dropped[type_] += count
    return sorted(found, key=lambda entry: entry.name), notes


def _county(census: Census, row: Row, notes: Notes) -> Draft:
    """A county municipality: its county division's code and line, the population of its
    `SC` parts."""
    divisions = [
        unit
        for unit in census.divisions.values()
        if unit.type_ == COUNTY_DIVISION and census_name(unit).casefold() == row.name.casefold()
    ]
    if len(divisions) != 1:
        raise ListFileError(f"{MUNICIPALITIES.name}: no county division named {row.name!r}")
    division = divisions[0]
    parts = [
        unit
        for unit in census.subdivisions
        if unit.division == division.code and unit.type_ == COUNTY_PART
    ]
    if not parts or any(unit.population is None for unit in parts):
        raise ListFileError(
            f"{MUNICIPALITIES.name}: county division {division.code} {row.name} has no counted "
            "subdivisions of county municipality"
        )
    population = sum(unit.population or 0 for unit in parts)
    notes.counties.append(
        f"{division.code} {row.legal_name}: {', '.join(unit.names[0] for unit in parts)} = "
        f"{population}"
    )
    return Draft(unit=division, name=census_name(division), parent=PROVINCE, population=population)


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[PlaceEntry]:
    """Nova Scotia's 49 municipalities, under the province."""
    del rules
    found, notes = build(files)
    notes.log()
    return found
