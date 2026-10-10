"""Statistics Canada's 2021 Census, shared by every provincial places list: the two national
files (the population table and the geographic attribute file), the readers that pick one
province out of them, and what each census unit type is in each province.

The census counts every province as divisions (CD) and subdivisions (CSD), each with a type
code. What a type means for the graph differs by province: Ontario's counties are governments,
Nova Scotia's are only census units; a `RM` is a regional municipality in Ontario's divisions
and a rural municipality in Saskatchewan's subdivisions. So the tables here are per province:
the division types that are regions with a government (`UPPER_TIER_TYPES`), regions nothing
governs (`DISTRICT_TYPES`) or no place at all (`CENSUS_ONLY_TYPES`), and the subdivision
types that are municipalities (`MUNICIPAL_TYPES`, with the designator a composed government
name takes) or not governments (`DROPPED_TYPES`). A `Province` reads the files for one
province and answers from these tables. The counts in the comments are the 2021 files'.
"""

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.imports.entries import (
    AliasEntry,
    Citation,
    Code,
    Fact,
    Figure,
    PlaceEntry,
)
from public_atlas.modules.imports.files import Format, ListFile, ListFileError, OpenedFile

COUNTRY = "CA"
PROVINCE_LEVEL = "province_territory"
REGION = "region"
MUNICIPALITY = "municipality"
CENSUS_YEAR = 2021
# A division code is the province's two digits plus two; a subdivision's is longer and starts
# with its division's.
DIVISION_CODE_LENGTH = 4
POPULATION_COLUMN = "Population and dwelling counts (13): Population, 2021 [1]"
# Between the names of a row that has two ("Greater Sudbury / Grand Sudbury").
NAME_SEPARATOR = " / "

POPULATION = ListFile(
    name="statcan_population_2021",
    title=(
        "Statistics Canada, table 98-10-0002-01: Population and dwelling counts, Canada and "
        "census subdivisions (municipalities), 2021 Census"
    ),
    url="https://www150.statcan.gc.ca/n1/tbl/csv/98100002-eng.zip",
    sha256="36ab6c8f3f6b82d70d9dea927cb5cf04f6fbf9b543a7ad543695e6ea70d22876",
    format=Format.CSV,
    member="98100002.csv",
    columns=("GEO", "DGUID", POPULATION_COLUMN),
)
# One row per dissemination block in the country (half a million); read for the division and
# subdivision columns, once per distinct unit.
ATTRIBUTES = ListFile(
    name="statcan_geographic_attributes_2021",
    title="Statistics Canada, 2021 Census Geographic Attribute File (92-151-X)",
    url=(
        "https://www12.statcan.gc.ca/census-recensement/2021/geo/aip-pia/attribute-attribs/"
        "files-fichiers/2021_92-151_X.zip"
    ),
    sha256="918aa8502d9d95b1ae5ce437ed9674e0977ec55977c08b8d01822a9dab6fe5da",
    format=Format.CSV,
    member="2021_92-151_X.csv",
    encoding="cp1252",
    columns=(
        "PRUID_PRIDU",
        "CDUID_DRIDU",
        "CDNAME_DRNOM",
        "CDTYPE_DRGENRE",
        "CSDUID_SDRIDU",
        "CSDNAME_SDRNOM",
        "CSDTYPE_SDRGENRE",
    ),
    distinct=True,
)
# The changes to subdivisions since the census (annexations, amalgamations, dissolutions,
# renames, recodings) up to 2024-01-01, one row per gaining and losing pair, with the new codes
# and names: how a post-census municipality (New Brunswick's reformed local governments, a new
# resort village) gets its code. Three title rows precede the header; a province's rows follow
# a row holding its name alone.
INTERIM_CHANGES = ListFile(
    name="statcan_interim_changes_2024",
    title=(
        "Statistics Canada, Interim List of Changes to Municipal Boundaries, Status and Names, "
        "January 2, 2021 to January 1, 2024 (92F0009X), table 1"
    ),
    url="https://www150.statcan.gc.ca/n1/pub/92f0009x/2024001/tbl/tbl01-eng.csv",
    sha256="fa40a4f1e53fcb84924d70e604cc187cbd3da601b5779188d14e11f867ab5c65",
    format=Format.CSV,
    encoding="cp1252",
    header_row=3,
    columns=(
        "Gaining CSDuid",
        "Gaining CSDname",
        "Gaining CSDtype",
        "Gaining CSD Change Code Description",
        "Losing CSDuid",
        "Losing CSDname",
        "Losing CSDtype",
        "Losing CSD Change Code Description",
        "Effective Date",
    ),
)

# The provinces and territories by their SGC code.
PROVINCES: dict[str, str] = {
    "10": "Newfoundland and Labrador",
    "11": "Prince Edward Island",
    "12": "Nova Scotia",
    "13": "New Brunswick",
    "24": "Quebec",
    "35": "Ontario",
    "46": "Manitoba",
    "47": "Saskatchewan",
    "48": "Alberta",
    "59": "British Columbia",
    "60": "Yukon",
    "61": "Northwest Territories",
    "62": "Nunavut",
}


@dataclass(frozen=True, slots=True)
class UnitType:
    """A census division or subdivision type (SGC 2021): its code, its English name as the
    population table's metadata gives it, and the provinces whose 2021 files use it."""

    code: str
    name: str
    provinces: frozenset[str]


def _types(rows: list[tuple[str, str, str]]) -> dict[str, UnitType]:
    return {
        code: UnitType(code=code, name=name, provinces=frozenset(provinces.split()))
        for code, name, provinces in rows
    }


# Census division types, with the provinces that have them.
CD_TYPES: dict[str, UnitType] = _types(
    [
        ("CDR", "Census division", "10 24 35 46 47 48"),
        ("CT", "County", "13"),
        ("CTY", "County", "11 12 35"),
        ("DIS", "District", "35"),
        ("DM", "District municipality", "35"),
        ("MRC", "Municipalité régionale de comté", "24"),
        ("RD", "Regional district", "59"),
        ("REG", "Region", "59 61 62"),
        ("RM", "Regional municipality", "35"),
        ("TER", "Territory", "60"),
        ("TÉ", "Territoire équivalent", "24"),
        ("UC", "United counties", "35"),
    ]
)
# Census subdivision types, with the provinces that have them.
CSD_TYPES: dict[str, UnitType] = _types(
    [
        ("C", "City", "13 35"),
        ("CC", "Chartered community", "61"),
        ("CG", "Community government", "61"),
        ("CN", "Crown colony", "47"),
        ("CT", "Canton (municipalité de)", "24"),
        ("CU", "Cantons unis (municipalité de)", "24"),
        ("CV", "City", "35"),
        ("CY", "City", "10 11 35 46 47 48 59 60 61 62"),
        ("DM", "District municipality", "59"),
        ("FD", "Fire district", "11"),
        ("GR", "Gouvernement régional", "24"),
        ("HAM", "Hamlet", "60 61 62"),
        ("ID", "Improvement district", "48"),
        ("IGD", "Indian government district", "59"),
        ("IM", "Island municipality", "59"),
        ("IRI", "Indian reserve", "10 11 12 13 24 35 46 47 48 59 61"),
        ("LGD", "Local government district", "46"),
        ("M", "Municipality", "35"),
        ("MD", "Municipal district", "12 48"),
        ("MRM", "Regional municipality", "13"),
        ("MU", "Municipality", "35 46"),
        ("MÉ", "Municipalité", "24"),
        ("NH", "Northern hamlet", "47"),
        ("NL", "Nisga'a land", "59"),
        ("NO", "Unorganized", "24 35 46 47 60 61 62"),
        ("NV", "Northern village", "47"),
        ("P", "Parish", "13"),
        ("PE", "Paroisse (municipalité de)", "24"),
        ("RCR", "Rural community", "13"),
        ("RDA", "Regional district electoral area", "59"),
        ("RGM", "Regional municipality", "12 59"),
        ("RM", "Regional municipality / Rural municipality", "11 12 46 47"),
        ("RMU", "Resort municipality", "11"),
        ("RV", "Resort village", "47"),
        ("S-É", "Indian settlement", "24 35 46 47 48 59 60"),
        ("SA", "Special area", "48"),
        ("SC", "Subdivision of county municipality", "12"),
        ("SET", "Settlement", "61 62"),
        ("SG", "Self-government", "60"),
        ("SM", "Specialized municipality", "48"),
        ("SNO", "Subdivision of unorganized", "10"),
        ("SV", "Summer village", "48"),
        ("SÉ", "Settlement", "60"),
        ("T", "Town", "10 11 12 35 46 47 48 59 60 61"),
        ("TAL", "Tla'amin Lands", "59"),
        ("TC", "Terres réservées aux Cris", "24"),
        ("TI", "Terre inuite", "24"),
        ("TK", "Terres réservées aux Naskapis", "24"),
        ("TL", "Teslin land", "60"),
        ("TP", "Township", "35"),
        ("TV", "Town", "13 35"),
        ("TWL", "Tsawwassen Lands", "59"),
        ("V", "Ville", "24"),
        ("VC", "Village cri", "24"),
        ("VK", "Village naskapi", "24"),
        ("VL", "Village", "13 24 35 46 47 48 59 60 61"),
        ("VN", "Village nordique", "24"),
    ]
)
# --- What each type is, per province ---

# Division types that are regions with a government, with the designator a composed
# government name takes. Region-level governments exist only in Ontario, Quebec (the MRCs) and
# British Columbia (the regional districts).
UPPER_TIER_TYPES: dict[str, dict[str, str]] = {
    "24": {"MRC": "Municipalité régionale de comté"},
    "35": {
        "CTY": "County",
        "RM": "Regional Municipality",
        "UC": "United Counties",
        "DM": "District Municipality",
    },
    "59": {"RD": "Regional District"},
}
# Division types that are regions with no government: Ontario's ten territorial districts have
# no council, and the bodies at that level need the place as a parent.
DISTRICT_TYPES: dict[str, frozenset[str]] = {"35": frozenset({"DIS"})}
# Division types that are only census units: no place, and their municipalities sit under the
# province. Quebec's twelve `TÉ` divisions are cities with no MRC above them; its five `CDR`
# divisions hold municipalities whose real MRC the directory names (research section 2.1).
CENSUS_ONLY_TYPES: dict[str, frozenset[str]] = {
    "10": frozenset({"CDR"}),
    "11": frozenset({"CTY"}),
    "12": frozenset({"CTY"}),
    "13": frozenset({"CT"}),
    "24": frozenset({"CDR", "TÉ"}),
    "35": frozenset({"CDR"}),
    "46": frozenset({"CDR"}),
    "47": frozenset({"CDR"}),
    "48": frozenset({"CDR"}),
    "59": frozenset({"REG"}),
    "60": frozenset({"TER"}),
    "61": frozenset({"REG"}),
    "62": frozenset({"REG"}),
}
# Subdivision types that are municipalities, with the designator a composed government name
# takes when the province's directory has no row ("Township of Elmwood"). Quebec's designators
# are French and go before the name with elision ("Municipalité d'Adstock"), which its module
# composes. Nova Scotia's nine county municipalities have no subdivision of their own (they
# are the `SC` parts of a county division); its module builds them.
MUNICIPAL_TYPES: dict[str, dict[str, str]] = {
    "10": {"CY": "City", "T": "Town"},
    "11": {"CY": "City", "T": "Town", "RM": "Rural Municipality", "RMU": "Resort Municipality"},
    "12": {
        "T": "Town",
        "MD": "Municipality of the District",
        "RGM": "Regional Municipality",
        "RM": "Regional Municipality",
    },
    "13": {
        "C": "City",
        "TV": "Town",
        "VL": "Village",
        "RCR": "Rural Community",
        "MRM": "Regional Municipality",
    },
    "24": {
        "V": "Ville",
        "MÉ": "Municipalité",
        "PE": "Paroisse",
        "CT": "Canton",
        "CU": "Cantons unis",
        "VL": "Village",
        "VN": "Village nordique",
        "VC": "Village cri",
        "VK": "Village naskapi",
        "GR": "Gouvernement régional",
    },
    "35": {
        "C": "City",
        "CV": "City",
        "CY": "City",
        "T": "Town",
        "TV": "Town",
        "TP": "Township",
        "VL": "Village",
        "M": "Municipality",
        "MU": "Municipality",
    },
    "46": {
        "CY": "City",
        "T": "Town",
        "VL": "Village",
        "MU": "Municipality",
        "RM": "Rural Municipality",
        "LGD": "Local Government District",
    },
    "47": {
        "CY": "City",
        "T": "Town",
        "VL": "Village",
        "RV": "Resort Village",
        "RM": "Rural Municipality",
        "NV": "Northern Village",
        "NH": "Northern Hamlet",
    },
    "48": {
        "CY": "City",
        "T": "Town",
        "VL": "Village",
        "SV": "Summer Village",
        "MD": "Municipal District",
        "SM": "Specialized Municipality",
    },
    "59": {
        "CY": "City",
        "DM": "District",
        "T": "Town",
        "VL": "Village",
        "IM": "Island Municipality",
        "RGM": "Regional Municipality",
    },
    "60": {"CY": "City", "T": "Town", "VL": "Village"},
    "61": {
        "CY": "City",
        "T": "Town",
        "VL": "Village",
        "HAM": "Hamlet",
        "CG": "Community Government",
        "CC": "Chartered Community",
    },
    "62": {"CY": "City", "HAM": "Hamlet"},
}
# Subdivision types that are not governments, with what they are. Indian reserves and
# settlements are land, not governments: First Nations come from Indigenous Services Canada's
# profiles, a later module. Alberta's improvement districts and special areas are administered
# by the province; its module decides whether to load them (lists-todo session 8).
DROPPED_TYPES: dict[str, dict[str, str]] = {
    "10": {"SNO": "subdivision of unorganized", "IRI": "Indian reserve"},
    "11": {"FD": "fire district", "IRI": "Indian reserve"},
    "12": {"SC": "subdivision of county municipality", "IRI": "Indian reserve"},
    "13": {"P": "parish", "IRI": "Indian reserve"},
    "24": {
        "NO": "unorganized area",
        "IRI": "Indian reserve",
        "TC": "Cree reserved land",
        "TI": "Inuit land",
        "TK": "Naskapi reserved land",
        "S-É": "Indian settlement",
    },
    "35": {"IRI": "Indian reserve", "NO": "unorganized area", "S-É": "Indian settlement"},
    "46": {"NO": "unorganized area", "IRI": "Indian reserve", "S-É": "Indian settlement"},
    "47": {
        "NO": "unorganized area",
        "IRI": "Indian reserve",
        "S-É": "Indian settlement",
        "CN": "Crown colony",
    },
    "48": {
        "ID": "improvement district",
        "SA": "special area",
        "IRI": "Indian reserve",
        "S-É": "Indian settlement",
    },
    "59": {
        "RDA": "regional district electoral area",
        "IGD": "Indian government district",
        "NL": "Nisga'a land",
        "TAL": "Tla'amin Lands",
        "TWL": "Tsawwassen Lands",
        "IRI": "Indian reserve",
        "S-É": "Indian settlement",
    },
    "60": {
        "HAM": "hamlet (a local advisory area)",
        "SÉ": "settlement",
        "SG": "self-government",
        "TL": "Teslin land",
        "NO": "unorganized area",
        "S-É": "Indian settlement",
    },
    "61": {"SET": "settlement", "NO": "unorganized area", "IRI": "Indian reserve"},
    "62": {"SET": "settlement", "NO": "unorganized area"},
}


# --- Reading one province ---


@dataclass
class Counted:
    """A census unit: a division or a subdivision."""

    code: str
    names: tuple[str, ...]
    population: int | None
    # The population table's line.
    line: int
    type_: str = ""
    # The division's code for a subdivision; None for a division.
    division: str | None = None


@dataclass(frozen=True)
class Province:
    """One province's view of the census files and the type tables."""

    code: str

    def __post_init__(self) -> None:
        if self.code not in PROVINCES:
            raise ValueError(f"no province or territory has the SGC code {self.code!r}")

    @property
    def name(self) -> str:
        return PROVINCES[self.code]

    @property
    def dguid(self) -> re.Pattern[str]:
        """A DGUID is the vintage, the geographic level and the code: 2021A0005 3510010 is
        Kingston. The province's rows are the ones whose code starts with its own."""
        return re.compile(rf"^{CENSUS_YEAR}A000[235](?P<code>{self.code}\d*)$")

    @property
    def upper_tier_types(self) -> dict[str, str]:
        return UPPER_TIER_TYPES.get(self.code, {})

    @property
    def district_types(self) -> frozenset[str]:
        return DISTRICT_TYPES.get(self.code, frozenset())

    @property
    def census_only_types(self) -> frozenset[str]:
        return CENSUS_ONLY_TYPES.get(self.code, frozenset())

    @property
    def municipal_types(self) -> dict[str, str]:
        return MUNICIPAL_TYPES[self.code]

    @property
    def dropped_types(self) -> dict[str, str]:
        return DROPPED_TYPES[self.code]

    def read_population(self, opened: OpenedFile) -> dict[str, Counted]:
        """The province, its divisions and subdivisions, with their names and 2021 population."""
        dguid = self.dguid
        counted: dict[str, Counted] = {}
        for row in opened.rows:
            match = dguid.match(row["DGUID"])
            if match is None:
                continue
            code = match.group("code")
            names = tuple(part.strip() for part in row["GEO"].split(NAME_SEPARATOR) if part.strip())
            figure = row[POPULATION_COLUMN].replace(",", "")
            counted[code] = Counted(
                code=code,
                names=names,
                population=int(figure) if figure.isdigit() else None,
                line=row.line,
            )
        return counted

    def read_types(self, counted: dict[str, Counted], opened: OpenedFile) -> None:
        """The type of each division and subdivision, and which division a subdivision is
        in."""
        for row in opened.rows:
            if row["PRUID_PRIDU"] != self.code:
                continue
            for code, type_ in (
                (row["CDUID_DRIDU"], row["CDTYPE_DRGENRE"]),
                (row["CSDUID_SDRIDU"], row["CSDTYPE_SDRGENRE"]),
            ):
                unit = counted.get(code)
                if unit is not None and not unit.type_:
                    unit.type_ = type_
                    unit.division = (
                        code[:DIVISION_CODE_LENGTH] if len(code) > DIVISION_CODE_LENGTH else None
                    )
        missing = [
            unit.code for unit in counted.values() if not unit.type_ and unit.code != self.code
        ]
        if missing:
            raise ListFileError(
                f"no type in the attribute file for {len(missing)} census codes: {missing[:5]}"
            )

    def read(self, files: Mapping[str, OpenedFile]) -> Census:
        """The province's units from the opened census files."""
        counted = self.read_population(files[POPULATION.name])
        self.read_types(counted, files[ATTRIBUTES.name])
        return Census(province=self, counted=counted)


@dataclass(frozen=True)
class Census:
    """One province's census units, sorted out: its divisions, its subdivisions, and which of
    the latter are municipalities."""

    province: Province
    counted: dict[str, Counted]

    @property
    def divisions(self) -> dict[str, Counted]:
        return {
            code: unit
            for code, unit in sorted(self.counted.items())
            if unit.division is None and code != self.province.code
        }

    @property
    def subdivisions(self) -> list[Counted]:
        return sorted(
            (unit for unit in self.counted.values() if unit.division is not None),
            key=lambda unit: unit.code,
        )

    @property
    def municipalities(self) -> list[Counted]:
        """The subdivisions whose type is a municipality in this province."""
        types = self.province.municipal_types
        return [unit for unit in self.subdivisions if unit.type_ in types]

    def dropped(self) -> Counter[str]:
        """How many subdivisions of each non-municipal type the province has."""
        types = self.province.municipal_types
        return Counter(unit.type_ for unit in self.subdivisions if unit.type_ not in types)

    def unit(self, code: str) -> Counted:
        return self.counted[code]


def census_name(unit: Counted) -> str:
    """The unit's English name as a place is named: the census marks the part of a city two
    provinces share ("Lloydminster (Part)"), the place does not."""
    return unit.names[0].removesuffix(" (Part)").strip()


def composed_government(province: Province, unit: Counted, name: str | None = None) -> str:
    """The government's name the census type gives when no directory names it: "Town of
    Elmwood"."""
    designator = province.municipal_types.get(unit.type_) or province.upper_tier_types.get(
        unit.type_
    )
    name = census_name(unit) if name is None else name
    return name if designator is None else f"{designator} of {name}"


def population_figure(unit: Counted, value: int | None = None) -> Figure:
    """The 2021 count, cited at the unit's line; `value` when the figure is summed over
    several units."""
    figure = unit.population if value is None else value
    if figure is None:
        raise ListFileError(f"{unit.code} {unit.names[0]} has no population")
    return Figure(
        name=MetricName.POPULATION,
        year=CENSUS_YEAR,
        value=Decimal(figure),
        citation=Citation(source=POPULATION.name, line=unit.line),
    )


@dataclass
class Draft:
    """One place as a provincial module puts it together from a census unit and, where a
    directory has a row, the directory: the census line cites the place and its population, the
    directory's line the government and its homepage."""

    unit: Counted
    name: str
    parent: str
    level: str = MUNICIPALITY
    parent_level: str | None = PROVINCE_LEVEL
    parent_parent: str | None = None
    language: str = "en"
    government: str | None = None
    government_citation: Citation | None = None
    homepage: str | None = None
    homepage_citation: Citation | None = None
    aliases: list[AliasEntry] = field(default_factory=list)
    # The 2021 count when it is not the unit's own (summed over parts); None for no figure.
    population: int | None = None
    codes: tuple[Code, ...] = ()
    cite_population: bool = True

    def alias(self, text: str, language: str = "en") -> None:
        text = " ".join(text.split())
        if text and text != self.name and all(alias.text != text for alias in self.aliases):
            self.aliases.append(AliasEntry(text=text, language=language))

    def entry(self) -> PlaceEntry:
        place = Citation(source=POPULATION.name, line=self.unit.line)
        citations: dict[Fact, Citation] = {"place": place}
        if self.government_citation is not None:
            citations["government"] = self.government_citation
        if self.homepage is not None:
            citations["homepage"] = self.homepage_citation or self.government_citation or place
        figures: tuple[Figure, ...] = ()
        if self.cite_population and (self.population or self.unit.population) is not None:
            figures = (population_figure(self.unit, self.population),)
        return PlaceEntry(
            name=self.name,
            aliases=tuple(self.aliases),
            language=self.language,
            level=self.level,
            parent=self.parent,
            parent_level=self.parent_level,
            parent_parent=self.parent_parent,
            government=self.government,
            code=Code(scheme=IdentifierScheme.STATCAN_SGC, value=self.unit.code),
            codes=self.codes,
            figures=figures,
            homepage=self.homepage,
            citations=citations,
        )


# --- The interim list of changes ---


@dataclass(frozen=True)
class Change:
    """One row of the interim list: what a subdivision gained or became, from which other."""

    code: str
    name: str
    type_: str
    change: str
    losing_code: str
    losing_name: str
    losing_type: str
    losing_change: str
    effective: str
    line: int

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(part.strip() for part in self.name.split(NAME_SEPARATOR) if part.strip())


def read_changes(opened: OpenedFile, province: Province) -> list[Change]:
    """The province's rows of the interim list, in the file's order."""
    found = []
    for row in opened.rows:
        code = row["Gaining CSDuid"]
        if not code.isdigit() or not code.startswith(province.code):
            continue
        found.append(
            Change(
                code=code,
                name=" ".join(row["Gaining CSDname"].split()),
                type_=row["Gaining CSDtype"],
                change=row["Gaining CSD Change Code Description"],
                losing_code=row["Losing CSDuid"],
                losing_name=" ".join(row["Losing CSDname"].split()),
                losing_type=row["Losing CSDtype"],
                losing_change=row["Losing CSD Change Code Description"],
                effective=row["Effective Date"],
                line=row.line,
            )
        )
    return found
