"""British Columbia's places from Statistics Canada's 2021 Census and the province's legal
administrative boundaries in the BC Data Catalogue: the 28 regional districts as regions, each
with its government, and the 160 municipalities under them, each with its code, its 2021
population and its government's legal name.

The census population table gives every unit's code, names and population and the geographic
attribute file says what each unit is (`canada/statcan.py`, shared with every province). The
two boundary layers (`ABMS_MUNICIPALITIES_SP`, `ABMS_REGIONAL_DISTRICTS_SP`) are read from
the catalogue's WFS service as CSV, one row per feature with the legal name, the abbreviation
and, for a municipality, the regional district it belongs to; the service's GeoJSON would be
one record holding every feature, which the loader renders as one line, so each row could not
cite its own. The rules:

- A regional district (`RD`) is a region with a government, named as the layer names it
  ("Regional District of North Okanagan", "Capital Regional District"); the place keeps the
  census's name, and where the layer's differs (Metro Vancouver, which the census still calls
  Greater Vancouver; qathet, still Powell River; North Coast, still Skeena-Queen Charlotte)
  the layer's name is the place's and the census's an alias. The Stikine region (`REG`) is
  unincorporated, and the Northern Rockies division holds only the regional municipality that
  replaced its regional district in 2009: census units, no place, and the Northern Rockies
  Regional Municipality sits under the province.
- A municipality (`CY`, `DM`, `T`, `VL`, `IM`, `RGM`) is matched to the layer's row by the
  place name inside the legal name and, where two municipalities share a name (the City and the
  Township of Langley, the City and the District of North Vancouver), by the kind of body the
  designator says. Its parent is the regional district the layer names, which is also its
  census division. Where the layer and the census spell a name differently, `OVERRIDES` names
  the row, and the municipality's own spelling wins (100 Mile House; Daajing Giids, which the
  census still calls Queen Charlotte) with the census's as an alias. The government's name is
  the legal name ("The Corporation of the District of North Vancouver", "Bowen Island
  Municipality", "Sun Peaks Mountain Resort Municipality").
- Electoral areas, Indian reserves, Indian settlements and the treaty lands are not
  municipalities and are left out.
- The layer's website field is empty for every row, so no homepage is loaded:
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
    PROVINCE_LEVEL,
    REGION,
    Citation,
    Counted,
    Draft,
    census_name,
)
from public_atlas.shared.text import name_key

if TYPE_CHECKING:
    from public_atlas.modules.countries.naming import Naming
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = statcan.COUNTRY
PROVINCE = "British Columbia"
PROVINCE_CODE = "59"
BRITISH_COLUMBIA = statcan.Province(PROVINCE_CODE)

_WFS = (
    "https://openmaps.gov.bc.ca/geo/pub/WHSE_LEGAL_ADMIN_BOUNDARIES.{layer}/ows"
    "?service=WFS&version=2.0.0&request=GetFeature&typeName=WHSE_LEGAL_ADMIN_BOUNDARIES.{layer}"
    "&outputFormat=csv&propertyName={fields}&sortBy=ADMIN_AREA_NAME"
)
MUNICIPALITIES = ListFile(
    name="bc_municipalities",
    title=(
        "BC Data Catalogue, Municipalities - Legally Defined Administrative Areas of BC "
        "(WHSE_LEGAL_ADMIN_BOUNDARIES.ABMS_MUNICIPALITIES_SP), as CSV from the WFS service"
    ),
    url=_WFS.format(
        layer="ABMS_MUNICIPALITIES_SP",
        fields=(
            "LGL_ADMIN_AREA_ID,ADMIN_AREA_NAME,ADMIN_AREA_ABBREVIATION,ADMIN_AREA_BOUNDARY_TYPE,"
            "ADMIN_AREA_GROUP_NAME,WEBSITE_URL,OIC_MO_YEAR"
        ),
    ),
    sha256="5d7a1940d4806ba8b0d12aa12036870212922af0736eed17a239b99e33717391",
    format=Format.CSV,
    columns=(
        "LGL_ADMIN_AREA_ID",
        "ADMIN_AREA_NAME",
        "ADMIN_AREA_ABBREVIATION",
        "ADMIN_AREA_GROUP_NAME",
        "WEBSITE_URL",
    ),
)
REGIONAL_DISTRICTS = ListFile(
    name="bc_regional_districts",
    title=(
        "BC Data Catalogue, Regional Districts - Legally Defined Administrative Areas of BC "
        "(WHSE_LEGAL_ADMIN_BOUNDARIES.ABMS_REGIONAL_DISTRICTS_SP), as CSV from the WFS service"
    ),
    url=_WFS.format(
        layer="ABMS_REGIONAL_DISTRICTS_SP",
        fields=(
            "LGL_ADMIN_AREA_ID,ADMIN_AREA_NAME,ADMIN_AREA_ABBREVIATION,ADMIN_AREA_BOUNDARY_TYPE,"
            "WEBSITE_URL,OIC_MO_YEAR"
        ),
    ),
    sha256="d596019a276dbe98111093c06451bf07243c8d7fe2e132db5874917deb9d037e",
    format=Format.CSV,
    columns=("LGL_ADMIN_AREA_ID", "ADMIN_AREA_NAME", "ADMIN_AREA_ABBREVIATION", "WEBSITE_URL"),
)
SOURCES = (POPULATION, ATTRIBUTES, MUNICIPALITIES, REGIONAL_DISTRICTS)

UPPER_TIER_TYPES = BRITISH_COLUMBIA.upper_tier_types
CENSUS_ONLY_TYPES = BRITISH_COLUMBIA.census_only_types
MUNICIPAL_TYPES = BRITISH_COLUMBIA.municipal_types
DROPPED_TYPES = BRITISH_COLUMBIA.dropped_types
REGIONAL_DISTRICT = "Regional District"
# The census types a legal name's designator answers to, when two municipalities share a name.
# Every other designator (District, Township, Island Municipality, Resort Municipality,
# Regional Municipality) is a district municipality or a kind of its own with no namesake.
CITY_TYPES = frozenset({"CY"})
REGIONAL_MUNICIPALITY = "RGM"
# The layer's group of a municipality under no regional district.
NO_GROUP = "-"

# Hand corrections keyed by census code, each with its reason: `name`, the layer's name where
# it is the current one and the census's an alias; `legal_name`, the layer's row for a
# municipality whose name the census writes otherwise.
OVERRIDES: dict[str, dict[str, str]] = {
    "5941005": {
        "legal_name": "District of 100 Mile House",
        "name": "100 Mile House",
        "reason": "the municipality writes its name in figures; the census spells them out",
    },
    "5955025": {
        "legal_name": "District of Hudsons Hope",
        "reason": "the layer drops the apostrophe of Hudson's Hope",
    },
    "5947026": {
        "legal_name": "Village of Daajing Giids",
        "name": "Daajing Giids",
        "reason": "the Village of Queen Charlotte became Daajing Giids in 2022; the census keeps "
        "Queen Charlotte",
    },
    "5915": {
        "name": "Metro Vancouver",
        "reason": "the regional district renamed itself Metro Vancouver in 2017; the census "
        "keeps Greater Vancouver",
    },
    "5947": {
        "name": "North Coast",
        "reason": "the Skeena-Queen Charlotte Regional District became the North Coast Regional "
        "District in 2016; the census keeps Skeena-Queen Charlotte",
    },
    "5927": {
        "name": "qathet",
        "reason": "the Powell River Regional District became the qathet Regional District in "
        "2018; the census keeps Powell River",
    },
}


@dataclass(frozen=True)
class Row:
    legal_name: str
    abbreviation: str
    # The regional district a municipality belongs to; "" for a regional district.
    group: str
    line: int


def read_rows(opened: OpenedFile) -> list[Row]:
    return [
        Row(
            legal_name=" ".join(row["ADMIN_AREA_NAME"].split()),
            abbreviation=row["ADMIN_AREA_ABBREVIATION"],
            group=row.get("ADMIN_AREA_GROUP_NAME", ""),
            line=row.line,
        )
        for row in opened.rows
    ]


def district_core(legal_name: str) -> str:
    """The place name inside a regional district's legal name: "North Okanagan" for "Regional
    District of North Okanagan", "Capital" for "Capital Regional District"."""
    name = legal_name.removeprefix(f"{REGIONAL_DISTRICT} of ").removesuffix(f" {REGIONAL_DISTRICT}")
    return name.strip()


@dataclass
class Notes:
    dropped: Counter[str] = field(default_factory=Counter)
    census_only: list[str] = field(default_factory=list)
    renamed: list[str] = field(default_factory=list)
    # Municipalities whose census division is not the regional district the layer names.
    moved: list[str] = field(default_factory=list)
    # Layer rows no municipality or district took.
    untaken: list[str] = field(default_factory=list)

    def log(self) -> None:
        for type_, count in sorted(self.dropped.items()):
            logger.info(
                "left out %d %s subdivisions (%s)", count, DROPPED_TYPES.get(type_, type_), type_
            )
        for line in self.census_only:
            logger.info("no place for census-only division %s", line)
        for line in self.renamed:
            logger.info("the layer names otherwise than the census: %s", line)
        for line in self.moved:
            logger.warning("the layer puts a municipality in another regional district: %s", line)
        for line in self.untaken:
            logger.warning("layer row no place took: %s", line)


class Builder:
    def __init__(self, files: Mapping[str, OpenedFile], naming: Naming) -> None:
        self.naming = naming
        self.census = BRITISH_COLUMBIA.read(files)
        self.districts = read_rows(files[REGIONAL_DISTRICTS.name])
        self.municipalities = read_rows(files[MUNICIPALITIES.name])
        self.notes = Notes()
        # Region name by census division code, and by the layer's legal name.
        self.region_of_division: dict[str, str] = {}
        self.region_of_legal_name: dict[str, str] = {}

    def regions(self) -> list[PlaceEntry]:
        found = []
        by_core = {name_key(district_core(row.legal_name)): row for row in self.districts}
        for code, division in self.census.divisions.items():
            if division.type_ in CENSUS_ONLY_TYPES:
                self.notes.census_only.append(f"{code} {division.names[0]} ({division.type_})")
                continue
            if division.type_ not in UPPER_TIER_TYPES:
                raise ListFileError(
                    f"census division {code} has an unknown type {division.type_!r}"
                )
            fields = OVERRIDES.get(code, {})
            name = fields.get("name", census_name(division))
            row = by_core.get(name_key(name))
            if row is None and self._is_regional_municipality(code):
                # The Northern Rockies Regional Municipality replaced its regional district in
                # 2009; the census keeps the division around the one municipality.
                self.notes.census_only.append(
                    f"{code} {division.names[0]} ({division.type_}): a regional municipality"
                )
                continue
            if row is None:
                raise ListFileError(
                    f"{REGIONAL_DISTRICTS.name}: no regional district named {name!r} for census "
                    f"division {code}"
                )
            draft = Draft(unit=division, name=name, parent=PROVINCE, level=REGION)
            if name != census_name(division):
                self.notes.renamed.append(f"{code} {census_name(division)} -> {name}")
                draft.alias(census_name(division))
            draft.government = row.legal_name
            draft.government_citation = Citation(source=REGIONAL_DISTRICTS.name, line=row.line)
            self.region_of_division[code] = name
            self.region_of_legal_name[row.legal_name] = name
            found.append(draft.entry())
        for row in self.districts:
            if row.legal_name not in self.region_of_legal_name:
                self.notes.untaken.append(row.legal_name)
        return sorted(found, key=lambda entry: entry.name)

    def _is_regional_municipality(self, division_code: str) -> bool:
        inside = [unit for unit in self.census.subdivisions if unit.division == division_code]
        return any(unit.type_ == REGIONAL_MUNICIPALITY for unit in inside)

    def _row_for(self, unit: Counted, namesakes: int) -> Row:
        """The layer's row whose legal name is the municipality's: the one an override names,
        else by the place name inside it, then, for a shared name, by whether the designator
        says a city."""
        legal_name = OVERRIDES.get(unit.code, {}).get("legal_name")
        if legal_name is not None:
            rows = [row for row in self.municipalities if row.legal_name == legal_name]
        else:
            forms = self.naming.forms(census_name(unit))
            rows = [row for row in self.municipalities if self.naming.core(row.legal_name) in forms]
        if namesakes > 1 and len(rows) > 1:
            cities = self.naming.designators_in("City")
            rows = [
                row
                for row in rows
                if bool(self.naming.designators_in(row.legal_name) & cities)
                == (unit.type_ in CITY_TYPES)
            ]
        if len(rows) != 1:
            raise ListFileError(
                f"{MUNICIPALITIES.name}: {len(rows)} rows answer to {unit.code} {unit.names[0]} "
                f"({unit.type_})"
            )
        return rows[0]

    def municipality_entries(self) -> list[PlaceEntry]:
        found = []
        names = Counter(census_name(unit) for unit in self.census.municipalities)
        taken: set[int] = set()
        for unit in self.census.subdivisions:
            if unit.type_ not in MUNICIPAL_TYPES:
                self.notes.dropped[unit.type_] += 1
                continue
            row = self._row_for(unit, names[census_name(unit)])
            taken.add(row.line)
            # A regional municipality (group "-") has no regional district above it.
            region = None if row.group == NO_GROUP else self.region_of_legal_name.get(row.group)
            if region is None and row.group != NO_GROUP:
                raise ListFileError(
                    f"{MUNICIPALITIES.name}: {row.legal_name} is in {row.group!r}, which is no "
                    "regional district"
                )
            if self.region_of_division.get(unit.division or "") != region:
                self.notes.moved.append(
                    f"{unit.code} {unit.names[0]}: division {unit.division}, layer {row.group}"
                )
            name = OVERRIDES.get(unit.code, {}).get("name", census_name(unit))
            draft = Draft(
                unit=unit,
                name=name,
                parent=region or PROVINCE,
                parent_level=REGION if region is not None else PROVINCE_LEVEL,
                parent_parent=PROVINCE if region is not None else None,
                government=row.legal_name,
                government_citation=Citation(source=MUNICIPALITIES.name, line=row.line),
            )
            if name != census_name(unit):
                self.notes.renamed.append(f"{unit.code} {census_name(unit)} -> {name}")
                draft.alias(census_name(unit))
            found.append(draft.entry())
        for row in self.municipalities:
            if row.line not in taken:
                self.notes.untaken.append(row.legal_name)
        return sorted(found, key=lambda entry: entry.name)


def build(files: Mapping[str, OpenedFile], naming: Naming) -> tuple[list[PlaceEntry], Notes]:
    builder = Builder(files, naming)
    regions = builder.regions()
    municipalities = builder.municipality_entries()
    return [*regions, *municipalities], builder.notes


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[PlaceEntry]:
    """British Columbia's regional districts, then its municipalities."""
    found, notes = build(files, rules.naming)
    notes.log()
    return found
