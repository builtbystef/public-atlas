"""Ontario's provincial agencies from the Treasury Board Secretariat's *List of provincial
agencies*: 137 agencies, boards, commissions, tribunals and councils, each under its ministry,
with its website as a candidate homepage, and the 25 ministries the list names, created under
Ontario as `ministry` rows so the agencies have a parent.

The list is one spreadsheet with two note rows above its header. Its rules:

- The classification column (the Agencies and Appointments Directive's) tells the type: an
  "Operational Enterprise" (the LCBO, Metrolinx, OLG, Ontario Power's financing corporation,
  the museums and parks commissions) is a `crown_corporation`; everything else (adjudicative,
  advisory, regulatory, operational service, trust) is an `agency`.
- The `Ministry` column names the ministry without the word: "Health" is the Ministry of
  Health. The Attorney General's and Solicitor General's take "the", and the Treasury Board
  Secretariat is not a ministry by name. The French column gives the ministry's French name as
  an alias; where the rows of one ministry disagree, the spelling most of them use wins.
- A trailing parenthetical in the agency's name is the name it goes by ("Ontario Science
  Centre") or its acronym ("TVO"), kept as an alias; "(English)", "(French)" and "(Crown
  Employees)" tell two bodies apart and stay in the name. The French name (`Organisme`) is an
  alias the same way.
- The website is the first address in the cell that is the agency's own: many are bare hosts
  ("www.agco.on.ca"); page titles ("Building Code Commission | ontario.ca"), "N/A" and "TBD"
  are no address; and the Public Appointments Secretariat's page of the agency, which four
  rows give alone and a few give first, is the directory's page, not the agency's. The address
  is kept as given, path included: a council's page on ontario.ca is its homepage.

The CKAN resource is `a1d05d04-1a6c-4342-97c2-0a3be47aea41` on dataset
`b72f248c-2e08-4b37-9882-9360c8398bec`; the file name carries the release month, so a new
release is one URL and hash swap.
"""

import logging
import re
from collections import Counter
from collections.abc import Mapping
from typing import TYPE_CHECKING

from public_atlas.modules.graph.service import host_of, normalize_url
from public_atlas.modules.imports.entries import AliasEntry, Citation, Fact, InstitutionEntry
from public_atlas.modules.imports.files import Format, ListFile, OpenedFile, Row
from public_atlas.shared.text import name_key

if TYPE_CHECKING:
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = "CA"
PROVINCE = "Ontario"
PROVINCE_LEVEL = "province_territory"
MINISTRY = "ministry"
AGENCY = "agency"
CROWN_CORPORATION = "crown_corporation"

AGENCIES = ListFile(
    name="tbs_provincial_agencies_2026_01",
    title=(
        "Ontario Treasury Board Secretariat, List of provincial agencies, release of January 2026"
    ),
    url=(
        "https://data.ontario.ca/dataset/b72f248c-2e08-4b37-9882-9360c8398bec/resource/"
        "a1d05d04-1a6c-4342-97c2-0a3be47aea41/download/provincial_agencies_list_-_january_2026.xlsx"
    ),
    sha256="15aae798f7e8da6ed4cd12548f778215b1f91bd52b79a66ebce658424d47fd19",
    format=Format.SPREADSHEET,
    header_row=3,
    columns=(
        "Agency Name",
        "Organisme",
        "Ministry",
        "Ministère",
        "Type",
        "AEAD, 2010 Classification/AAD, 2015 Classification",
        "Website",
    ),
)
SOURCES = (AGENCIES,)

CLASSIFICATION = "AEAD, 2010 Classification/AAD, 2015 Classification"
OPERATIONAL_ENTERPRISE = "Operational Enterprise"
# Ministries the column does not name as "Ministry of X".
MINISTRY_NAMES = {
    "Attorney General": "Ministry of the Attorney General",
    "Solicitor General": "Ministry of the Solicitor General",
    "Treasury Board Secretariat": "Treasury Board Secretariat",
}
# Parentheticals that are part of the name.
KEPT_NOTES = frozenset({"English", "French", "anglais", "français", "Crown Employees"})
# Hosts whose pages are the directory's, never an agency's homepage.
DIRECTORY_HOSTS = frozenset({"www.pas.gov.on.ca", "pas.gov.on.ca"})
NO_ADDRESS = frozenset({"", "n/a", "tbd"})

# Hand corrections keyed by the agency's name as the list writes it, each with its reason.
# Fields: `homepage` (None when the list's address is not the agency's own site).
OVERRIDES: dict[str, dict[str, str | None]] = {}

_TRAILING_NOTE = re.compile(r"^(?P<name>.+?)\s*\((?P<note>[^()]*)\)$")
_ACRONYM = re.compile(r"^[A-Z]{2,}$")
_ADDRESS = re.compile(r"(?:https?://|www\.)\S+")


def split_name(text: str, language: str = "en") -> tuple[str, list[AliasEntry]]:
    """The name without its trailing parenthetical, and the alias the parenthetical gives."""
    text = " ".join(text.split())
    match = _TRAILING_NOTE.match(text)
    if match is None:
        return text, []
    name, note = match.group("name"), " ".join(match.group("note").split())
    if note in KEPT_NOTES or not note:
        return text, []
    return name, [AliasEntry(text=note, language=language, is_acronym=bool(_ACRONYM.match(note)))]


def ministry_name(column: str) -> str:
    return MINISTRY_NAMES.get(column, f"Ministry of {column}")


def homepage_of(cell: str) -> str | None:
    """The first address in the cell that is the agency's, not the directory's."""
    if cell.strip().casefold() in NO_ADDRESS:
        return None
    for found in _ADDRESS.findall(cell):
        url = normalize_url(found.rstrip(".,;"))
        if host_of(url) not in DIRECTORY_HOSTS:
            return url
    return None


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[InstitutionEntry]:  # noqa: ARG001 - the loader's signature
    """The ministries first, then the agencies, each group by name."""
    opened = files[AGENCIES.name]
    ministries = _ministries(opened.rows)
    agencies: list[InstitutionEntry] = []
    applied: set[str] = set()
    for row in opened.rows:
        listed = " ".join(row["Agency Name"].split())
        fields = OVERRIDES.get(listed, {})
        if fields:
            applied.add(listed)
            logger.info("override: %s: %s", listed, fields["reason"])
        name, aliases = split_name(listed)
        french, french_aliases = split_name(row["Organisme"], "fr")
        if french:
            aliases.append(AliasEntry(text=french, language="fr"))
        aliases.extend(french_aliases)
        homepage = fields["homepage"] if "homepage" in fields else homepage_of(row["Website"])
        citation = Citation(source=AGENCIES.name, line=row.line)
        citations: dict[Fact, Citation] = {"institution": citation}
        if homepage is not None:
            citations["homepage"] = citation
        agencies.append(
            InstitutionEntry(
                name=name,
                aliases=tuple(aliases),
                institution_type=(
                    CROWN_CORPORATION if row[CLASSIFICATION] == OPERATIONAL_ENTERPRISE else AGENCY
                ),
                place=PROVINCE,
                place_level=PROVINCE_LEVEL,
                parent_institution=ministry_name(row["Ministry"]),
                homepage=homepage,
                citations=citations,
            )
        )
    for listed, fields in OVERRIDES.items():
        if listed not in applied:
            logger.warning(
                "override changed nothing: %s: %s (no such row)", listed, fields["reason"]
            )
    return [*ministries, *sorted(agencies, key=lambda entry: name_key(entry.name))]


def _ministries(rows: list[Row]) -> list[InstitutionEntry]:
    """One entry per ministry the rows name, cited to the first row that names it, with the
    French name most of its rows give as an alias."""
    first: dict[str, Row] = {}
    french: dict[str, Counter[str]] = {}
    for row in rows:
        name = ministry_name(row["Ministry"])
        first.setdefault(name, row)
        french.setdefault(name, Counter())[" ".join(row["Ministère"].split())] += 1
    found = []
    for name, row in first.items():
        (french_name, _), *others = french[name].most_common()
        if others:
            logger.info(
                "%s is written %d ways in French; %r kept", name, len(others) + 1, french_name
            )
        found.append(
            InstitutionEntry(
                name=name,
                aliases=(AliasEntry(text=french_name, language="fr"),) if french_name else (),
                institution_type=MINISTRY,
                place=PROVINCE,
                place_level=PROVINCE_LEVEL,
                citations={"institution": Citation(source=AGENCIES.name, line=row.line)},
            )
        )
    return sorted(found, key=lambda entry: name_key(entry.name))
