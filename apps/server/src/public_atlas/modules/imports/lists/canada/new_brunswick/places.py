"""New Brunswick's places from Statistics Canada's interim list of changes and the province's
*Local government contacts* PDF: the 77 local governments of the 2023 reform, each with its
post-reform code, its government's composed name and, where the PDF gives one, its website as
a candidate homepage. The province is single-tier: every local government sits under New
Brunswick, and a county is only a census unit.

The reform of 2023-01-01 replaced 340 entities with 77 local governments (8 cities, 30 towns,
21 villages, 17 rural communities and the Regional Municipality of Tracadie) and 12 rural
districts, and did away with the parishes. The 2021 Census geography is pre-reform, so the
census files are not read: the interim list (`canada/statcan.py`, `INTERIM_CHANGES`) carries
every post-reform local government with its new code, name and type, one row per
incorporation, annexation or recoding, and no population is loaded until the 2026 Census. The
contacts PDF names each local government with its type, clerk, phone and website; the parser
reconstructs its table (`tables`), so each local government is a row and a line of its own,
and the government and the homepage cite that row. The rules:

- A local government is a row of the interim list whose gaining subdivision has a post-reform
  code (the reform renumbered every local government, the unchanged ones by an "SGC code
  change") and a municipal type; its first row is its citation. A rural district (`RDR`) is
  the province's administration of the unincorporated land, not a government, and is left out.
  Indian reserves are left out.
- The place is named as the interim list names it, with the second of two names ("Grand-Sault
  / Grand Falls", "Heron Bay / Baie-des-Hérons") as an alias; the PDF's spelling wins where the
  list's is a typo (Rivière-du-Nord, which the list writes "Rivère-du-Nord"). The government's
  name is composed from the type in English: "City of Bathurst", "Town of Caraquet", "Village
  of Belledune", "Rural Community of Alnwick", "Regional Municipality of Tracadie".
- The website is the PDF's where it is an address ("www.caraquet.ca", "Bathurst.ca"); a cell
  that holds a page title ("Grand Falls Regional Municipality") or a bare word is none.
"""

import html
import logging
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from public_atlas.modules.graph.models import IdentifierScheme
from public_atlas.modules.graph.service import host_of, is_domain_name, normalize_url
from public_atlas.modules.imports.entries import AliasEntry, Code, Fact, PlaceEntry
from public_atlas.modules.imports.files import Format, ListFile, ListFileError, OpenedFile
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.statcan import (
    INTERIM_CHANGES,
    MUNICIPALITY,
    PROVINCE_LEVEL,
    Change,
    Citation,
    read_changes,
)

if TYPE_CHECKING:
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = statcan.COUNTRY
PROVINCE = "New Brunswick"
PROVINCE_CODE = "13"
NEW_BRUNSWICK = statcan.Province(PROVINCE_CODE)

CONTACTS = ListFile(
    name="gnb_local_government_contacts_2026_09",
    title=(
        "Government of New Brunswick, Contact the representative who serves your local "
        "government, updated 2026-09-29"
    ),
    url=(
        "https://www2.gnb.ca/content/dam/gnb/Corporate/Promo/localgovreform/"
        "local-government-contacts.pdf"
    ),
    sha256="1671f4efedf6ba54cd775e5c1fda3b014dab11f350cd90a84615156c9dccfb09",
    format=Format.PDF,
    tables=True,
)
SOURCES = (INTERIM_CHANGES, CONTACTS)

MUNICIPAL_TYPES = NEW_BRUNSWICK.municipal_types
RURAL_DISTRICT = "RDR"
# The reform's codes: the county part of a post-reform code is 21 to 32, the pre-reform 01 to 15.
REFORMED = re.compile(r"^13(?:2\d|3\d)\d{3}$")
# The PDF's kinds, as the table writes them.
KINDS = ("City", "Town", "Village", "Rural Community", "Regional Municipality")
# The table's header cells the rows are read by.
NAME, TYPE, WEBSITE = "Local Government Name", "Type", "Website"
# The language of the second name, where the list gives two.
SECOND_NAME_LANGUAGE: dict[str, str] = {
    "Grand Falls": "en",
    "Baie-des-Hérons": "fr",
}

# Hand corrections keyed by the post-reform census code, each with its reason: `name`, the
# spelling the PDF and the local government use where the interim list's differs.
OVERRIDES: dict[str, dict[str, str]] = {
    "1324013": {
        "name": "Rivière-du-Nord",
        "reason": "the interim list writes 'Rivère-du-Nord'; the PDF and the town write "
        "Rivière-du-Nord",
    },
}
# The PDF's spelling of a name the interim list writes otherwise.
PDF_NAMES: dict[str, str] = {
    "Grand-Sault / Grand Falls": "Grand Falls/Grand-Sault",
    "Heron Bay / Baie-des-Hérons": "Heron Bay/Baie-des-Hérons",
}


@dataclass(frozen=True)
class Row:
    name: str
    kind: str
    homepage: str | None
    line: int


def website(cell: str) -> str | None:
    """The PDF's website cell as a URL, or None when it holds a page title or a bare word."""
    cell = cell.strip()
    if not cell or " " in cell or "." not in cell or "@" in cell:
        return None
    url = normalize_url(cell)
    return url if is_domain_name(host_of(url)) else None


def read_rows(opened: OpenedFile) -> list[Row]:
    """The table's rows, one markdown table line each. The header is read once; the second
    page's first row stands where a header would, and is a row."""
    rows = []
    columns: dict[str, int] | None = None
    for number, line in enumerate(opened.lines, 1):
        if not line.startswith("|") or line.startswith("|-"):
            continue
        cells = [html.unescape(cell).strip() for cell in line.strip().strip("|").split("|")]
        if cells[0] == NAME:
            columns = {cell: index for index, cell in enumerate(cells)}
            continue
        if columns is None:
            raise ListFileError(f"{CONTACTS.name} line {number}: a row before the table's header")
        if len(cells) != len(columns):
            raise ListFileError(f"{CONTACTS.name} line {number}: {len(cells)} cells, not a row")
        kind = cells[columns[TYPE]]
        if kind not in KINDS:
            raise ListFileError(f"{CONTACTS.name} line {number}: {kind!r} is no kind")
        rows.append(
            Row(
                name=" ".join(cells[columns[NAME]].split()),
                kind=kind,
                homepage=website(cells[columns[WEBSITE]]),
                line=number,
            )
        )
    return rows


@dataclass
class Notes:
    rural_districts: list[str] = field(default_factory=list)
    dropped: Counter[str] = field(default_factory=Counter)
    without_website: list[str] = field(default_factory=list)
    renamed: list[str] = field(default_factory=list)
    untaken: list[str] = field(default_factory=list)

    def log(self) -> None:
        for line in self.rural_districts:
            logger.info("rural district, not a government: %s", line)
        for type_, count in sorted(self.dropped.items()):
            logger.info("left out %d reformed subdivisions typed %s", count, type_)
        for line in self.without_website:
            logger.info("no website in the PDF: %s", line)
        for line in self.renamed:
            logger.info("override: %s", line)
        for line in self.untaken:
            logger.warning("PDF row no local government took: %s", line)


def local_governments(changes: list[Change], notes: Notes) -> list[Change]:
    """The first row of each post-reform local government."""
    first: dict[str, Change] = {}
    for change in changes:
        if not REFORMED.match(change.code) or change.code in first:
            continue
        if change.type_ == RURAL_DISTRICT:
            notes.rural_districts.append(f"{change.code} {change.name}")
            first[change.code] = change
            continue
        if change.type_ not in MUNICIPAL_TYPES:
            notes.dropped[change.type_] += 1
            first[change.code] = change
            continue
        first[change.code] = change
    return [change for change in first.values() if change.type_ in MUNICIPAL_TYPES]


def build(files: Mapping[str, OpenedFile]) -> tuple[list[PlaceEntry], Notes]:
    notes = Notes()
    governments = local_governments(read_changes(files[INTERIM_CHANGES.name], NEW_BRUNSWICK), notes)
    rows = read_rows(files[CONTACTS.name])
    by_name = {row.name.casefold(): row for row in rows}
    found = []
    taken: set[str] = set()
    for change in governments:
        fields = OVERRIDES.get(change.code, {})
        names = list(change.names)
        name = fields.get("name", names[0])
        if name != names[0]:
            notes.renamed.append(f"{change.code} {names[0]} -> {name}: {fields['reason']}")
        pdf_name = PDF_NAMES.get(change.name, name)
        row = by_name.get(pdf_name.casefold())
        if row is None:
            raise ListFileError(f"{CONTACTS.name}: no row for {change.code} {change.name}")
        taken.add(row.name)
        aliases = tuple(
            AliasEntry(text=other, language=SECOND_NAME_LANGUAGE.get(other, "en"))
            for other in names[1:]
        )
        interim = Citation(source=INTERIM_CHANGES.name, line=change.line)
        pdf = Citation(source=CONTACTS.name, line=row.line)
        citations: dict[Fact, Citation] = {"place": interim, "government": pdf}
        if row.homepage is not None:
            citations["homepage"] = pdf
        else:
            notes.without_website.append(f"{change.code} {name}")
        found.append(
            PlaceEntry(
                name=name,
                aliases=aliases,
                level=MUNICIPALITY,
                parent=PROVINCE,
                parent_level=PROVINCE_LEVEL,
                government=f"{MUNICIPAL_TYPES[change.type_]} of {name}",
                code=Code(scheme=IdentifierScheme.STATCAN_SGC, value=change.code),
                homepage=row.homepage,
                citations=citations,
            )
        )
    for row in rows:
        if row.name not in taken:
            notes.untaken.append(f"{row.name} ({row.kind})")
    return sorted(found, key=lambda entry: entry.name), notes


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[PlaceEntry]:
    """New Brunswick's 77 local governments, under the province."""
    del rules
    found, notes = build(files)
    notes.log()
    return found
