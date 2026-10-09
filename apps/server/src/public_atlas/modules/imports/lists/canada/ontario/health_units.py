"""Ontario's public health units from the Ministry of Health's *Public Health Unit locations*
page: the 29 boards of health that remain after the mergers of 2025, every one a
`public_health_unit`, named as the page names it with the name Regulation 553 prescribes as an
alias, with its website as a candidate homepage and the counties, districts and municipalities
it serves as its served places.

The page is one table of the units with their addresses, phone numbers and websites. It
cannot be fetched by a script: every response carries a new bot-detection token, so no hash
can be pinned and a person saves the page into the loader's cache (`PAGE.instructions`). Its
rules:

- The page's name is the name ("Lakelands Public Health"); the heading of the unit's schedule
  in R.R.O. 1990, Reg. 553 (*Areas Comprising Health Units*, under the Health Protection and
  Promotion Act) is the legal name ("Haliburton Kawartha Northumberland Peterborough Health
  Unit"), kept as an alias. e-Laws serves the regulation as a legacy `.doc` the loader cannot
  read, so its schedules are the hand-written table in `OVERRIDES`, from the consolidation of
  2025-01-01 (last amended by O. Reg. 534/24), saved as a PDF for the record.
- Where the unit is a department of a municipality (Toronto, Ottawa, Hamilton, Chatham-Kent,
  Durham, Halton, Peel, York, Waterloo, Niagara, Lambton), the board of health is the council:
  the unit sits at that municipality or region and its parent is the government. Every other
  unit is an autonomous board: it sits at the municipality of its head office, read from the
  address through `communities.py`.
- The served places are the schedule's, read as the regulation is: a county named in a
  schedule is the geographic county, which takes in the separated cities and towns inside it
  (Windsor-Essex County serves Windsor and Pelee; Middlesex-London serves London), and a
  territorial district named whole is the district. Where a schedule carves a district up
  (Algoma without Hornepayne; Nipissing without Temagami and South Algonquin), the
  municipalities are listed one by one; the unorganized parts of Kenora and Thunder Bay that
  the schedules divide by survey lines hold no municipality. A served place carries the level
  and parent that tell the County of Peterborough from the city.
- The website is the page's, given a scheme.
"""

import logging
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

from public_atlas.modules.graph.service import normalize_url
from public_atlas.modules.imports.entries import (
    AliasEntry,
    Citation,
    Fact,
    InstitutionEntry,
    ServedPlace,
)
from public_atlas.modules.imports.files import Format, ListFile, ListFileError, OpenedFile
from public_atlas.modules.imports.lists.canada.ontario.communities import (
    MUNICIPALITY,
    PROVINCE,
    REGION,
    Location,
    location_of,
)
from public_atlas.modules.imports.models import Retrieval
from public_atlas.shared.text import name_key

if TYPE_CHECKING:
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = "CA"
PUBLIC_HEALTH_UNIT = "public_health_unit"

PAGE = ListFile(
    name="public_health_unit_locations_2026_08",
    title="Ontario Ministry of Health, Public Health Unit locations, updated 2026-08-28",
    url="https://www.ontario.ca/page/public-health-unit-locations",
    format=Format.HTML,
    retrieval=Retrieval.MANUAL,
    instructions=(
        "Open https://www.ontario.ca/page/public-health-unit-locations in a browser and save "
        'the page as HTML only (Ctrl+S, "Webpage, HTML Only"), or fetch it once with curl and a '
        "browser user agent. Every response carries a new bot-detection token, so no hash is "
        'pinned. The page says "Updated: August 28, 2026" and lists 29 units, from Algoma '
        "Public Health to York Region Public Health, each with an address, a phone number, a "
        "website and its Ontario Health region."
    ),
    filename_override="public-health-unit-locations.html",
)
SOURCES = (PAGE,)

EXPECTED = 29
# The page's table header, as the visible text runs its cells together.
HEADER = "Public Health UnitAddressOntario Health Region"
# A unit's last line: its Ontario Health region, or two joined by a bar.
REGIONS = frozenset({"Central", "East", "North East", "North West", "Toronto", "West"})


def region(place: str) -> Location:
    return Location(place, REGION, PROVINCE)


def municipality(place: str, parent: str | None = None) -> Location:
    return Location(place, MUNICIPALITY, parent)


# Algoma's municipalities except Hornepayne, and Nipissing's except Temagami and South
# Algonquin, which other schedules name.
ALGOMA_LESS_HORNEPAYNE = tuple(
    municipality(name)
    for name in (
        "Blind River",
        "Bruce Mines",
        "Dubreuilville",
        "Elliot Lake",
        "Hilton",
        "Hilton Beach",
        "Huron Shores",
        "Jocelyn",
        "Johnson",
        "Laird",
        "Macdonald, Meredith and Aberdeen Additional",
        "Plummer Additional",
        "Prince",
        "Sault Ste. Marie",
        "Spanish",
        "St. Joseph",
        "Tarbutt",
        "The North Shore",
        "Thessalon",
        "Wawa",
        "White River",
    )
)
NIPISSING_LESS_TWO = tuple(
    municipality(name)
    for name in (
        "Bonfield",
        "Calvin",
        "Chisholm",
        "East Ferris",
        "Mattawa",
        "Mattawan",
        "North Bay",
        "Papineau-Cameron",
        "West Nipissing",
    )
)

# Reg. 553, by the page's name of the unit. Fields: `legal_name` (the schedule's heading),
# `served` (the schedule's area as loaded places), `place` (the municipality or region whose
# department the unit is; absent for an autonomous board, which sits at its head office).
OVERRIDES: dict[str, dict[str, object]] = {
    "Algoma Public Health": {
        "legal_name": "The District of Algoma Health Unit",
        "served": ALGOMA_LESS_HORNEPAYNE,
    },
    "Chatham-Kent Public Health": {
        "legal_name": "Chatham-Kent Health Unit",
        "place": municipality("Chatham-Kent"),
        "served": (municipality("Chatham-Kent"),),
    },
    "Durham Region Health Department": {
        "legal_name": "Durham Regional Health Unit",
        "place": region("Durham"),
        "served": (region("Durham"),),
    },
    "Eastern Ontario Health Unit": {
        "legal_name": "The Eastern Ontario Health Unit",
        "served": (
            region("Stormont, Dundas and Glengarry"),
            region("Prescott and Russell"),
            municipality("Cornwall"),
        ),
    },
    "Grand Erie Public Health": {
        "legal_name": "Grand Erie Health Unit",
        "served": (
            municipality("Brant"),
            municipality("Brantford"),
            municipality("Haldimand County"),
            municipality("Norfolk County"),
        ),
    },
    "Grey Bruce Public Health": {
        "legal_name": "Grey Bruce Health Unit",
        "served": (region("Bruce"), region("Grey")),
    },
    "Lakelands Public Health": {
        "legal_name": "Haliburton Kawartha Northumberland Peterborough Health Unit",
        "served": (
            region("Haliburton"),
            municipality("Kawartha Lakes"),
            region("Northumberland"),
            municipality("Peterborough"),
            region("Peterborough"),
        ),
    },
    "Halton Region Health Department": {
        "legal_name": "Halton Regional Health Unit",
        "place": region("Halton"),
        "served": (region("Halton"),),
    },
    "Hamilton Public Health Services": {
        "legal_name": "City of Hamilton Health Unit",
        "place": municipality("Hamilton", PROVINCE),
        "served": (municipality("Hamilton", PROVINCE),),
    },
    "Huron Perth Public Health": {
        "legal_name": "Huron Perth Health Unit",
        "served": (
            region("Huron"),
            region("Perth"),
            municipality("Stratford"),
            municipality("St. Marys"),
        ),
    },
    "Lambton Public Health": {
        "legal_name": "Lambton Health Unit",
        "place": region("Lambton"),
        "served": (region("Lambton"),),
    },
    "Middlesex-London Health Unit": {
        "legal_name": "Middlesex-London Health Unit",
        "served": (region("Middlesex"), municipality("London")),
    },
    "Niagara Region Public Health": {
        "legal_name": "Niagara Regional Area Health Unit",
        "place": region("Niagara"),
        "served": (region("Niagara"),),
    },
    "North Bay Parry Sound District Health Unit": {
        "legal_name": "North Bay Parry Sound District Health Unit",
        "served": (*NIPISSING_LESS_TWO, region("Parry Sound")),
    },
    "Northeastern Public Health": {
        "legal_name": "Northeastern Health Unit",
        "served": (
            region("Cochrane"),
            region("Timiskaming"),
            municipality("Hornepayne"),
            municipality("Temagami"),
        ),
    },
    "Northwestern Health Unit": {
        "legal_name": "Northwestern Health Unit",
        "served": (region("Rainy River"), region("Kenora")),
    },
    "Ottawa Public Health": {
        "legal_name": "City of Ottawa Health Unit",
        "place": municipality("Ottawa"),
        "served": (municipality("Ottawa"),),
    },
    "Peel Public Health": {
        "legal_name": "Peel Regional Health Unit",
        "place": region("Peel"),
        "served": (region("Peel"),),
    },
    "Renfrew County and District Health Unit": {
        "legal_name": "Renfrew County and District Health Unit",
        "served": (
            region("Renfrew"),
            municipality("Pembroke"),
            municipality("South Algonquin"),
        ),
    },
    "Simcoe Muskoka District Health Unit": {
        "legal_name": "Simcoe Muskoka District Health Unit",
        "served": (
            region("Simcoe"),
            region("Muskoka"),
            municipality("Barrie"),
            municipality("Orillia"),
        ),
    },
    "Southeast Public Health": {
        "legal_name": "South East Health Unit",
        "served": (
            region("Frontenac"),
            region("Lennox and Addington"),
            region("Hastings"),
            municipality("Quinte West"),
            municipality("Prince Edward County"),
            region("Leeds and Grenville"),
            region("Lanark"),
            municipality("Kingston"),
            municipality("Belleville"),
            municipality("Brockville"),
            municipality("Gananoque"),
            municipality("Prescott"),
            municipality("Smiths Falls"),
        ),
    },
    "Southwestern Public Health": {
        "legal_name": "Oxford Elgin St. Thomas Health Unit",
        "served": (region("Oxford"), region("Elgin"), municipality("St. Thomas")),
    },
    "Public Health Sudbury & Districts": {
        "legal_name": "Sudbury and District Health Unit",
        "served": (region("Sudbury"), region("Manitoulin"), municipality("Greater Sudbury")),
    },
    "Thunder Bay District Health Unit": {
        "legal_name": "Thunder Bay District Health Unit",
        "served": (region("Thunder Bay"),),
    },
    "Toronto Public Health": {
        "legal_name": "City of Toronto Health Unit",
        "place": municipality("Toronto"),
        "served": (municipality("Toronto"),),
    },
    "Region of Waterloo Public Health and Paramedic Services": {
        "legal_name": "Waterloo Health Unit",
        "place": region("Waterloo"),
        "served": (region("Waterloo"),),
    },
    "Wellington-Dufferin-Guelph Public Health": {
        "legal_name": "Wellington-Dufferin-Guelph Health Unit",
        "served": (region("Wellington"), region("Dufferin"), municipality("Guelph")),
    },
    "Windsor-Essex County Health Unit": {
        "legal_name": "Windsor-Essex County Health Unit",
        "served": (region("Essex"), municipality("Windsor"), municipality("Pelee")),
    },
    "York Region Public Health": {
        "legal_name": "York Regional Health Unit",
        "place": region("York"),
        "served": (region("York"),),
    },
}

_WEBSITE = re.compile(r"^Website:\s*(?P<rest>.*)$")
_ADDRESS = re.compile(
    r"(?:https?://)?(?:www\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[a-z]{2,}(?:/\S*)?"
)
_CITY = re.compile(r"^(?P<city>.+?),?\s+ON\s+[A-Z]\d[A-Za-z]\s?\d[A-Za-z]\d$")
_ACRONYM = re.compile(r"\((?P<acronym>[A-Z]{2,})\)")


def is_region_line(text: str) -> bool:
    return all(part.strip() in REGIONS for part in text.split("|"))


def read_units(opened: OpenedFile) -> list[tuple[str, list[tuple[int, str]]]]:
    """The page's units: each name as `OVERRIDES` keys it, with the numbered lines of its
    table row, from the header to the page's "Updated" line."""
    try:
        start = opened.lines.index(HEADER) + 1
    except ValueError:
        raise ListFileError(f"{PAGE.name}: the page has no table of health units") from None
    units: list[tuple[str, list[tuple[int, str]]]] = []
    block: list[tuple[int, str]] = []
    for number, text in enumerate(opened.lines[start:], start=start + 1):
        if text.startswith("Updated:"):
            break
        block.append((number, text))
        if is_region_line(text) or (text.endswith(tuple(REGIONS)) and "Website:" in text):
            units.append((_name_of(block[0][1]), block))
            block = []
    if block or len(units) != EXPECTED:
        raise ListFileError(
            f"{PAGE.name}: the page lists {len(units)} health units, not {EXPECTED}"
        )
    return units


def _name_of(first_line: str) -> str:
    """The unit the row's first line names: the longest `OVERRIDES` key it starts with, since
    the page runs a name into its address where a cell lacks its line break."""
    keys = sorted((key for key in OVERRIDES if first_line.startswith(key)), key=len)
    if not keys:
        raise ListFileError(f"{PAGE.name}: no health unit in Reg. 553 starts {first_line!r}")
    return keys[-1]


def website_of(lines: list[tuple[int, str]]) -> tuple[str, int] | None:
    """The row's website with a scheme, and the line it is on: the text after "Website:", or
    the next line when that is empty. A region name the page runs onto the address is left."""
    for index, (number, text) in enumerate(lines):
        match = _WEBSITE.match(text)
        if match is None:
            continue
        cited, rest = number, match.group("rest").strip()
        if not rest and index + 1 < len(lines):
            cited, rest = lines[index + 1]
        found = _ADDRESS.search(rest)
        if found is None:
            return None
        return normalize_url(found.group()), cited
    return None


def city_of(lines: list[tuple[int, str]]) -> str:
    for _, text in lines:
        match = _CITY.match(text)
        if match:
            return match.group("city")
    raise ListFileError(f"{PAGE.name}: no address line in {lines[0][1]!r}")


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[InstitutionEntry]:  # noqa: ARG001 - the loader's signature
    """The units, by name."""
    opened = files[PAGE.name]
    found: list[InstitutionEntry] = []
    for name, lines in read_units(opened):
        fields = OVERRIDES[name]
        legal_name = str(fields["legal_name"])
        served = fields["served"]
        assert isinstance(served, tuple)  # noqa: S101 - the table holds tuples of locations
        where = fields.get("place") or location_of(city_of(lines))
        assert isinstance(where, Location)  # noqa: S101 - the table holds locations
        aliases: list[AliasEntry] = []
        acronym = _ACRONYM.search(lines[0][1])
        if acronym:
            aliases.append(AliasEntry(text=acronym.group("acronym"), is_acronym=True))
        if name_key(legal_name) != name_key(name):
            aliases.append(AliasEntry(text=legal_name))
        citation = Citation(source=PAGE.name, line=lines[0][0])
        citations: dict[Fact, Citation] = {"institution": citation}
        website = website_of(lines)
        homepage = None
        if website is not None:
            homepage, line = website
            citations["homepage"] = Citation(source=PAGE.name, line=line)
        else:
            logger.warning("%s has no website on the page", name)
        found.append(
            InstitutionEntry(
                name=name,
                aliases=tuple(aliases),
                institution_type=PUBLIC_HEALTH_UNIT,
                place=where.place,
                place_level=where.level,
                place_parent=where.parent,
                served_places=tuple(
                    ServedPlace(name=where.place, level=where.level, parent=where.parent)
                    for where in served
                ),
                homepage=homepage,
                citations=citations,
            )
        )
    return sorted(found, key=lambda entry: name_key(entry.name))
