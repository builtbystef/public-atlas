"""The Census Bureau's 2022 Census of Governments list of government units, shared by the
lists that read it: `us/government_units` reads the General Purpose sheet (counties,
municipalities and townships, with their legal names and websites) and `us/special_districts`
the Special District sheet. The workbook is one file, and a file's bytes have one stored text,
so one `ListFile` renders both sheets and each list keeps the rows of its sheet.

The sheet writes every name in capitals ("CITY OF SPRINGFIELD", "PRATTVILLE HOUSING
AUTHORITY"); `title_case` recases one as a page would write it, keeping the abbreviations
districts are known by (MUD, PUD, ISD). A legal name puts the designator first and the place
name after "OF"; `split_legal_name` takes one apart so the place name can be taken from the
census's own spelling where the two agree.
"""

import re
from dataclasses import dataclass
from functools import partial

from public_atlas.modules.graph.service import host_of, is_domain_name, normalize_url
from public_atlas.modules.imports.files import Format, ListFile, OpenedFile, Row

GENERAL_PURPOSE = "General Purpose"
SPECIAL_DISTRICT = "Special District"
ACTIVE = "Y"

GOVT_UNITS = ListFile(
    name="census_govt_units_2022",
    title=(
        "U.S. Census Bureau, 2022 Census of Governments, Government Units Survey: the list of "
        "government units (Govt_Units_2022_Final.xlsx), General Purpose and Special District "
        "sheets"
    ),
    url="https://www2.census.gov/programs-surveys/gus/datasets/2022/govt_units_2022.ZIP",
    sha256="3ef3d93c91697b00d4d53384176dc584db9dacbd0f0a23e45657f0a3a1058c28",
    format=Format.SPREADSHEET,
    member="Govt_Units_2022_Final.xlsx",
    sheets=(GENERAL_PURPOSE, SPECIAL_DISTRICT),
    # The address columns stay out of the stored text; `UNIT_TYPE` and `FIPS_PLACE` are the
    # General Purpose sheet's, `FUNCTION_NAME` the Special District sheet's.
    columns=(
        "CENSUS_ID_GIDID",
        "UNIT_NAME",
        "UNIT_TYPE",
        "FUNCTION_NAME",
        "CITY",
        "STATE",
        "WEB_ADDRESS",
        "FIPS_STATE",
        "FIPS_COUNTY",
        "FIPS_PLACE",
        "COUNTY_AREA_NAME",
        "IS_ACTIVE",
    ),
)

# The General Purpose sheet's unit types.
COUNTY = "1 - COUNTY"
MUNICIPAL = "2 - MUNICIPAL"
TOWNSHIP = "3 - TOWNSHIP"


@dataclass(frozen=True, slots=True)
class GovernmentUnit:
    """One row of either sheet."""

    gid: str | None
    name: str
    # The General Purpose sheet's unit type, or the Special District sheet's function.
    unit_type: str
    function: str
    city: str
    state: str
    website: str | None
    fips_state: str
    fips_county: str
    # A county's is 99 and its county code; a municipality's its place code; a township's its
    # county subdivision code.
    fips_place: str
    county_area: str
    active: bool
    line: int

    @property
    def type_name(self) -> str:
        """The unit type's word: "county", "municipal", "township"."""
        return self.unit_type.partition(" - ")[2].lower()

    @property
    def key(self) -> str:
        """The unit as the sheet keys it: state and place code, or state, county and
        subdivision code for a township."""
        if self.unit_type == TOWNSHIP:
            return self.fips_state + self.fips_county + self.fips_place
        return self.fips_state + self.fips_place


def read_units(opened: OpenedFile, sheet: str) -> list[GovernmentUnit]:
    """The rows of one sheet."""
    return [_unit(row) for row in opened.rows if row.sheet == sheet]


def _unit(row: Row) -> GovernmentUnit:
    return GovernmentUnit(
        gid=row.get("CENSUS_ID_GIDID") or None,
        name=" ".join(row["UNIT_NAME"].split()),
        unit_type=row.get("UNIT_TYPE"),
        function=row.get("FUNCTION_NAME"),
        city=row.get("CITY"),
        state=row["STATE"],
        website=website(row.get("WEB_ADDRESS")),
        fips_state=row["FIPS_STATE"].zfill(2),
        fips_county=row["FIPS_COUNTY"].zfill(3),
        fips_place=row.get("FIPS_PLACE").zfill(5) if row.get("FIPS_PLACE") else "",
        county_area=row.get("COUNTY_AREA_NAME"),
        active=row["IS_ACTIVE"] == ACTIVE,
        line=row.line,
    )


# --- Websites ---


_SCHEME = re.compile(r"^(https?):/*", re.IGNORECASE)


def website(value: str | None) -> str | None:
    """A self-reported web address as a URL, or None when the cell holds no address (empty, a
    note, an e-mail address, a host that is no domain name). A scheme missing its slashes
    ("http:www.x.org") is repaired."""
    if value is None:
        return None
    value = _SCHEME.sub(r"\1://", value.strip())
    if not value or "@" in value or " " in value or "." not in value:
        return None
    try:
        url = normalize_url(value)
    except ValueError:
        return None
    return url if is_domain_name(host_of(url)) else None


# --- Names ---

# Words that stay lower case inside a name.
_SMALL_WORDS = frozenset(
    {"of", "and", "the", "for", "at", "on", "in", "to", "by", "a", "an", "de", "del", "y"}
)
# Abbreviations districts are known by, kept in capitals: utility and improvement districts
# (MUD, PUD, PID, WCID, CDD), school and sanitation districts (ISD, CSD, USD, MSD), fire and
# emergency services (FPD, RFD, ESD, EMS), conservation (SWCD), and a few more.
_ACRONYMS = frozenset(
    {
        "MUD",
        "PUD",
        "PID",
        "WCID",
        "FWSD",
        "CDD",
        "CID",
        "SID",
        "BID",
        "TIF",
        "TDD",
        "TIRZ",
        "ISD",
        "CSD",
        "USD",
        "MSD",
        "FPD",
        "RFD",
        "ESD",
        "EMS",
        "SWCD",
        "JPA",
        "COG",
        "EDC",
        "EDA",
        "IDA",
        "DDA",
        "LLC",
        "USA",
        "E911",
        "911",
        "II",
        "III",
        "IV",
        "VI",
        "VII",
        "VIII",
    }
)
_MC = re.compile(r"^MC([A-Z]{3,})$")
_ORDINAL = re.compile(r"^(\d+)(ST|ND|RD|TH)$")
_WORD = re.compile(r"[A-Za-z0-9]+")


def title_case(name: str) -> str:
    """A name written in capitals as a page would write it: "Prattville Housing Authority",
    "Harris County MUD 400", "McHenry Township Fire Protection District", "3rd Street Bridge
    Authority". Best effort: an abbreviation not in `_ACRONYMS` is recased as a word."""
    return " ".join(
        _WORD.sub(partial(_recase, first=index == 0), word)
        for index, word in enumerate(name.split())
    )


def _recase(match: re.Match[str], *, first: bool) -> str:
    word = match.group()
    if word in _ACRONYMS:
        return word
    # The letter after an apostrophe: "O'Fallon", but "Women's".
    if match.start() > 0 and match.string[match.start() - 1] == "'" and len(word) == 1:
        return word.lower()

    if (ordinal := _ORDINAL.match(word)) is not None:
        return ordinal.group(1) + ordinal.group(2).lower()
    if (mc := _MC.match(word)) is not None:
        return "Mc" + mc.group(1).capitalize()
    if word.lower() in _SMALL_WORDS and not first:
        return word.lower()
    return word.capitalize()


# The legal designators the General Purpose sheet puts before "OF", with the designator as a
# name writes it.
DESIGNATORS: dict[str, str] = {
    "CITY": "City",
    "TOWN": "Town",
    "VILLAGE": "Village",
    "BOROUGH": "Borough",
    "TOWNSHIP": "Township",
    "CHARTER TOWNSHIP": "Charter Township",
    "CIVIL TOWNSHIP": "Civil Township",
    "METRO TOWNSHIP": "Metro Township",
    "PLANTATION": "Plantation",
    "MUNICIPALITY": "Municipality",
    "CORPORATION": "Corporation",
    "COUNTY": "County",
    "PARISH": "Parish",
    "CITY AND COUNTY": "City and County",
    "CITY AND BOROUGH": "City and Borough",
    "CITY-PARISH": "City-Parish",
    "UNIFIED GOVERNMENT": "Unified Government",
    "CONSOLIDATED GOVERNMENT": "Consolidated Government",
    "METROPOLITAN GOVERNMENT": "Metropolitan Government",
    "METRO GOVERNMENT": "Metro Government",
    "URBAN COUNTY GOVERNMENT": "Urban County Government",
}
_LEGAL = re.compile(
    r"^(?P<designator>" + "|".join(re.escape(d) for d in DESIGNATORS) + r") OF (?P<rest>.+)$"
)
_LETTERS = re.compile(r"[^A-Z0-9]")


def split_legal_name(name: str) -> tuple[str, str] | None:
    """A legal name as its designator and the name after "OF": "CITY OF SPRINGFIELD" is
    ("City", "SPRINGFIELD"). None for a name of another shape."""
    match = _LEGAL.match(name)
    if match is None:
        return None
    return DESIGNATORS[match.group("designator")], match.group("rest")


def same_letters(a: str, b: str) -> bool:
    """Whether two spellings are one name but for case and punctuation: "ST MARTIN" and
    "St. Martin", "SEWALLS POINT" and "Sewall's Point"."""
    return _LETTERS.sub("", a.upper()) == _LETTERS.sub("", b.upper())
