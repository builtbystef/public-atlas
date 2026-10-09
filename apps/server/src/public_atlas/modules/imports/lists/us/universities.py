"""The United States' public universities and colleges from IPEDS, the NCES Integrated
Postsecondary Education Data System's directory of institutions for 2024 (HD2024, 6,072 rows),
each with its IPEDS unit id in `ipeds` and its website as a candidate homepage, attached to the
county of its campus. The rules:

- A public institution (`CONTROL` 1) is kept; private non-profit and for-profit ones (2, 3) are
  left out. One closed or merged in the year (`CYACTIVE` other than 1) is left out and counted.
- The level (`ICLEVEL`) gives the type: a four-year or above institution (1) is a `university`,
  a two-year one (2) a `college`. A less-than-two-year institution (3: a technical center, an
  adult education program, a school of practical nursing, most run by a school district or a
  hospital) is left out and counted; it waits for a list that says which are bodies of their
  own.
- A system or district office (the University of California's Office of the President, a
  California community college district) is a row of the directory with the level of its
  campuses, and is loaded as one: the body that buys for the system.
- The place is the county of the campus (`COUNTYCD`) when that county is a loaded place; else
  the loaded municipality under the state the county row or the campus city names; else the
  state (`us/loaded.py`). A campus in a territory the seed does not have (American Samoa, Guam,
  the Northern Mariana Islands, the Virgin Islands, the freely associated states) is dropped and
  counted.
- The name is the directory's (`INSTNM`); its aliases (`IALIAS`, separated by bars or runs of
  spaces) are aliases, an all-capitals one an acronym; a cell that runs names together past
  the length of a name gives none.
- The website is the directory's (`WEBADDR`), cleaned (`governments.website`); most lack a
  scheme.
"""

import logging
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field

from public_atlas.modules.countries.service import CountryRules
from public_atlas.modules.graph.models import IdentifierScheme
from public_atlas.modules.imports.entries import AliasEntry, Citation, Code, Fact, InstitutionEntry
from public_atlas.modules.imports.files import Format, ListFile, OpenedFile, Row
from public_atlas.modules.imports.lists.us import governments
from public_atlas.modules.imports.lists.us.census import SUB_EST, Estimates
from public_atlas.modules.imports.lists.us.loaded import Attachment, Places

logger = logging.getLogger(__name__)

COUNTRY = "US"
DIRECTORY = ListFile(
    name="ipeds_hd2024",
    title=(
        "National Center for Education Statistics, Integrated Postsecondary Education Data "
        "System, Directory information 2024 (HD2024)"
    ),
    url="https://nces.ed.gov/ipeds/datacenter/data/HD2024.zip",
    sha256="d98425c123d7c0e872aec6e83960dfb501884818bf17385c340790f3d1f28345",
    format=Format.CSV,
    member="HD2024.csv",
    # The address, phone, chief officer and classification columns stay out of the stored text.
    columns=(
        "UNITID",
        "INSTNM",
        "IALIAS",
        "CITY",
        "STABBR",
        "FIPS",
        "WEBADDR",
        "SECTOR",
        "ICLEVEL",
        "CONTROL",
        "CYACTIVE",
        "COUNTYCD",
        "COUNTYNM",
    ),
)
SOURCES = (DIRECTORY, SUB_EST)
UNIVERSITY = "university"
COLLEGE = "college"
PUBLIC = "1"
ACTIVE = "1"
# `ICLEVEL`.
LEVELS: dict[str, str] = {"1": UNIVERSITY, "2": COLLEGE}
LESS_THAN_TWO_YEAR = "3"
_ALIAS_SEPARATOR = re.compile(r"\s*\|\s*|\s{2,}")
# What an alias may be long: `AliasEntry`'s limit.
ALIAS_LENGTH = 300
_ACRONYM = re.compile(r"^[A-Z0-9&]+$")

# Hand corrections keyed by the institution's name, each with its reason. None are needed yet.
OVERRIDES: dict[str, dict[str, str]] = {}


@dataclass
class Notes:
    """What the build typed, placed or left out, logged for the operator and pinned by the
    rule test."""

    # Loaded institutions by type.
    typed: Counter[str] = field(default_factory=Counter)
    # Institutions by the level of their place.
    placed: Counter[str] = field(default_factory=Counter)
    private: int = 0
    inactive: int = 0
    less_than_two_year: int = 0
    # Institutions in a territory the seed does not have.
    no_state: list[str] = field(default_factory=list)
    aliases: int = 0
    websites: int = 0

    def log(self) -> None:
        for institution_type, count in sorted(self.typed.items()):
            logger.info("%d institutions typed %s", count, institution_type)
        for level, count in sorted(self.placed.items()):
            logger.info("%d institutions at a %s", count, level)
        logger.info(
            "left out %d private institutions, %d closed in the year, %d less-than-two-year; "
            "%d are in a territory the seed does not have: %s",
            self.private,
            self.inactive,
            self.less_than_two_year,
            len(self.no_state),
            ", ".join(self.no_state),
        )
        logger.info("%d aliases; %d institutions have a website", self.aliases, self.websites)


def aliases_of(cell: str) -> tuple[AliasEntry, ...]:
    """The directory's aliases, one per bar or run of spaces, an all-capitals one an acronym.
    A cell that runs several names together with no separator is longer than a name can be
    and gives none."""
    found: dict[str, AliasEntry] = {}
    for piece in _ALIAS_SEPARATOR.split(cell.strip()):
        text = " ".join(piece.split())
        if text and text not in found and len(text) <= ALIAS_LENGTH:
            found[text] = AliasEntry(text=text, is_acronym=bool(_ACRONYM.match(text)))
    return tuple(found.values())


def build(
    files: Mapping[str, OpenedFile], rules: CountryRules
) -> tuple[list[InstitutionEntry], Notes]:
    """The entries and the notes of the build."""
    notes = Notes()
    places = Places(Estimates(files[SUB_EST.name]), rules.naming)
    found: list[InstitutionEntry] = []
    for row in files[DIRECTORY.name].rows:
        if row["CONTROL"] != PUBLIC:
            notes.private += 1
            continue
        if row["CYACTIVE"] != ACTIVE:
            notes.inactive += 1
            continue
        institution_type = LEVELS.get(row["ICLEVEL"])
        if institution_type is None:
            notes.less_than_two_year += 1
            continue
        name = " ".join(row["INSTNM"].split())
        place = _place(row, places)
        if place is None:
            notes.no_state.append(f"{name} ({row['STABBR']})")
            continue
        aliases = aliases_of(row["IALIAS"])
        notes.typed[institution_type] += 1
        notes.placed[place.level] += 1
        notes.aliases += len(aliases)
        homepage = governments.website(row["WEBADDR"])
        citation = Citation(source=DIRECTORY.name, line=row.line)
        citations: dict[Fact, Citation] = {"institution": citation}
        if homepage is not None:
            citations["homepage"] = citation
            notes.websites += 1
        found.append(
            InstitutionEntry(
                name=name,
                aliases=aliases,
                institution_type=institution_type,
                codes=(Code(scheme=IdentifierScheme.IPEDS, value=row["UNITID"]),),
                place=place.name,
                place_level=place.level,
                place_parent=place.parent,
                homepage=homepage,
                citations=citations,
            )
        )
    return found, notes


def _place(row: Row, places: Places) -> Attachment | None:
    """The campus's county as a loaded place, else the municipality or state (`Places.attach`);
    None for a territory the seed does not have."""
    state = row["FIPS"].zfill(2)
    county = row["COUNTYCD"]
    if not county.isdigit():
        return places.state(state)
    county = county.zfill(5)
    return places.attach(county[:2], county[2:], city=row["CITY"])


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[InstitutionEntry]:
    """Every public university and college, in the directory's order."""
    found, notes = build(files, rules)
    notes.log()
    return found
