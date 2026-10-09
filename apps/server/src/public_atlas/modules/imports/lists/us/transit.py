"""The United States' public transit agencies from the Federal Transit Administration's
National Transit Database, the 2024 agency information file (2,914 reporters), each a
`transit_agency` with its website as a candidate homepage, attached to the government it is a
department of, else to the city of its address. The rules:

- A reporter is kept when its organization type is public: a city, county or local government
  unit or department of transportation; an independent public agency or authority; a state
  government unit or department of transportation. Private corporations, non-profits, tribes,
  planning agencies, area agencies on aging, universities and the rest are left out and counted
  by type.
- A reporter of the asset module (a reduced asset reporter, a group plan sponsor, a building
  reporter: a village with a few vans bought through a regional authority, or that authority
  reporting its sponsored fleet) is left out and counted: it is not a transit body, or it is
  one that the urban or rural module lists under its own id.
- The file lists services, not bodies: one body reports several services as rows of one agency
  name with a division or a trade name each (Los Angeles County's eleven Public Works transit
  operations, Regional Transit Service's eight county divisions), so the rows of one agency
  name in one state are one body. The body's name is the agency name when the agency is a body
  of its own (an authority, a district, a commission), with its trade names ("Doing Business
  As") as aliases. When the agency name is a loaded government's ("City of Owensboro",
  "Montezuma County"), the body is the transit service the government runs, which goes by its
  trade name ("Owensboro Transit Systems", "MoCo Public Transportation") or, failing one, by
  its division's name when that says it is a transit service ("Natchez Transit System", "Dial A
  Bus"), composed with the government's name when it does not name the place ("Town of
  Wallkill Dial A Bus"). A government is known by the place name inside the agency name and
  its designator, with a trailing state or body name taken off ("Forsyth County Board of
  Commissioners", "City of Springfield, Ohio"), as the .gov registry's names are read. A
  government that runs a service under no name of its own ("City of Seneca", division "Public
  Works") has a department, not a body (the eval dataset's scope rule 3), and is left out and
  counted.
- The place: a state unit sits under its state; a government's service under that government's
  place (the county or the municipality the agency name names); any other body under the
  loaded municipality in its state that its city names, when one does, else under the state.
  Where the loader could not tell the municipality from another of its name (the city and the
  charter township of Grand Rapids, both under Kent County; the City of Jackson under Madison
  County, Tennessee, and the Township of Jackson under Madison County, Indiana, which the
  loader reads alike), the county stands in. A reporter in a territory the seed does not have
  (American Samoa, Guam, the Northern Mariana Islands, the Virgin Islands) is dropped and
  counted. Puerto Rico's municipios are not in the index the lists share, so its reporters sit
  under Puerto Rico.
- The National Transit Database id has no identifier scheme, so a body carries no code and
  the loader finds it by name at its place: a transit district the Census of Governments
  listed (`us/special_districts`) joins its row when the two names agree at one place, and is
  a second row when they do not.
- The website is the row's, cleaned (`governments.website`); a few lack a scheme.

The file is obtained by hand: the open data platform's CSV export is the same rows in a
different order from one request to the next, so no hash can be pinned (lists-todo, "Sources
to fetch by hand"). The module's instructions say how to export it and where it goes.
"""

import logging
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field

from public_atlas.modules.countries.service import CountryRules
from public_atlas.modules.imports.entries import AliasEntry, Citation, Fact, InstitutionEntry
from public_atlas.modules.imports.files import Format, ListFile, OpenedFile
from public_atlas.modules.imports.lists.us import governments
from public_atlas.modules.imports.lists.us.census import STATE_CODES, SUB_EST, Estimates
from public_atlas.modules.imports.lists.us.loaded import Attachment, Places
from public_atlas.modules.imports.models import Retrieval

logger = logging.getLogger(__name__)

COUNTRY = "US"
AGENCIES = ListFile(
    name="ntd_agency_information_2024",
    title=(
        "Federal Transit Administration, National Transit Database, 2024 Annual Database "
        "Agency Information (data.transportation.gov dataset ccvf-fykn), exported 2026-10-09"
    ),
    url="https://data.transportation.gov/Public-Transit/2024-Annual-Database-Agency-Information/ccvf-fykn",
    format=Format.CSV,
    retrieval=Retrieval.MANUAL,
    # The export is not the same bytes twice: the platform (Socrata) orders the rows as it
    # pleases on each request (the same 2,914 rows, two orders seen on 2026-10-09), so no hash
    # can be pinned; the file is kept as a person exported it.
    instructions=(
        "Open the dataset page, choose Export, then CSV (the download URL is "
        "https://data.transportation.gov/api/views/ccvf-fykn/rows.csv?accessType=DOWNLOAD), "
        "and save the file as ntd_agency_information_2024.csv. Expect 2,914 rows (one per "
        "reporter) with the columns NTD ID, State/Parent NTD ID, Agency Name, "
        "Division/Department, Doing Business As, Reporter Type, Reporting Module, Organization "
        "Type, ..., City, State, ..., URL. The platform orders the rows differently from one "
        "export to the next; any order will do."
    ),
    min_rows=2900,
    filename_override="ntd_agency_information_2024.csv",
    # The address, due dates, fleet and service area columns stay out of the stored text.
    columns=(
        "NTD ID",
        "Agency Name",
        "Division/Department",
        "Doing Business As",
        "Reporter Type",
        "Reporting Module",
        "Organization Type",
        "Reported by Name",
        "City",
        "State",
        "URL",
    ),
)
SOURCES = (AGENCIES, SUB_EST)
TRANSIT_AGENCY = "transit_agency"
LOCAL_GOVERNMENT = "City, County or Local Government Unit or Department of Transportation"
INDEPENDENT = "Independent Public Agency or Authority of Transit Service"
STATE_GOVERNMENT = "State Government Unit or Department of Transportation"
PUBLIC_TYPES = frozenset({LOCAL_GOVERNMENT, INDEPENDENT, STATE_GOVERNMENT})
ASSET_MODULE = "Asset"
# A division's name that says it is a transit service.
_TRANSIT_WORDS = re.compile(
    r"\b(transit|transportation|bus|ride|dial|van|mobility|metro|trolley|shuttle|rail|ferry|"
    r"cab|taxi|paratransit|coach|link|express|streetcar|handivan|lift)\b",
    re.IGNORECASE,
)

# Hand corrections keyed by the body's name, each with its reason. None are needed yet.
OVERRIDES: dict[str, dict[str, str]] = {}


@dataclass
class Notes:
    """What the build kept, named, placed or left out, logged for the operator and pinned by
    the rule test."""

    # Rows left out by their organization type.
    left_out: Counter[str] = field(default_factory=Counter)
    asset_module: int = 0
    # Rows in a territory the seed does not have.
    no_state: int = 0
    # Rows of one agency folded into a body already made.
    folded: int = 0
    # Bodies by how they were named.
    named: Counter[str] = field(default_factory=Counter)
    # A government's services with no name of their own.
    no_name: list[str] = field(default_factory=list)
    # Bodies by the level of their place and how it was found.
    placed: Counter[str] = field(default_factory=Counter)
    aliases: int = 0
    websites: int = 0

    def log(self) -> None:
        for kind, count in sorted(self.left_out.items()):
            logger.info("left out %d rows: %s", count, kind or "no organization type")
        logger.info(
            "left out %d rows of the asset module and %d in a territory the seed does not have; "
            "%d rows folded into a body already made",
            self.asset_module,
            self.no_state,
            self.folded,
        )
        for how, count in sorted(self.named.items()):
            logger.info("%d bodies named by %s", count, how)
        logger.info(
            "left out %d services a government runs under no name of their own: %s",
            len(self.no_name),
            ", ".join(self.no_name),
        )
        for how, count in sorted(self.placed.items()):
            logger.info("%d bodies at %s", count, how)
        logger.info("%d aliases; %d bodies have a website", self.aliases, self.websites)


@dataclass(frozen=True, slots=True)
class Reporter:
    """One row of the file."""

    ntd_id: str
    agency: str
    division: str
    trade_name: str
    organization_type: str
    module: str
    city: str
    state: str
    website: str | None
    line: int


def read_reporters(opened: OpenedFile) -> list[Reporter]:
    return [
        Reporter(
            ntd_id=row["NTD ID"],
            agency=_recased(row["Agency Name"]),
            division=" ".join(row["Division/Department"].split()),
            trade_name=" ".join(row["Doing Business As"].split()),
            organization_type=row["Organization Type"],
            module=row["Reporting Module"],
            city=_recased(row["City"]),
            state=row["State"],
            website=governments.website(row["URL"]),
            line=row.line,
        )
        for row in opened.rows
    ]


def _recased(text: str) -> str:
    """A name written in capitals as a page would write it; any other as given."""
    text = " ".join(text.split())
    return governments.title_case(text) if text.isupper() else text


@dataclass(frozen=True, slots=True)
class Body:
    """A transit body as the rows of one agency name describe it."""

    name: str
    place: Attachment
    # How the place was found, for the notes.
    placed: str
    # The row that names the body, cited for it.
    named_by: Reporter
    aliases: tuple[AliasEntry, ...]
    # The first row with a website, cited for it.
    website_row: Reporter | None


def service_name(reporter: Reporter, government: Attachment) -> str | None:
    """The name a government's service goes by in a row without a trade name: its division's
    name when that says it is a transit service, composed with the government's name when it
    does not name the place; None when the row gives the service no name of its own."""
    division = reporter.division
    if not division or not _TRANSIT_WORDS.search(division):
        return None
    if government.name.lower() in division.lower() or reporter.agency.lower() in division.lower():
        return division
    return f"{reporter.agency} {division}"


def _trade_names(rows: list[Reporter], name: str) -> tuple[AliasEntry, ...]:
    found: dict[str, AliasEntry] = {}
    for row in rows:
        if row.trade_name and row.trade_name != name:
            found.setdefault(row.trade_name, AliasEntry(text=row.trade_name))
    return tuple(found.values())


def _body(rows: list[Reporter], places: Places, state: str, notes: Notes) -> Body | None:
    """The body the rows of one agency name describe, named and placed by the rules; None for
    a government's service with no name of its own."""
    first = rows[0]
    website_row = next((row for row in rows if row.website is not None), None)
    state_place = places.state(state)
    assert state_place is not None  # noqa: S101 - the caller checked
    if first.organization_type == STATE_GOVERNMENT:
        notes.named["the agency name"] += 1
        return Body(
            first.agency,
            state_place,
            "the state: a state unit",
            first,
            _trade_names(rows, first.agency),
            website_row,
        )
    government = places.government(state, first.agency)
    if government is not None:
        named_by = next((row for row in rows if row.trade_name), None)
        if named_by is not None:
            notes.named["the trade name of a government's service"] += 1
            name = named_by.trade_name
        else:
            names = [(row, service_name(row, government)) for row in rows]
            named_by, name = next(((row, name) for row, name in names if name), (None, None))
            if named_by is None or name is None:
                notes.no_name.append(f"{first.agency} ({first.state})")
                return None
            notes.named["the division of a government's service"] += 1
        placed = "a government's place"
        if government.instead_of is not None:
            placed = "the county of a government whose place shares its name"
        return Body(name, government, placed, named_by, (), website_row)
    notes.named["the agency name"] += 1
    city = places.city(state, first.city)
    if city is not None:
        placed = "the city of its address"
        if city.instead_of is not None:
            placed = "the county of its city, which shares its name"
        return Body(
            first.agency, city, placed, first, _trade_names(rows, first.agency), website_row
        )
    return Body(
        first.agency,
        state_place,
        "the state: its city is no one place",
        first,
        _trade_names(rows, first.agency),
        website_row,
    )


def build(
    files: Mapping[str, OpenedFile], rules: CountryRules
) -> tuple[list[InstitutionEntry], Notes]:
    """The entries and the notes of the build."""
    notes = Notes()
    places = Places(Estimates(files[SUB_EST.name]), rules.naming)
    groups: dict[tuple[str, str], list[Reporter]] = {}
    for reporter in read_reporters(files[AGENCIES.name]):
        if reporter.organization_type not in PUBLIC_TYPES:
            notes.left_out[reporter.organization_type] += 1
            continue
        if reporter.module == ASSET_MODULE:
            notes.asset_module += 1
            continue
        if STATE_CODES.get(reporter.state, "") not in places.states:
            notes.no_state += 1
            continue
        rows = groups.setdefault((reporter.agency, reporter.state), [])
        if rows:
            notes.folded += 1
        rows.append(reporter)

    found: list[InstitutionEntry] = []
    for (_, state_code), rows in groups.items():
        body = _body(rows, places, STATE_CODES[state_code], notes)
        if body is None:
            continue
        notes.placed[body.placed] += 1
        notes.aliases += len(body.aliases)
        citations: dict[Fact, Citation] = {
            "institution": Citation(source=AGENCIES.name, line=body.named_by.line)
        }
        website = None
        if body.website_row is not None:
            website = body.website_row.website
            citations["homepage"] = Citation(source=AGENCIES.name, line=body.website_row.line)
            notes.websites += 1
        found.append(
            InstitutionEntry(
                name=body.name,
                aliases=body.aliases,
                institution_type=TRANSIT_AGENCY,
                place=body.place.name,
                place_level=body.place.level,
                place_parent=body.place.parent,
                homepage=website,
                citations=citations,
            )
        )
    return found, notes


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[InstitutionEntry]:
    """Every public transit body, in the file's order of first appearance."""
    found, notes = build(files, rules)
    notes.log()
    return found
