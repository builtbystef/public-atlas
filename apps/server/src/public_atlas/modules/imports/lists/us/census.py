"""The Census Bureau's files, shared by the United States' places lists: the Vintage 2025
subcounty population estimates (SUB-EST2025), which give every state, county equivalent,
incorporated place, county subdivision and consolidated city with its functional status and
its 2025 population; the 2020 ANSI code files, the only ones that carry each unit's class
(`CLASSFP`); the 2026 Gazetteer's county file and the Puerto Rico estimates, since SUB-EST2025
leaves Puerto Rico out; and the readers that turn them into units.

What is a government is the functional status (lists-research section 1.1): `A` (active), `B`
(active, partially consolidated) and `C` (active, consolidated with another government) are
governments; `F` (fictitious filler), `G` (subordinate), `I` (inactive), `N` (nonfunctioning
legal entity) and `S` (statistical) are not. A `C` unit's government is the other unit's: a
county consolidated with its city, a Connecticut town consolidated with the city of its name.

The census writes a unit's kind after its name in lower case ("Springfield city", "Canton
charter township", "Cyr plantation"); the legal name puts the designator first ("City of
Springfield"). `split_name` takes a census name apart and `legal_name` composes the government's
name from the kind, as the naming rules read it.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from public_atlas.modules.graph.models import MetricName
from public_atlas.modules.imports.entries import Citation, Figure
from public_atlas.modules.imports.files import CELL_SEPARATOR, Format, ListFile, OpenedFile

ESTIMATES_YEAR = 2025
POPULATION_COLUMN = "POPESTIMATE2025"
COUNTRY_NAME = "United States"
# The seed's administrative levels.
COUNTRY_LEVEL = "country"
STATE_LEVEL = "state"
COUNTY_LEVEL = "county"
MUNICIPALITY_LEVEL = "municipality"
# Summary levels (SUB-EST2025 layout).
SUMLEV_STATE = "040"
SUMLEV_COUNTY = "050"
SUMLEV_SUBDIVISION = "061"
SUMLEV_PLACE_IN_SUBDIVISION = "071"
SUMLEV_PLACE_IN_COUNTY = "157"
SUMLEV_PLACE = "162"
SUMLEV_CONSOLIDATED_CITY = "170"
SUMLEV_PLACE_IN_CONSOLIDATED_CITY = "172"
# The rows SUB-EST2025 uses for a county's or subdivision's remainder: not units.
BALANCE_PLACE_CODE = "99990"
# The functional statuses that are governments.
ACTIVE = frozenset({"A", "B", "C"})
FUNCTIONAL_STATUS = {
    "A": "active government",
    "B": "active government, partially consolidated with another",
    "C": "active government, consolidated with another government",
    "F": "fictitious entity, a filler",
    "G": "subordinate unit",
    "I": "inactive government",
    "N": "nonfunctioning legal entity",
    "S": "statistical entity",
}
PUERTO_RICO = "Puerto Rico"
PUERTO_RICO_CODE = "72"
# The states whose governments are commonwealths by name; the District's is "Government of the
# District of Columbia".
COMMONWEALTHS = frozenset({"Kentucky", "Massachusetts", "Pennsylvania", "Virginia", PUERTO_RICO})
DISTRICT_OF_COLUMBIA = "District of Columbia"

SUB_EST = ListFile(
    name="census_sub_est2025",
    title=(
        "U.S. Census Bureau, Vintage 2025 Subcounty Resident Population Estimates "
        "(SUB-EST2025), released May 2026"
    ),
    url=(
        "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/cities/totals/"
        "sub-est2025.csv"
    ),
    sha256="e3508f5201465913476d4ddf91740f191f7977c9f2614a2a7e30b5fd22027934",
    format=Format.CSV,
    encoding="cp1252",
    columns=(
        "SUMLEV",
        "STATE",
        "COUNTY",
        "PLACE",
        "COUSUB",
        "CONCIT",
        "FUNCSTAT",
        "NAME",
        "STNAME",
        POPULATION_COLUMN,
    ),
)
COUNTY_CODES = ListFile(
    name="census_county_codes_2020",
    title="U.S. Census Bureau, 2020 ANSI codes for counties and county equivalents",
    url="https://www2.census.gov/geo/docs/reference/codes2020/national_county2020.txt",
    sha256="9f6e5f6eb6ac2f5e9a36d5fd01dec77991bddc75118f748a069441a4782970d6",
    format=Format.CSV,
    delimiter="|",
    encoding="utf-8",
)
COUSUB_CODES = ListFile(
    name="census_cousub_codes_2020",
    title="U.S. Census Bureau, 2020 ANSI codes for county subdivisions",
    url="https://www2.census.gov/geo/docs/reference/codes2020/national_cousub2020.txt",
    sha256="2f292e90e56b1c1b085402bef6e4dc9d9404b0006e44988860226759217c7cf3",
    format=Format.CSV,
    delimiter="|",
    encoding="utf-8",
    columns=("STATEFP", "COUNTYFP", "COUSUBFP", "COUSUBNAME", "CLASSFP", "FUNCSTAT"),
)
PLACE_CODES = ListFile(
    name="census_place_codes_2020",
    title="U.S. Census Bureau, 2020 ANSI codes for places",
    url="https://www2.census.gov/geo/docs/reference/codes2020/national_place2020.txt",
    sha256="302ff3cf031217aca032d89f42c0dd93611a76d72ab2036944fa40d5c23c6613",
    format=Format.CSV,
    delimiter="|",
    encoding="utf-8",
    columns=("STATEFP", "PLACEFP", "PLACENAME", "CLASSFP", "FUNCSTAT"),
)
GAZETTEER_COUNTIES = ListFile(
    name="census_gazetteer_counties_2026",
    title="U.S. Census Bureau, 2026 Gazetteer file of counties and county equivalents",
    url=(
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2026_Gazetteer/"
        "2026_Gaz_counties_national.zip"
    ),
    sha256="6a99ca00efbc0be5112e225d4102704c51d5ce3b16e3afd6e4159460595fd12a",
    format=Format.CSV,
    member="2026_Gaz_counties_national.txt",
    delimiter="|",
    encoding="utf-8",
    columns=("USPS", "GEOID", "ANSICODE", "NAME"),
)
# The sheet's header spans rows 3 and 4: row 3 names the first three columns and row 4 gives
# the year of each estimate, so the 2025 estimate is a row's last cell (`last_cell`).
PUERTO_RICO_POPULATION = ListFile(
    name="census_prm_est2025",
    title=(
        "U.S. Census Bureau, Annual Estimates of the Resident Population for Puerto Rico "
        "Municipios: April 1, 2020 to July 1, 2025 (PRM-EST2025-POP), released March 2026"
    ),
    url=(
        "https://www2.census.gov/programs-surveys/popest/tables/2020-2025/municipios/totals/"
        "prm-est2025-pop.xlsx"
    ),
    sha256="25535fb5935273bd201afd28cf4fbf72504196613552ce0aefa7a880abc0c965",
    format=Format.SPREADSHEET,
    header_row=3,
)
PUERTO_RICO_YEAR_ROW = 4
PUERTO_RICO_AREA_COLUMN = "Geographic Area"


# --- Units ---


@dataclass(frozen=True, slots=True)
class Unit:
    """One row of SUB-EST2025."""

    sumlev: str
    state: str
    county: str
    place: str
    cousub: str
    concit: str
    funcstat: str
    name: str
    state_name: str
    population: int
    line: int

    @property
    def fips(self) -> str:
        """The unit's FIPS code, as the Gazetteer's GEOID writes it: the state's two digits,
        then the county's three, the place's or consolidated city's five, or the county's
        three and the subdivision's five."""
        match self.sumlev:
            case "040":
                return self.state
            case "050":
                return self.state + self.county
            case "061" | "071":
                return self.state + self.county + self.cousub
            case "162" | "157" | "172":
                return self.state + self.place
            case "170":
                return self.state + self.concit
        raise ValueError(f"no FIPS code for summary level {self.sumlev}")

    @property
    def active(self) -> bool:
        return self.funcstat in ACTIVE

    @property
    def citation(self) -> Citation:
        return Citation(source=SUB_EST.name, line=self.line)

    @property
    def figure(self) -> Figure:
        return Figure(
            name=MetricName.POPULATION,
            year=ESTIMATES_YEAR,
            value=Decimal(self.population),
            citation=self.citation,
        )


class Estimates:
    """SUB-EST2025 as read: the units by summary level, the county parts of each place and the
    place parts of each county subdivision, and the states by code."""

    def __init__(self, opened: OpenedFile) -> None:
        self.by_level: dict[str, list[Unit]] = defaultdict(list)
        # The county parts of a place (summary level 157), by state and place.
        self.county_parts: dict[tuple[str, str], list[Unit]] = defaultdict(list)
        # The places inside a county subdivision (071), by state, county and subdivision.
        self.places_within: dict[tuple[str, str, str], list[Unit]] = defaultdict(list)
        # The places inside a consolidated city (172), by state and consolidated city.
        self.consolidated_parts: dict[tuple[str, str], list[Unit]] = defaultdict(list)
        self.state_names: dict[str, str] = {}
        for row in opened.rows:
            unit = Unit(
                sumlev=row["SUMLEV"],
                state=row["STATE"],
                county=row["COUNTY"],
                place=row["PLACE"],
                cousub=row["COUSUB"],
                concit=row["CONCIT"],
                funcstat=row["FUNCSTAT"],
                name=" ".join(row["NAME"].split()),
                state_name=row["STNAME"],
                population=int(row[POPULATION_COLUMN]),
                line=row.line,
            )
            self.by_level[unit.sumlev].append(unit)
            if unit.sumlev == SUMLEV_PLACE_IN_COUNTY:
                self.county_parts[unit.state, unit.place].append(unit)
            elif unit.sumlev == SUMLEV_PLACE_IN_SUBDIVISION:
                self.places_within[unit.state, unit.county, unit.cousub].append(unit)
            elif unit.sumlev == SUMLEV_PLACE_IN_CONSOLIDATED_CITY:
                self.consolidated_parts[unit.state, unit.concit].append(unit)
            elif unit.sumlev == SUMLEV_STATE:
                self.state_names[unit.state] = unit.name

    def units(self, sumlev: str) -> list[Unit]:
        return self.by_level.get(sumlev, [])

    def active_counties(self) -> dict[str, Unit]:
        """The county equivalents that are governments, by FIPS code."""
        return {unit.fips: unit for unit in self.units(SUMLEV_COUNTY) if unit.active}

    def main_county(self, unit: Unit) -> str | None:
        """The county holding most of a place's population, as its three-digit code; None for
        a place with no county parts. The layout's `PRIMGEO_FLAG` does not mark one: it says
        whether a row is a primitive geography of the estimates, and a place in two counties
        is flagged in both or in neither."""
        parts = self.county_parts.get((unit.state, unit.place), [])
        if not parts:
            return None
        return max(parts, key=lambda part: (part.population, part.county)).county


# --- Classes ---


def read_classes(opened: OpenedFile, *key_columns: str) -> dict[tuple[str, ...], str]:
    """Each row's `CLASSFP`, keyed by the given columns: a county's by state and county, a
    subdivision's by state, county and subdivision, a place's by state and place."""
    return {tuple(row[column] for column in key_columns): row["CLASSFP"] for row in opened.rows}


# --- Names ---


# The kinds the census writes after a name, longest first so "charter township" is not read as
# "township", with the legal designator each composes.
KINDS: dict[str, str] = {
    "charter township": "Charter Township",
    "city and borough": "City and Borough",
    "urban county": "Urban County Government",
    "metropolitan government": "Metropolitan Government",
    "consolidated government": "Consolidated Government",
    "unified government": "Unified Government",
    "metro government": "Metro Government",
    "municipality": "Municipality",
    "plantation": "Plantation",
    "township": "Township",
    "borough": "Borough",
    "village": "Village",
    "city": "City",
    "town": "Town",
}
# Kinds whose designator follows the name ("Cyr Plantation", "Lexington-Fayette Urban County
# Government"), the rest put it first ("City of Springfield").
TRAILING_KINDS = frozenset(
    {
        "plantation",
        "urban county",
        "metropolitan government",
        "consolidated government",
        "unified government",
        "metro government",
    }
)
_KIND = re.compile(
    r"^(?P<base>.+?) (?P<kind>" + "|".join(re.escape(kind) for kind in KINDS) + r")$"
)
# A county part or a consolidated city's remainder, never a unit of its own.
_PART = re.compile(r" \((?:pt\.|balance)\)$")


def split_name(name: str) -> tuple[str, str | None]:
    """A census name as its place name and its kind: "Springfield city" is ("Springfield",
    "city"); "Carson City" and "Township 1" have no kind. The kind is lower case: "Carson City
    city" is the city of Carson City."""
    match = _KIND.match(name)
    if match is None:
        return name, None
    return match.group("base"), match.group("kind")


def is_part(name: str) -> bool:
    return _PART.search(name) is not None


def legal_name(base: str, kind: str | None) -> str:
    """The government's name composed from the census kind: "City of Springfield", "Charter
    Township of Canton", "Cyr Plantation". A unit with no kind is its own name."""
    if kind is None:
        return base
    designator = KINDS[kind]
    if kind in TRAILING_KINDS:
        return f"{base} {designator}"
    return f"{designator} of {base}"


def state_government(name: str) -> str:
    """ "State of Ohio", "Commonwealth of Kentucky", "Government of the District of Columbia"."""
    if name == DISTRICT_OF_COLUMBIA:
        return f"Government of the {name}"
    if name in COMMONWEALTHS:
        return f"Commonwealth of {name}"
    return f"State of {name}"


# --- Puerto Rico ---


def last_cell(opened: OpenedFile, line: int) -> str:
    """The last cell of a table's line: the 2025 estimate of the Puerto Rico sheet, whose year
    columns are nameless in the header row."""
    return opened.line(line).split(CELL_SEPARATOR)[-1].strip()


def puerto_rico_populations(opened: OpenedFile) -> dict[str, tuple[int, int]]:
    """Each municipio's 2025 population with the line that gives it, by the census name
    ("Adjuntas Municipio"), and Puerto Rico's own under `PUERTO_RICO`."""
    if last_cell(opened, PUERTO_RICO_YEAR_ROW) != str(ESTIMATES_YEAR):
        raise ValueError(
            f"{PUERTO_RICO_POPULATION.name}: the last column is not the {ESTIMATES_YEAR} estimate"
        )
    found: dict[str, tuple[int, int]] = {}
    for row in opened.rows:
        area = row[PUERTO_RICO_AREA_COLUMN].lstrip(".")
        if area == PUERTO_RICO:
            found[PUERTO_RICO] = int(last_cell(opened, row.line)), row.line
        elif area.endswith(f", {PUERTO_RICO}"):
            name = area.removesuffix(f", {PUERTO_RICO}")
            found[name] = int(last_cell(opened, row.line)), row.line
    return found
