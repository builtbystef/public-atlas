"""The United States' school districts from the NCES Common Core of Data's directory of local
education agencies for 2023-24 (19,637 rows), each a `school_board` with its NCES id in `nces`
and its website as a candidate homepage, attached to the county of its office from the EDGE
geocodes NCES publishes with the directory; the city of the office is a served place where it
is one loaded municipality under that county. The rules:

- The agency type (`LEA_TYPE`) says what a row is. Regular districts (1) and the component
  districts of a supervisory union (2) are school boards. An independent charter district (7)
  is a school board that carries the file's words for its kind as an alias, since the type
  cannot say it. A service agency (4: an intermediate unit, a board of cooperative educational
  services, an education service district) is an `education_service_agency`. Supervisory
  unions (3), state and federal operated agencies
  (5, 6), other agencies (8) and specialized districts (9) are left out and counted.
- A row closed, inactive or yet to open (`SY_STATUS` 2, 6, 7) is left out.
- The place is the county of the location address when that county is a loaded place; else
  the loaded municipality under the state the county row or the address city names; else the
  state (`us/loaded.py`). An agency whose office is in another state (`OUT_OF_STATE_FLAG`) sits
  under the state whose system it belongs to. One in a territory the seed does not have (American
  Samoa, Guam, the Northern Mariana Islands, the Virgin Islands) is dropped and counted.
- The name is the file's (`LEA_NAME`): Alabama's "Albertville City" and "Marshall County" are
  the agencies' names as the state reports them.
- The website is the row's, cleaned (`governments.website`).
"""

import logging
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field

from public_atlas.modules.countries.service import CountryRules
from public_atlas.modules.graph.models import IdentifierScheme
from public_atlas.modules.imports.entries import (
    AliasEntry,
    Citation,
    Code,
    Fact,
    InstitutionEntry,
    ServedPlace,
)
from public_atlas.modules.imports.files import Format, ListFile, OpenedFile, Row
from public_atlas.modules.imports.lists.us import governments
from public_atlas.modules.imports.lists.us.census import (
    COUNTY_LEVEL,
    STATE_CODES,
    SUB_EST,
    Estimates,
)
from public_atlas.modules.imports.lists.us.loaded import Attachment, Places

logger = logging.getLogger(__name__)

COUNTRY = "US"
DIRECTORY = ListFile(
    name="nces_ccd_lea_directory_2023_24",
    title=(
        "National Center for Education Statistics, Common Core of Data, Local Education Agency "
        "Universe Survey Directory 2023-24 (ccd_lea_029_2324_w_1a_073124)"
    ),
    url="https://nces.ed.gov/ccd/Data/zip/ccd_lea_029_2324_w_1a_073124.zip",
    sha256="f6b87458dbffc68bf94ac2633f8b4b6dcaa68171912aed77d828d18e5581d6e8",
    format=Format.CSV,
    member="ccd_lea_029_2324_w_1a_073124.csv",
    # The address, phone and grade columns stay out of the stored text.
    columns=(
        "LEAID",
        "LEA_NAME",
        "ST",
        "LCITY",
        "LSTATE",
        "WEBSITE",
        "SY_STATUS",
        "SY_STATUS_TEXT",
        "LEA_TYPE",
        "LEA_TYPE_TEXT",
        "OUT_OF_STATE_FLAG",
    ),
)
GEOCODES = ListFile(
    name="nces_edge_lea_geocodes_2023_24",
    title=(
        "National Center for Education Statistics, EDGE geocodes of public local education "
        "agencies 2023-24 (EDGE_GEOCODE_PUBLICLEA_2324)"
    ),
    url="https://nces.ed.gov/programs/edge/data/EDGE_GEOCODE_PUBLICLEA_2324.zip",
    sha256="8d7dab23af01ea6ea3d005ce13748ddd1cb7a99c407f62297b042d1d4b710082",
    format=Format.SPREADSHEET,
    member="EDGE_GEOCODE_PUBLICLEA_2324/EDGE_GEOCODE_PUBLICLEA_2324.xlsx",
    columns=("LEAID", "NAME", "CITY", "STATE", "CNTY", "NMCNTY"),
)
SOURCES = (DIRECTORY, GEOCODES, SUB_EST)
SCHOOL_BOARD = "school_board"
EDUCATION_SERVICE_AGENCY = "education_service_agency"
# `LEA_TYPE`.
REGULAR = "1"
COMPONENT = "2"
SERVICE_AGENCY = "4"
CHARTER = "7"
# `SY_STATUS`: closed, inactive, future.
NOT_OPERATING = frozenset({"2", "6", "7"})
OUT_OF_STATE = "Yes"

# Hand corrections keyed by the agency's name, each with its reason. None are needed yet.
OVERRIDES: dict[str, dict[str, str]] = {}


@dataclass
class Notes:
    """What the build typed, placed or left out, logged for the operator and pinned by the
    rule test."""

    # Loaded agencies by type and kind.
    typed: Counter[str] = field(default_factory=Counter)
    # Rows left out by their agency type.
    left_out: Counter[str] = field(default_factory=Counter)
    # Rows left out by their status.
    not_operating: Counter[str] = field(default_factory=Counter)
    # Agencies by the level of their place.
    placed: Counter[str] = field(default_factory=Counter)
    out_of_state: int = 0
    no_geocode: int = 0
    # Agencies in a territory the seed does not have.
    no_state: list[str] = field(default_factory=list)
    served: int = 0
    websites: int = 0

    def log(self) -> None:
        for kind, count in sorted(self.typed.items()):
            logger.info("%d %s", count, kind)
        for kind, count in sorted(self.left_out.items()):
            logger.info("left out %d rows: %s", count, kind)
        for status, count in sorted(self.not_operating.items()):
            logger.info("left out %d rows: %s", count, status)
        for level, count in sorted(self.placed.items()):
            logger.info("%d agencies at a %s", count, level)
        logger.info(
            "%d agencies with an office in another state sit under their own state; %d have no "
            "geocode; %d are in a territory the seed does not have: %s",
            self.out_of_state,
            self.no_geocode,
            len(self.no_state),
            ", ".join(self.no_state),
        )
        logger.info(
            "%d agencies serve the city of their office; %d have a website",
            self.served,
            self.websites,
        )


def _kind(row: Row) -> tuple[str, str | None, tuple[AliasEntry, ...]] | None:
    """The type, suggested type and marking aliases of a row, or None for a row left out."""
    lea_type = row["LEA_TYPE"]
    if lea_type in (REGULAR, COMPONENT):
        return SCHOOL_BOARD, None, ()
    if lea_type == CHARTER:
        return SCHOOL_BOARD, None, (AliasEntry(text=row["LEA_TYPE_TEXT"]),)
    if lea_type == SERVICE_AGENCY:
        return EDUCATION_SERVICE_AGENCY, None, ()
    return None


def build(
    files: Mapping[str, OpenedFile], rules: CountryRules
) -> tuple[list[InstitutionEntry], Notes]:
    """The entries and the notes of the build."""
    notes = Notes()
    places = Places(Estimates(files[SUB_EST.name]), rules.naming)
    geocodes = {row["LEAID"]: row for row in files[GEOCODES.name].rows}
    found: list[InstitutionEntry] = []
    for row in files[DIRECTORY.name].rows:
        if row["SY_STATUS"] in NOT_OPERATING:
            notes.not_operating[row["SY_STATUS_TEXT"]] += 1
            continue
        kind = _kind(row)
        if kind is None:
            notes.left_out[row["LEA_TYPE_TEXT"]] += 1
            continue
        institution_type, suggested_type, aliases = kind
        name = " ".join(row["LEA_NAME"].split())
        place, served = _place(row, geocodes.get(row["LEAID"]), places, notes)
        if place is None:
            notes.no_state.append(f"{name} ({row['ST']})")
            continue
        notes.typed[f"{institution_type}: {row['LEA_TYPE_TEXT']}"] += 1
        notes.placed[place.level] += 1
        if served is not None:
            notes.served += 1
        homepage = governments.website(row["WEBSITE"])
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
                suggested_type=suggested_type,
                codes=(Code(scheme=IdentifierScheme.NCES, value=row["LEAID"]),),
                place=place.name,
                place_level=place.level,
                place_parent=place.parent,
                served_places=(
                    ServedPlace(name=served.name, level=served.level, parent=served.parent),
                )
                if served is not None
                else (),
                homepage=homepage,
                citations=citations,
            )
        )
    return found, notes


def _place(
    row: Row, geocode: Row | None, places: Places, notes: Notes
) -> tuple[Attachment | None, Attachment | None]:
    """The agency's place and, when the place is its county, the municipality of its office
    as a served place."""
    state = STATE_CODES.get(row["ST"], "")
    if row["OUT_OF_STATE_FLAG"] == OUT_OF_STATE or row["LSTATE"] != row["ST"]:
        notes.out_of_state += 1
        return places.state(state), None
    if geocode is None:
        notes.no_geocode += 1
        return places.state(state), None
    county = geocode["CNTY"].zfill(5)
    place = places.attach(county[:2], county[2:], city=row["LCITY"])
    served = None
    if place is not None and place.level == COUNTY_LEVEL:
        served = places.municipality(county[:2], county[2:], row["LCITY"])
    return place, served


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[InstitutionEntry]:
    """Every agency, in the file's order."""
    found, notes = build(files, rules)
    notes.log()
    return found
