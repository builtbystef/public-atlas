"""Canada's federal organizations from the Treasury Board of Canada Secretariat's *Inventory of
Federal Organizations and Interests* (GC InfoBase): the 277 active bodies, each under Canada
with its website as a candidate homepage, typed by the inventory's institutional structure and
placed under the department that heads its portfolio. The rules:

- Only active rows (`status` "a") are loaded; the dissolved and transferred ones (55) are
  counted. The structure (`inst_struct`) gives the type: a ministerial department is a
  `department`; a departmental, service or special operating agency, a departmental
  corporation and an agent of Parliament are an `agency`; a Crown corporation is a
  `crown_corporation`; a shared-governance corporation is an `airport_authority` or a
  `port_authority` when its name says so (21 airports, 18 ports) and a `public_authority`
  otherwise (NAV CANADA, the Seaway, CIHI, the Canada Foundation for Innovation); the House of
  Commons and the Senate are a `legislature` and the other parliamentary entities (the Library
  of Parliament, the budget officer, the ethics offices, the protective service) an `agency`;
  an international organization Canada holds an interest in, a joint enterprise and the
  inventory's "other organizations" (legal entities such as the Director of Soldier
  Settlement, without a website or a portfolio) are `other`, with the structure as the
  suggested type, so a reviewer sees them rather than the list dropping them.
- The name is the legal title; the applied title (the name the body goes by, "Agriculture and
  Agri-Food Canada" for the Department of Agriculture and Agri-Food) and the abbreviation are
  aliases, the abbreviation marked an acronym when it is one. An abbreviation two bodies share
  ("HC" is Health Canada's and the House of Commons') is given to neither, since the loader
  finds a body by any alias.
- The parent is the body that heads the row's portfolio (`min_port`): the ministerial
  department whose own portfolio it is, and a hand table where a portfolio has no ministerial
  department (the Privy Council Office, the Canada Revenue Agency, Housing, Infrastructure and
  Communities Canada) or two (Innovation, Science and Economic Development, where the
  Department of Industry heads and Prairies Economic Development Canada is a department of the
  portfolio). A head and a body of a portfolio with no head (Parliament's entities, the five
  rows with no portfolio) sit under the Government of Canada, the loader's default.
- The website is the row's, cleaned: a bare host gets its scheme, and the one row that lists
  two sites keeps the first. A domain is trusted the spec's way, by a `find_homepage`
  assignment, never by this list; the inventory's own line is the trusted link that
  assignment needs.

The file is the open dataset's resource `7c131a87-7784-4208-8e5c-043451240d95` on dataset
`a35cf382-690c-4221-a971-cf0fd189a46f`, modified 2026-10-04; a new release is one hash swap.
"""

import logging
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from public_atlas.modules.graph.service import host_of, is_domain_name, normalize_url
from public_atlas.modules.imports.entries import AliasEntry, Citation, Fact, InstitutionEntry
from public_atlas.modules.imports.files import Format, ListFile, ListFileError, OpenedFile
from public_atlas.shared.text import name_key

if TYPE_CHECKING:
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = "CA"
PLACE = "Canada"
PLACE_LEVEL = "country"
DEPARTMENT = "department"
AGENCY = "agency"
CROWN_CORPORATION = "crown_corporation"
LEGISLATURE = "legislature"
PUBLIC_AUTHORITY = "public_authority"
AIRPORT_AUTHORITY = "airport_authority"
PORT_AUTHORITY = "port_authority"
OTHER = "other"

INVENTORY = ListFile(
    name="tbs_federal_organizations",
    title=(
        "Treasury Board of Canada Secretariat, Inventory of Federal Organizations and Interests "
        "(GC InfoBase), as modified 2026-10-04"
    ),
    url=(
        "https://open.canada.ca/data/dataset/a35cf382-690c-4221-a971-cf0fd189a46f/resource/"
        "7c131a87-7784-4208-8e5c-043451240d95/download/ifoi_roif_en.csv"
    ),
    sha256="e1994383ba3b6b91389e27e64ecc95b49cfcb41e9193d8a62c81e87672341c9d",
    format=Format.CSV,
    # The descriptions, ministers, dates and notes stay out of the stored text.
    columns=(
        "org_id",
        "abbr_en",
        "legal_title",
        "applied_title",
        "min_port",
        "inst_struct",
        "status",
        "FAA_LRC_inst",
        "website",
    ),
)
SOURCES = (INVENTORY,)

ACTIVE = "a"
MINISTERIAL_DEPARTMENT = "Ministerial Departments"
SHARED_GOVERNANCE = "Shared-Governance Corporations"
PARLIAMENTARY = "Parliamentary Entities"
# The type each institutional structure takes, unless `type_of` reads the name.
TYPES: dict[str, str] = {
    MINISTERIAL_DEPARTMENT: DEPARTMENT,
    "Departmental Agencies": AGENCY,
    "Service Agencies": AGENCY,
    "Special Operating Agencies": AGENCY,
    "Departmental Corporations": AGENCY,
    "Agents Of Parliament": AGENCY,
    "Crown Corporations": CROWN_CORPORATION,
    SHARED_GOVERNANCE: PUBLIC_AUTHORITY,
    "International Organizations": OTHER,
    PARLIAMENTARY: AGENCY,
    "Joint Enterprises": OTHER,
    "Other Organizations": OTHER,
}
# The chambers of Parliament.
CHAMBERS = frozenset({"House of Commons", "Senate"})
_AIRPORT = re.compile(r"\b(airports?|aéroports?)\b", re.IGNORECASE)
_PORT = re.compile(r"\bport authority\b", re.IGNORECASE)


def type_of(structure: str, legal_title: str) -> str:
    """The type the structure gives, read with the name for the two structures that hold
    several kinds: a shared-governance corporation named for an airport or a port runs one, and
    a parliamentary entity is a chamber or an office that serves the chambers."""
    if structure == SHARED_GOVERNANCE:
        if _AIRPORT.search(legal_title):
            return AIRPORT_AUTHORITY
        if _PORT.search(legal_title):
            return PORT_AUTHORITY
    elif structure == PARLIAMENTARY and legal_title in CHAMBERS:
        return LEGISLATURE
    return TYPES[structure]


# The body heading a portfolio that no ministerial department's own portfolio names, or that
# two name, by the portfolio as the inventory writes it; None where the portfolio has no head.
PORTFOLIO_HEADS: dict[str, str | None] = {
    "Innovation, Science and Economic Development": "Department of Industry",
    "Infrastructure and Communities": "Department of Housing, Infrastructure and Communities",
    "National Revenue": "Canada Revenue Agency",
    "Privy Council": "Privy Council Office",
    "Office of the Governor General's Secretary": "Office of the Governor General's Secretary",
    "Parliament": None,
    "": None,
}
# Between two sites in one website cell.
WEBSITE_SEPARATOR = "*,*"
_ACRONYM = re.compile(r"^[A-Z0-9&]+$")

# Hand corrections keyed by the body's legal title, each with its reason. None are needed yet.
OVERRIDES: dict[str, dict[str, str]] = {}


@dataclass(frozen=True, slots=True)
class Organization:
    """One row of the inventory, with the line of the text it is."""

    id: str
    legal_title: str
    applied_title: str | None
    abbreviation: str | None
    portfolio: str
    structure: str
    status: str
    website: str | None
    line: int


def website(cell: str) -> str | None:
    """The first site the cell names as a URL, or None when it names none."""
    first = cell.split(WEBSITE_SEPARATOR, maxsplit=1)[0].strip()
    if not first or " " in first or "." not in first:
        return None
    try:
        url = normalize_url(first)
    except ValueError:
        return None
    return url if is_domain_name(host_of(url)) else None


def read_organizations(opened: OpenedFile) -> list[Organization]:
    """The rows that name a body; the file ends in a blank row."""
    return [
        Organization(
            id=row["org_id"],
            legal_title=" ".join(row["legal_title"].split()),
            applied_title=" ".join(row["applied_title"].split()) or None,
            abbreviation=" ".join(row["abbr_en"].split()) or None,
            portfolio=" ".join(row["min_port"].split()),
            structure=row["inst_struct"],
            status=row["status"],
            website=website(row["website"]),
            line=row.line,
        )
        for row in opened.rows
        if row["legal_title"]
    ]


def portfolio_heads(active: list[Organization]) -> dict[str, str | None]:
    """The legal title of the body heading each portfolio the active rows name: the one
    ministerial department of the portfolio, else the hand table's."""
    departments: dict[str, list[str]] = {}
    for organization in active:
        if organization.structure == MINISTERIAL_DEPARTMENT:
            departments.setdefault(organization.portfolio, []).append(organization.legal_title)
    heads: dict[str, str | None] = {}
    for portfolio in {organization.portfolio for organization in active}:
        if portfolio in PORTFOLIO_HEADS:
            heads[portfolio] = PORTFOLIO_HEADS[portfolio]
        elif len(departments.get(portfolio, [])) == 1:
            heads[portfolio] = departments[portfolio][0]
        else:
            count = len(departments.get(portfolio, []))
            raise ListFileError(
                f"{INVENTORY.name}: portfolio {portfolio!r} has {count} ministerial departments "
                "and no entry in PORTFOLIO_HEADS"
            )
    titles = {organization.legal_title for organization in active}
    for portfolio, head in heads.items():
        if head is not None and head not in titles:
            raise ListFileError(
                f"{INVENTORY.name}: the head of portfolio {portfolio!r}, {head!r}, is not an "
                "active row"
            )
    return heads


@dataclass
class Notes:
    """What the build typed, named and left out, logged for the operator and pinned by the
    rule test."""

    typed: Counter[str] = field(default_factory=Counter)
    # Active rows by structure.
    structures: Counter[str] = field(default_factory=Counter)
    # Rows left out by status.
    inactive: Counter[str] = field(default_factory=Counter)
    # The heads of the portfolios, by portfolio.
    heads: dict[str, str | None] = field(default_factory=dict)
    # Abbreviations two bodies share, given to neither.
    shared_abbreviations: list[str] = field(default_factory=list)
    with_parent: int = 0
    websites: int = 0

    def log(self) -> None:
        for type_, count in sorted(self.typed.items()):
            logger.info("%d bodies typed %s", count, type_)
        for structure, count in sorted(self.structures.items()):
            logger.info("%d active bodies are %s", count, structure)
        for status, count in sorted(self.inactive.items()):
            logger.info("left out %d bodies with status %r", count, status)
        for portfolio, head in sorted(self.heads.items()):
            logger.info("portfolio %r is headed by %s", portfolio, head or "no body")
        logger.info(
            "%d abbreviations shared by two bodies and given to neither: %s",
            len(self.shared_abbreviations),
            ", ".join(self.shared_abbreviations),
        )
        logger.info(
            "%d bodies sit under a parent; %d have a website", self.with_parent, self.websites
        )


def build(
    files: Mapping[str, OpenedFile], rules: CountryRules
) -> tuple[list[InstitutionEntry], Notes]:
    """The entries, the portfolios' heads first, and the notes of the build."""
    del rules
    notes = Notes()
    organizations = read_organizations(files[INVENTORY.name])
    active = [organization for organization in organizations if organization.status == ACTIVE]
    notes.inactive = Counter(
        organization.status for organization in organizations if organization.status != ACTIVE
    )
    heads = portfolio_heads(active)
    notes.heads = heads
    head_titles = {head for head in heads.values() if head is not None}
    abbreviations = Counter(
        organization.abbreviation for organization in active if organization.abbreviation
    )
    notes.shared_abbreviations = sorted(
        abbreviation for abbreviation, count in abbreviations.items() if count > 1
    )

    found: list[InstitutionEntry] = []
    for organization in active:
        if organization.structure not in TYPES:
            raise ListFileError(
                f"{INVENTORY.name}: {organization.legal_title!r} has an unknown structure "
                f"{organization.structure!r}"
            )
        institution_type = type_of(organization.structure, organization.legal_title)
        notes.typed[institution_type] += 1
        notes.structures[organization.structure] += 1
        aliases: list[AliasEntry] = []
        if organization.applied_title and organization.applied_title != organization.legal_title:
            aliases.append(AliasEntry(text=organization.applied_title))
        if organization.abbreviation and abbreviations[organization.abbreviation] == 1:
            aliases.append(
                AliasEntry(
                    text=organization.abbreviation,
                    is_acronym=bool(_ACRONYM.match(organization.abbreviation)),
                )
            )
        parent = heads[organization.portfolio]
        if parent == organization.legal_title:
            parent = None
        if parent is not None:
            notes.with_parent += 1
        citation = Citation(source=INVENTORY.name, line=organization.line)
        citations: dict[Fact, Citation] = {"institution": citation}
        if organization.website is not None:
            citations["homepage"] = citation
            notes.websites += 1
        found.append(
            InstitutionEntry(
                name=organization.legal_title,
                aliases=tuple(aliases),
                institution_type=institution_type,
                suggested_type=organization.structure if institution_type == OTHER else None,
                place=PLACE,
                place_level=PLACE_LEVEL,
                parent_institution=parent,
                homepage=organization.website,
                citations=citations,
            )
        )
    # The loader finds a parent by name among the bodies already at the place.
    return sorted(
        found, key=lambda entry: (entry.name not in head_titles, name_key(entry.name))
    ), notes


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[InstitutionEntry]:
    """Every active body, the portfolios' heads first."""
    found, notes = build(files, rules)
    notes.log()
    return found
