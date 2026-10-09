"""The United States' federal departments and agencies from the Federal Register's list of
agencies (473), kept to the bodies alive today, each under the United States with its website
as a candidate homepage: the fifteen cabinet departments as `department`, everything else (the
military departments, the bureaus, offices, services and administrations inside a department,
the independent agencies, boards and commissions) as `agency`, each under the body the list
names as its parent. The rules:

- The list carries every body that ever published in the Federal Register, defunct ones
  included (the Interstate Commerce Commission, the Resolution Trust Corporation, the
  commissions of the 1990s). A body is kept when it published a document in the three years
  2023 to 2025 (the Federal Register's count of documents per agency over that window, a second
  file) or when its website's domain is registered to it by name in the .gov registry's list of
  federal domains (the Architect of the Capitol, the Congressional Budget Office, the Delta
  Regional Authority: live bodies that publish nothing). A kept body's parents are kept with it.
  The rest are left out and counted.
- The list writes a department's name inverted ("Agriculture Department"); the fifteen cabinet
  departments, the three military departments and the three offices the list inverts around a
  comma ("Procurement and Property Management, Office of") take their official names from a
  hand table, with the list's form as an alias. Any other name is the list's. The short name
  is an alias, marked an acronym when it is one, unless two kept bodies share it ("FS" is the
  Fiscal Service's and the Forest Service's; "LOC" the Library of Congress's and the Copyright
  Royalty Board's), since the loader would read the second body as the first.
- The parent is the list's (`parent_id`): a bureau under its department, a few offices under a
  bureau. A body with no parent sits under the Government of the United States, the loader's
  default.
- The website is the list's `agency_url`, cleaned (`governments.website`), a candidate homepage
  like any other list's. The .gov registry's federal domains (`current-federal.csv`, pinned at a
  commit since the file changes daily) say which body holds each domain; the loader stores the
  file as a snapshot on a trusted host, so a registry line that names the body and its domain
  is the linking evidence its `find_homepage` assignment needs (spec section 6.3). The domain is
  trusted the spec's way, by that assignment, never by this list: the bodies whose website sits
  on a registered domain are counted in the notes.
"""

import logging
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from public_atlas.modules.countries.service import CountryRules
from public_atlas.modules.graph.service import host_of
from public_atlas.modules.imports.entries import AliasEntry, Citation, Fact, InstitutionEntry
from public_atlas.modules.imports.files import Format, ListFile, OpenedFile
from public_atlas.modules.imports.lists.us import governments

logger = logging.getLogger(__name__)

COUNTRY = "US"
PLACE = "United States"
PLACE_LEVEL = "country"
DEPARTMENT = "department"
AGENCY = "agency"

AGENCIES = ListFile(
    name="federal_register_agencies",
    title="Office of the Federal Register, the Federal Register API's list of agencies",
    url="https://www.federalregister.gov/api/v1/agencies.json",
    sha256="7a806d209d75ee543e6e91506e485ec6a8f42687056e14a1484c8bc9e79f5443",
    format=Format.JSON,
)
# The window a body must have published in; closed, so the counts hold still.
DOCUMENTS_FROM = "2023-01-01"
DOCUMENTS_TO = "2025-12-31"
DOCUMENTS = ListFile(
    name="federal_register_documents_2023_2025",
    title=(
        "Office of the Federal Register, the Federal Register API's count of documents per "
        "agency published from 2023-01-01 to 2025-12-31"
    ),
    url=(
        "https://www.federalregister.gov/api/v1/documents/facets/agency"
        f"?conditions[publication_date][gte]={DOCUMENTS_FROM}"
        f"&conditions[publication_date][lte]={DOCUMENTS_TO}"
    ),
    sha256="96b9b2e0a571d8fab8d1235d04efb883ae9015c4057a7d57b3e198eaa362200b",
    format=Format.JSON,
    filename_override="documents_per_agency_2023_2025.json",
)
DOTGOV_FEDERAL = ListFile(
    name="dotgov_federal_registry_2026_10_09",
    title=(
        "Cybersecurity and Infrastructure Security Agency, the .gov registry's list of federal "
        "domains (current-federal.csv), as of 2026-10-09"
    ),
    url=(
        "https://raw.githubusercontent.com/cisagov/dotgov-data/"
        "b4cb1970319c9621bb09e50da7cd6538610516a6/current-federal.csv"
    ),
    sha256="f8fd8cd9e24ecf373605bec61c165e56f2dd99ffc5cd35b7069bb1cca4364152",
    format=Format.CSV,
    columns=("Domain name", "Domain type", "Organization name"),
)
SOURCES = (AGENCIES, DOCUMENTS, DOTGOV_FEDERAL)

# The cabinet departments, by the list's inverted name.
CABINET: dict[str, str] = {
    "Agriculture Department": "Department of Agriculture",
    "Commerce Department": "Department of Commerce",
    "Defense Department": "Department of Defense",
    "Education Department": "Department of Education",
    "Energy Department": "Department of Energy",
    "Health and Human Services Department": "Department of Health and Human Services",
    "Homeland Security Department": "Department of Homeland Security",
    "Housing and Urban Development Department": "Department of Housing and Urban Development",
    "Interior Department": "Department of the Interior",
    "Justice Department": "Department of Justice",
    "Labor Department": "Department of Labor",
    "State Department": "Department of State",
    "Transportation Department": "Department of Transportation",
    "Treasury Department": "Department of the Treasury",
    "Veterans Affairs Department": "Department of Veterans Affairs",
}
# The military departments inside the Department of Defense: departments by name, agencies here.
MILITARY: dict[str, str] = {
    "Air Force Department": "Department of the Air Force",
    "Army Department": "Department of the Army",
    "Navy Department": "Department of the Navy",
}
# The offices the list names inverted around a comma.
INVERTED: dict[str, str] = {
    "National Intelligence, Office of the National Director": (
        "Office of the Director of National Intelligence"
    ),
    "Procurement and Property Management, Office of": (
        "Office of Procurement and Property Management"
    ),
    "Trade Representative, Office of United States": (
        "Office of the United States Trade Representative"
    ),
}
OFFICIAL_NAMES: dict[str, str] = {**CABINET, **MILITARY, **INVERTED}
_ACRONYM = re.compile(r"^[A-Z0-9&]+$")

# Hand corrections keyed by the body's name, each with its reason. None are needed yet.
OVERRIDES: dict[str, dict[str, str]] = {}


@dataclass
class Notes:
    """What the build kept, named and left out, logged for the operator and pinned by the rule
    test."""

    # Kept bodies by type.
    typed: Counter[str] = field(default_factory=Counter)
    # How each kept body earned its place.
    kept_by: Counter[str] = field(default_factory=Counter)
    # Bodies left out: no documents in the window, no domain of their own.
    left_out: list[str] = field(default_factory=list)
    # Bodies given their official name from the hand tables.
    official_names: int = 0
    # Short names two kept bodies share, given to neither.
    shared_short_names: list[str] = field(default_factory=list)
    with_parent: int = 0
    websites: int = 0
    # Kept bodies whose website sits on a domain the .gov registry lists as federal, with the
    # domain: the registry line is the linking evidence for their homepage assignments.
    registered: list[tuple[str, str]] = field(default_factory=list)

    def log(self) -> None:
        for institution_type, count in sorted(self.typed.items()):
            logger.info("%d bodies typed %s", count, institution_type)
        for reason, count in sorted(self.kept_by.items()):
            logger.info("%d bodies kept: %s", count, reason)
        logger.info(
            "left out %d bodies with no documents from %s to %s and no registered domain of "
            "their own: %s",
            len(self.left_out),
            DOCUMENTS_FROM,
            DOCUMENTS_TO,
            ", ".join(self.left_out),
        )
        logger.info(
            "%d bodies given their official name; %d short names shared by two bodies and given "
            "to neither: %s",
            self.official_names,
            len(self.shared_short_names),
            ", ".join(self.shared_short_names),
        )
        logger.info(
            "%d bodies sit under a parent; %d have a website, %d of them on a registered "
            "federal domain (the registry line is the evidence for their homepage assignments)",
            self.with_parent,
            self.websites,
            len(self.registered),
        )


@dataclass(frozen=True, slots=True)
class Agency:
    """One record of the list, with the line of the text it is."""

    id: int
    slug: str
    name: str
    short_name: str | None
    parent_id: int | None
    website: str | None
    line: int


def read_agencies(opened: OpenedFile) -> list[Agency]:
    """The list's records, each with its line (the text is one line per record, in order)."""
    records: list[dict[str, Any]] = opened.document
    return [
        Agency(
            id=int(record["id"]),
            slug=record["slug"],
            name=" ".join(str(record["name"]).split()),
            short_name=" ".join(str(record["short_name"]).split()) or None
            if record.get("short_name")
            else None,
            parent_id=int(record["parent_id"]) if record.get("parent_id") else None,
            website=governments.website(record.get("agency_url")),
            line=index + 1,
        )
        for index, record in enumerate(records)
    ]


def published_slugs(opened: OpenedFile) -> set[str]:
    """The slugs of the agencies with a document in the window."""
    counts: dict[str, Any] = opened.document
    return {slug for slug, facet in counts.items() if int(facet.get("count", 0)) > 0}


def registered_domains(opened: OpenedFile) -> dict[str, str]:
    """Each federal domain's organization, by domain."""
    return {
        row["Domain name"].lower(): " ".join(row["Organization name"].split())
        for row in opened.rows
    }


def registrable_domain(url: str) -> str:
    """The domain a .gov host is registered as: its last two labels ("www.usda.gov" is
    "usda.gov")."""
    host = host_of(url)
    labels = host.split(".")
    return ".".join(labels[-2:]) if len(labels) > 1 else host


def _same_body(a: str, b: str) -> bool:
    """Whether two names are one body's but for case, punctuation and "U.S."."""

    def key(text: str) -> str:
        text = text.replace("U.S.", "United States").replace("US ", "United States ")
        return " ".join(re.sub(r"[^\w\s]", "", text).lower().split())

    return key(a) == key(b)


def official_name(name: str) -> tuple[str, str | None]:
    """A body's name as it writes it, and the list's name as an alias when they differ: the
    hand tables, else the list's name."""
    if name in OFFICIAL_NAMES:
        return OFFICIAL_NAMES[name], name
    return name, None


def build(
    files: Mapping[str, OpenedFile], rules: CountryRules
) -> tuple[list[InstitutionEntry], Notes]:
    """The entries, parents before children, and the notes of the build."""
    del rules
    notes = Notes()
    agencies = read_agencies(files[AGENCIES.name])
    by_id = {agency.id: agency for agency in agencies}
    published = published_slugs(files[DOCUMENTS.name])
    registry = registered_domains(files[DOTGOV_FEDERAL.name])

    kept = _kept(agencies, by_id, published, registry)
    notes.left_out = [agency.name for agency in agencies if agency.id not in kept]
    names = {agency.id: official_name(agency.name)[0] for agency in agencies if agency.id in kept}
    short_names = Counter(agency.short_name for agency in agencies if agency.id in kept)
    notes.shared_short_names = sorted(
        name for name, count in short_names.items() if name is not None and count > 1
    )

    found: list[InstitutionEntry] = []
    for agency in agencies:
        if agency.id not in kept:
            continue
        name, listed = official_name(agency.name)
        aliases: list[AliasEntry] = []
        if listed is not None:
            aliases.append(AliasEntry(text=listed))
            notes.official_names += 1
        if agency.short_name and agency.short_name != name and short_names[agency.short_name] == 1:
            aliases.append(
                AliasEntry(
                    text=agency.short_name, is_acronym=bool(_ACRONYM.match(agency.short_name))
                )
            )
        institution_type = DEPARTMENT if agency.name in CABINET else AGENCY
        notes.typed[institution_type] += 1
        notes.kept_by[kept[agency.id]] += 1
        parent = names[agency.parent_id] if agency.parent_id is not None else None
        if parent is not None:
            notes.with_parent += 1
        citation = Citation(source=AGENCIES.name, line=agency.line)
        citations: dict[Fact, Citation] = {"institution": citation}
        if agency.website is not None:
            citations["homepage"] = citation
            notes.websites += 1
            domain = registrable_domain(agency.website)
            if domain in registry:
                notes.registered.append((name, domain))
        found.append(
            InstitutionEntry(
                name=name,
                aliases=tuple(aliases),
                institution_type=institution_type,
                place=PLACE,
                place_level=PLACE_LEVEL,
                parent_institution=parent,
                homepage=agency.website,
                citations=citations,
            )
        )
    return _parents_first(found, by_id, names), notes


def _kept(
    agencies: list[Agency],
    by_id: Mapping[int, Agency],
    published: set[str],
    registry: Mapping[str, str],
) -> dict[int, str]:
    """The bodies kept, each with why: published in the window, a registered domain in its
    own name, or the parent of one so kept."""
    kept: dict[int, str] = {}
    for agency in agencies:
        if agency.slug in published:
            kept[agency.id] = "published in the window"
        elif agency.website is not None and _same_body(
            registry.get(registrable_domain(agency.website), ""), agency.name
        ):
            kept[agency.id] = "a registered domain in its own name"
    for agency_id in list(kept):
        parent_id = by_id[agency_id].parent_id
        while parent_id is not None and parent_id not in kept:
            kept[parent_id] = "the parent of a kept body"
            parent_id = by_id[parent_id].parent_id
    return kept


def _parents_first(
    entries: list[InstitutionEntry], by_id: Mapping[int, Agency], names: Mapping[int, str]
) -> list[InstitutionEntry]:
    """The entries ordered so a parent is loaded before its children, and by name within a
    depth, since the loader finds a parent by name among the bodies already at the place."""
    depth_of_name: dict[str, int] = {}
    for agency_id, name in names.items():
        depth, parent_id = 0, by_id[agency_id].parent_id
        while parent_id is not None:
            depth, parent_id = depth + 1, by_id[parent_id].parent_id
        depth_of_name[name] = depth
    return sorted(entries, key=lambda entry: (depth_of_name[entry.name], entry.name))


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[InstitutionEntry]:
    """Every kept body, parents first."""
    found, notes = build(files, rules)
    notes.log()
    return found
