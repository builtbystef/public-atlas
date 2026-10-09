"""Ontario's public library boards from the Ministry of Tourism, Culture and Gaming's annual
*Ontario public library statistics*: 290 boards (241 public and union library boards, 12 county,
county co-operative and regional library boards, 33 First Nations library boards and 4 local
services board libraries), every one a `library`, with its website as a candidate homepage,
attached to the municipality, county or district it serves.

The file is one spreadsheet (sheet `OpenData`, 355 rows, one per library system that filed the
2025 survey). Its rules:

- `A1.4 Type of Library Service` tells a board from a place that buys service from one: a
  contracting municipality and a contracting local services board are places served by another
  board, not institutions, and are left out.
- The file names a system by its municipality in the survey's shorthand ("Addington Highlands
  Twp", "Alderville FN", "Kenora City", "Bonnechere Union"). The board's name is composed from
  that: the shorthand's type words are dropped and "Public Library" is added, a union library
  keeps "Union", a First Nation's keeps "First Nation", and "&" is written "and". The file's
  shorthand stays as an alias. A row the composition misnames is corrected in `OVERRIDES`.
- The place is the municipality the name says, with its level and parent so a town named like
  its district (Cochrane, Kenora, Parry Sound) is the town, and the City of Hamilton is not the
  township of that name. A county or regional library sits at its county or region. A union,
  memorial or district library, whose name is not one municipality's, and a local services
  board library, whose community is unorganized land, are placed by hand in `PLACES`.
- A First Nation's library is placed by hand in `FIRST_NATIONS`: a reserve is land, not a
  municipality, so the library sits at the county or district the reserve lies in, or at the
  single-tier city that surrounds it (Greater Sudbury, Chatham-Kent, Brant).
- The website is the row's, given a scheme where it has none and its trailing stop dropped.
  Text that is no address (a name, an email address) is none, and a page on a social network
  is none: the network is a platform the graph never trusts, so the page cannot be verified as
  a homepage.

The CKAN resource is `f0ba384f-d8ff-427a-a8a2-29c921e19e9d` on dataset
`363fff31-6a07-41eb-9922-e9b64192b08b`; the file name carries the survey year, so a new release
is one URL and hash swap.
"""

import logging
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

from public_atlas.modules.graph.service import host_of, normalize_url
from public_atlas.modules.imports.entries import AliasEntry, Citation, Fact, InstitutionEntry
from public_atlas.modules.imports.files import Format, ListFile, OpenedFile, Row
from public_atlas.modules.imports.lists.canada.ontario.communities import (
    MUNICIPALITY,
    PROVINCE,
    REGION,
    Location,
    location_of,
)
from public_atlas.shared.text import name_key

if TYPE_CHECKING:
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = "CA"
LIBRARY = "library"

STATISTICS = ListFile(
    name="ontario_library_statistics_2025",
    title=(
        "Ontario Ministry of Tourism, Culture and Gaming, Ontario public library statistics, "
        "2025 survey"
    ),
    url=(
        "https://data.ontario.ca/dataset/363fff31-6a07-41eb-9922-e9b64192b08b/resource/"
        "f0ba384f-d8ff-427a-a8a2-29c921e19e9d/download/opendata_2025_ontario_library_statistics.xlsx"
    ),
    sha256="5478a9ba9982d8d2fb8b5f154bf79b270c49fdcde06e7a0337af3d67f2bc5b29",
    format=Format.SPREADSHEET,
    # The survey's hundreds of figures stay out of the stored text.
    columns=(
        "Library Full Name",
        "Library Number",
        "A1.4 Type of Library Service (English)",
        "A1.10 City/Town",
        "A1.13 Web Site Address",
    ),
)
SOURCES = (STATISTICS,)

NAME = "Library Full Name"
TYPE = "A1.4 Type of Library Service (English)"
CITY = "A1.10 City/Town"
WEBSITE = "A1.13 Web Site Address"

# The file's types that are boards, and what the composed name says of each.
PUBLIC = "Public or Union Library"
COUNTY = "County, County co-operative or Regional Municipality Library"
FIRST_NATION = "First Nations Library"
LOCAL_SERVICES_BOARD = "LSB Library"
BOARD_TYPES = frozenset({PUBLIC, COUNTY, FIRST_NATION, LOCAL_SERVICES_BOARD})
# Places served by another board, not institutions.
CONTRACTING_TYPES = frozenset({"Contracting Municipality", "Contracting LSB"})

# Hosts whose pages are never a homepage: a social network is a platform the graph never trusts.
SOCIAL_HOSTS = frozenset({"facebook.com", "www.facebook.com"})

# Hand corrections keyed by the file's name, each with its reason. Fields: `name` (the board's
# name, when the composed one is wrong), `place` (a `Location`, when the name's is wrong).
OVERRIDES: dict[str, dict[str, object]] = {
    "Kingston-Frontenac County": {
        "name": "Kingston Frontenac Public Library",
        "place": Location("Kingston"),
        "reason": "the board serves the city and the county and is named for both, not a county",
    },
    "Atikameksheng Anishnawbek Band No. 6 FN": {
        "name": "Atikameksheng Anishnawbek First Nation Public Library",
        "reason": "the band number is not part of the name",
    },
    "Mattice-Val Cote Twp": {
        "place": Location("Mattice-Val Côté"),
        "reason": "the file leaves out the accents",
    },
    "St. Charles": {
        "place": Location("St.-Charles"),
        "reason": "the census writes the municipality with a hyphen",
    },
    "Sioux Narrows Nestor Falls Twp": {
        "place": Location("Sioux Narrows-Nestor Falls"),
        "reason": "the file leaves out the hyphen",
    },
    "Blue Mountains": {
        "place": Location("The Blue Mountains"),
        "reason": "the file leaves out the article",
    },
    "La Nation": {
        "place": Location("The Nation"),
        "reason": "the census writes the municipality in English",
    },
}

# Where a board whose name is not one municipality's sits: a union library at the municipality
# of its main branch, a local services board's at the territorial district its community is in.
PLACES: dict[str, Location] = {
    "Bonnechere Union": Location("Bonnechere Valley"),
    "Bruce Mines & Plummer Additional Union": Location("Bruce Mines"),
    "Burk's Falls, Armour & Ryerson Union": Location("Burk's Falls"),
    "Lincoln Pelham Union Public Library": Location("Lincoln"),
    "Owen Sound & North Grey Union": Location("Owen Sound"),
    "Perth and District Union": Location("Perth", MUNICIPALITY, "Lanark"),
    "South River-Machar Union": Location("South River"),
    "Sundridge-Strong Union": Location("Sundridge"),
    "Whitestone-Hagerman Memorial": Location("Whitestone"),
    "Britt Area": Location("Parry Sound", REGION, PROVINCE),
    "Gogama LSB": Location("Sudbury", REGION, PROVINCE),
    "Loring, Port Loring and District Local Services Board": Location(
        "Parry Sound", REGION, PROVINCE
    ),
    "Phelps": Location("Nipissing", REGION, PROVINCE),
}

# A First Nation's library by the file's name: the county or district its reserve lies in, or
# the single-tier municipality that surrounds the reserve.
FIRST_NATIONS: dict[str, Location] = {
    "Alderville FN": Location("Northumberland", REGION, PROVINCE),
    "Algonquins of Pikwakanagan FN": Location("Renfrew", REGION, PROVINCE),
    "Atikameksheng Anishnawbek Band No. 6 FN": Location("Greater Sudbury"),
    "Beausoleil First Nation Public Library": Location("Simcoe", REGION, PROVINCE),
    "Big Grassy FN": Location("Rainy River", REGION, PROVINCE),
    "Biigtigong Nishnaabeg": Location("Thunder Bay", REGION, PROVINCE),
    "Bkejwanong FN": Location("Lambton", REGION, PROVINCE),
    "Chippewas of Georgina Island FN": Location("York", REGION, PROVINCE),
    "Chippewas of Kettle & Stony Point FN": Location("Lambton", REGION, PROVINCE),
    "Chippewas of Rama FN": Location("Simcoe", REGION, PROVINCE),
    "Curve Lake FN": Location("Peterborough", REGION, PROVINCE),
    "Delaware FN": Location("Chatham-Kent"),
    "Dokis FN": Location("Parry Sound", REGION, PROVINCE),
    "Garden River FN": Location("Algoma", REGION, PROVINCE),
    "Henvey Inlet FN": Location("Parry Sound", REGION, PROVINCE),
    "Iskatewizaagegan No. 39 FN": Location("Kenora", REGION, PROVINCE),
    "M'Chigeeng FN": Location("Manitoulin", REGION, PROVINCE),
    "Mattagami FN": Location("Sudbury", REGION, PROVINCE),
    "Michipicoten FN": Location("Algoma", REGION, PROVINCE),
    "Mississauga FN": Location("Algoma", REGION, PROVINCE),
    "Mohawks of the Bay of Quinte FN": Location("Hastings", REGION, PROVINCE),
    "New Credit FN": Location("Brant"),
    "Nipissing FN": Location("Nipissing", REGION, PROVINCE),
    "Sagamok Anishnawbek FN": Location("Sudbury", REGION, PROVINCE),
    "Seine River FN": Location("Rainy River", REGION, PROVINCE),
    "Serpent River FN": Location("Algoma", REGION, PROVINCE),
    "Sheshegwaning FN": Location("Manitoulin", REGION, PROVINCE),
    "Six Nations": Location("Brant"),
    "Temagami FN": Location("Nipissing", REGION, PROVINCE),
    "Thessalon FN": Location("Algoma", REGION, PROVINCE),
    "Wahta Mohawk FN": Location("Muskoka", REGION, PROVINCE),
    "Wasauksing FN": Location("Parry Sound", REGION, PROVINCE),
    "Whitefish River FN": Location("Manitoulin", REGION, PROVINCE),
}

# The shorthand's type words, at the end of a name, and a list's inverted form.
_TYPE_WORDS = re.compile(
    r"\s*(?:,\s*(?:Township|City|Municipality|Town) of"
    r"|Public Library Board|Library Board|Public Library|Library|Local Services Board"
    r"|Union|Township|Twp\.?|Town|City|FN|LSB)$",
    re.IGNORECASE,
)
_UNION = re.compile(r"\bUnion\b")
# What a name says beyond the municipality's: dropped to find the place.
_BEYOND_PLACE = re.compile(r"\s*(?:Memorial|(?:&|and) Area|(?:&|and) District)$", re.IGNORECASE)
_ADDRESS = re.compile(r"(?:https?://|www\.)\S+|[\w.-]+\.(?:ca|com|org|net|on\.ca)(?:/\S*)?")


def shorthand(cell: str) -> str:
    """The file's name as written, whitespace evened out and a bare hyphen closed up."""
    return " ".join(cell.replace(" - ", "-").split())


def base_name(text: str) -> str:
    """The name without its type words: "Addington Highlands" from "Addington Highlands Twp",
    "Bonnechere" from "Bonnechere Union"."""
    while True:
        stripped = _TYPE_WORDS.sub("", text).strip()
        if stripped == text or not stripped:
            return text
        text = stripped


def composed_name(text: str, library_type: str) -> str:
    """The board's name from the file's shorthand."""
    base = base_name(text).replace(" & ", " and ")
    words = [base]
    if library_type == FIRST_NATION and text.endswith(" FN"):
        words.append("First Nation")
    if _UNION.search(text):
        words.append("Union")
    words.append("Public Library")
    return " ".join(words)


def place_of(text: str, library_type: str) -> Location:
    """Where the board sits, from its name: the municipality the name says, or the county or
    region for a county library."""
    base = _BEYOND_PLACE.sub("", base_name(text)).replace(" & ", " and ").strip()
    if library_type == COUNTY:
        return Location(base, REGION, PROVINCE)
    return location_of(base)


def homepage_of(cell: str) -> str | None:
    """The row's address with a scheme, or none: text that is no address, or a page on a social
    network."""
    text = cell.strip()
    if not text or "@" in text:
        return None
    match = _ADDRESS.search(text)
    if match is None:
        return None
    url = normalize_url(match.group().rstrip(".,;"))
    if host_of(url) in SOCIAL_HOSTS:
        return None
    return url


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[InstitutionEntry]:  # noqa: ARG001 - the loader's signature
    """The boards, by name."""
    opened = files[STATISTICS.name]
    found: list[InstitutionEntry] = []
    applied: set[str] = set()
    for row in opened.rows:
        listed = shorthand(row[NAME])
        library_type = row[TYPE]
        if not listed or library_type in CONTRACTING_TYPES:
            continue
        if library_type not in BOARD_TYPES:
            logger.warning("%s has an unknown type %r; left out", listed, library_type)
            continue
        fields = OVERRIDES.get(listed, {})
        if fields:
            applied.add(listed)
            logger.info("override: %s: %s", listed, fields["reason"])
        found.append(_entry(row, listed, library_type, fields))
    for listed, fields in OVERRIDES.items():
        if listed not in applied:
            logger.warning(
                "override changed nothing: %s: %s (no such row)", listed, fields["reason"]
            )
    return sorted(found, key=lambda entry: name_key(entry.name))


def _entry(
    row: Row, listed: str, library_type: str, fields: Mapping[str, object]
) -> InstitutionEntry:
    name = str(fields.get("name") or composed_name(listed, library_type))
    where = fields.get("place") or FIRST_NATIONS.get(listed) or PLACES.get(listed)
    if where is None:
        if library_type in (FIRST_NATION, LOCAL_SERVICES_BOARD):
            logger.warning("%s is not placed by hand; placed by its name", listed)
        where = place_of(listed, library_type)
    assert isinstance(where, Location)  # noqa: S101 - the tables hold locations
    homepage = homepage_of(row[WEBSITE])
    citation = Citation(source=STATISTICS.name, line=row.line)
    citations: dict[Fact, Citation] = {"institution": citation}
    if homepage is not None:
        citations["homepage"] = citation
    aliases = () if listed == name else (AliasEntry(text=listed),)
    return InstitutionEntry(
        name=name,
        aliases=aliases,
        institution_type=LIBRARY,
        place=where.place,
        place_level=where.level,
        place_parent=where.parent,
        homepage=homepage,
        citations=citations,
    )
