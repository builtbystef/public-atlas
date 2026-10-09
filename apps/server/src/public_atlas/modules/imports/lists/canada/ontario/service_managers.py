"""Ontario's district social services administration boards from the Ministry of Municipal
Affairs and Housing's *List of service managers*: the 10 boards that deliver housing, Ontario
Works and child care across the north's territorial districts, every one a
`municipal_corporation` under its district, with the municipalities it serves as its served
places and its housing page as a candidate homepage.

The list is one CSV with a row per municipality (425 rows) naming the municipality's service
manager in a link whose title is the manager's name and whose address is its housing page, as
the municipal directory's cells are written. Its rules:

- A service manager that is a municipality (37: the cities, counties and regions that are
  consolidated municipal service managers) is a role of a government the places list loads,
  not a new body: nothing is loaded for it.
- A board is named "... Services Board" or "... Social Services Administration Board". Its
  place is the territorial district it is named for, a region with no government, so the
  board's parent is none; the Sault Ste. Marie board's district is Algoma, and the
  Manitoulin-Sudbury board sits at Sudbury, where its head office is.
- The board's served places are its rows' municipalities, written as the list writes them with
  the forms the places list has ("&" is "and", "Add'l" is "Additional"); `MEMBERS` corrects the
  cells the list gets wrong. A row for unincorporated territory is unorganized land, no place.
- The housing page is the board's own site: the homepage is the link as given, path included,
  since the board's site is where the page sits.

The CKAN resource is `ba287328-1e86-4d4f-8e87-fa7f148aef1d` on dataset
`70eef1c4-0b40-44bd-a4f1-0281731235cb`.
"""

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from public_atlas.modules.graph.service import normalize_url
from public_atlas.modules.imports.entries import Citation, InstitutionEntry, ServedPlace
from public_atlas.modules.imports.files import Format, ListFile, ListFileError, OpenedFile, Row
from public_atlas.modules.imports.lists.canada.ontario.communities import (
    MUNICIPALITY,
    PROVINCE,
    REGION,
)
from public_atlas.shared.text import name_key, repair_mojibake

if TYPE_CHECKING:
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = "CA"
MUNICIPAL_CORPORATION = "municipal_corporation"

LIST = ListFile(
    name="service_managers_list",
    title=(
        "Ontario Ministry of Municipal Affairs and Housing, List of service managers (Find your "
        "local service manager)"
    ),
    url=(
        "https://data.ontario.ca/dataset/70eef1c4-0b40-44bd-a4f1-0281731235cb/resource/"
        "ba287328-1e86-4d4f-8e87-fa7f148aef1d/download/find_your_local_sm_-_english.csv"
    ),
    sha256="f0464f4cd21763e31947846867b0e63843494a2c08568ec82279885619effda8",
    format=Format.CSV,
    # The phone, email and address columns stay out of the stored text.
    columns=("Municipality", "Service manager"),
)
SOURCES = (LIST,)

# A board's district, by the board's name as the list writes it.
DISTRICTS: dict[str, str] = {
    "Algoma District Services Administration Board": "Algoma",
    "District of Cochrane Social Service Administration Board": "Cochrane",
    "District of Nipissing Social Services Administration Board": "Nipissing",
    "District of Parry Sound Social Services Administration Board": "Parry Sound",
    "District of Sault Ste. Marie Social Services Administration Board": "Algoma",
    "District of Timiskaming Social Services Administration Board": "Timiskaming",
    "Kenora District Services Board": "Kenora",
    "Manitoulin-Sudbury District Services Board": "Sudbury",
    "Rainy River District Social Services Administration Board": "Rainy River",
    "Thunder Bay District Social Services Administration Board": "Thunder Bay",
}

# Hand corrections keyed by a board's name, each with its reason. None so far.
OVERRIDES: dict[str, dict[str, str]] = {}

# A municipality cell the list gets wrong, to the municipality's name as the places list has it
# (None: no place), each with its reason.
MEMBERS: dict[str, dict[str, str | None]] = {
    "Township of Michipicoten": {
        "place": None,
        "reason": "the Municipality of Wawa under its former name, listed beside it",
    },
    "Township of Tarbutt & Tarbutt Additional": {
        "place": "Tarbutt",
        "reason": "the township is Tarbutt since 2022",
    },
    "Township of Sioux Narrows\u2013Nester Falls": {
        "place": "Sioux Narrows-Nestor Falls",
        "reason": "the list misspells Nestor",
    },
    "Township of Mattice-Val Cote": {
        "place": "Mattice-Val Côté",
        "reason": "the list leaves out the accents",
    },
    "Township of Sables Spanish Rivers": {
        "place": "Sables-Spanish Rivers",
        "reason": "the list leaves out the hyphen",
    },
    "Township Tehkummah": {"place": "Tehkummah", "reason": "the list leaves out 'of'"},
    "Municipality of St. Charles": {
        "place": "St.-Charles",
        "reason": "the census writes the municipality with a hyphen",
    },
}

_ANCHOR = re.compile(r'^<a title="(?P<title>[^"]*)"(?: href="(?P<href>[^"]*)")?>')
_BOARD = re.compile(r"\bServices? (?:Administration )?Board$")
_UNINCORPORATED = re.compile(r"unincorporated", re.IGNORECASE)


@dataclass
class Manager:
    """One service manager with the rows that name it."""

    name: str
    homepage: str | None
    rows: list[Row] = field(default_factory=list)

    @property
    def is_board(self) -> bool:
        return bool(_BOARD.search(self.name))


def clean_name(text: str) -> str:
    """A municipality's name as the list writes it, in the places list's forms."""
    text = repair_mojibake(" ".join(text.split()))
    return (
        text.replace(" & ", " and ")
        .replace("Add\u2019l", "Additional")
        .replace("Add'l", "Additional")
        .replace("\u2013", "-")
    )


def read_managers(opened: OpenedFile) -> list[Manager]:
    """The managers in the order the list first names them, each with its rows."""
    managers: dict[str, Manager] = {}
    for row in opened.rows:
        cell = row["Service manager"]
        match = _ANCHOR.match(cell)
        if match is None:
            raise ListFileError(f"{LIST.name}: a service manager cell is not a link: {cell!r}")
        name = clean_name(match.group("title"))
        href = (match.group("href") or "").strip()
        manager = managers.setdefault(
            name, Manager(name=name, homepage=normalize_url(href) if href else None)
        )
        manager.rows.append(row)
    return list(managers.values())


def served_places(manager: Manager) -> tuple[ServedPlace, ...]:
    """The municipalities the board's rows name, as the places list has them, each at the
    municipal level so a town named like its district is the town."""
    names: list[str] = []
    for row in manager.rows:
        cell = " ".join(row["Municipality"].split())
        if _UNINCORPORATED.search(cell):
            continue
        fields = MEMBERS.get(cell)
        if fields is not None:
            logger.info("member: %s: %s", cell, fields["reason"])
            if fields["place"] is None:
                continue
            name = str(fields["place"])
        else:
            name = clean_name(cell)
        if name not in names:
            names.append(name)
    return tuple(ServedPlace(name=name, level=MUNICIPALITY) for name in names)


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[InstitutionEntry]:  # noqa: ARG001 - the loader's signature
    """The boards, by name."""
    managers = read_managers(files[LIST.name])
    found: list[InstitutionEntry] = []
    for manager in managers:
        if not manager.is_board:
            continue
        district = DISTRICTS.get(manager.name)
        if district is None:
            raise ListFileError(f"{LIST.name}: no district for the board {manager.name!r}")
        citation = Citation(source=LIST.name, line=manager.rows[0].line)
        found.append(
            InstitutionEntry(
                name=manager.name,
                institution_type=MUNICIPAL_CORPORATION,
                place=district,
                place_level=REGION,
                place_parent=PROVINCE,
                served_places=served_places(manager),
                homepage=manager.homepage,
                citations=(
                    {"institution": citation, "homepage": citation}
                    if manager.homepage
                    else {"institution": citation}
                ),
            )
        )
    logger.info(
        "%d service managers: %d boards loaded, %d municipalities are governments already",
        len(managers),
        len(found),
        len(managers) - len(found),
    )
    return sorted(found, key=lambda entry: name_key(entry.name))
