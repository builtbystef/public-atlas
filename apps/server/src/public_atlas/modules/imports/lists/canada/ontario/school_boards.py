"""Ontario's school boards and school authorities from the Ministry of Education's monthly
contact list: 72 district school boards (English and French, public and Catholic) and 11
school authorities, every one a `school_board`, with its website as a candidate homepage,
attached to the municipality of its head office.

The file is one row per board (85 in the September 2026 release), ISO-8859-1. Its rules:

- `Board Type` tells a district school board from a school authority: the hospital and
  provincial school authorities, the two district school area boards of the James Bay coast,
  the secondary school board there, the Protestant separate school board and the one
  consortium. The type is `school_board` for all; a school authority carries its kind as an
  alias, since the type cannot say it.
- `Board Language` French names the body in French.
- "Provincial and Demonstration Schools" is a unit of the ministry, not a board: left out.
- Grandview School Authority is listed twice, at its old Oshawa site and at the Ajax campus
  it moved to in 2024; the Ajax row is kept.
- The place is the municipality the `City` column's community lies in, with its level and
  parent so a city named like its district is the city (`communities.py`). Moose Factory is
  unorganized land: the district of Cochrane.
- The website is the row's, given a scheme where it has none.

The file's name carries the release month and changes with it, so the URL pins one release;
the CKAN resource is `74aa6226-7798-4130-ba44-8546e3198186` on dataset
`9831236f-6e01-447a-9e28-b9c6b3348631`, where the next month's file is found.
"""

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING

from public_atlas.modules.graph.service import normalize_url
from public_atlas.modules.imports.entries import AliasEntry, Citation, Fact, InstitutionEntry
from public_atlas.modules.imports.files import Format, ListFile, ListFileError, OpenedFile, Row
from public_atlas.modules.imports.lists.canada.ontario.communities import location_of
from public_atlas.shared.text import name_key

if TYPE_CHECKING:
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = "CA"
SCHOOL_BOARD = "school_board"

CONTACTS = ListFile(
    name="school_board_contacts_2026_09",
    title=(
        "Ontario Ministry of Education, School board and school authority contact information, "
        "release of September 2026"
    ),
    url=(
        "https://data.ontario.ca/dataset/9831236f-6e01-447a-9e28-b9c6b3348631/resource/"
        "74aa6226-7798-4130-ba44-8546e3198186/download/"
        "school_board_contact_list_september2026_en_csv.csv"
    ),
    sha256="efcb405b1ca08f4124c4468de51ee1daffe3df486cf5b47f45c61ea73dc16268",
    format=Format.CSV,
    encoding="iso-8859-1",
    # The address and phone columns stay out of the stored text.
    columns=("Board Number", "Board Name", "Board Language", "Board Type", "City", "Website"),
)
SOURCES = (CONTACTS,)

# The file's `Board Type` labels: a district school board, or a school authority of a kind.
DISTRICT_BOARD_TYPES = frozenset({"Pub Dist Sch Brd (E/F)", "Cath Dist Sch Brd (E/F)"})
AUTHORITY_KINDS = {
    "Provincial/Hospital": "Hospital school authority",
    "Public School Board": "District school area board",
    "Sec Sch Brd (Sch Auth)": "Secondary school board",
    "Prot Sep Sch Brd (Sch Auth)": "Protestant separate school board",
    "Consortium": "School authority consortium",
}

# Rows left out, with the reason.
LEFT_OUT: dict[str, str] = {
    "Provincial and Demonstration Schools": (
        "a unit of the Ministry of Education that runs the provincial schools, not a board"
    ),
}

# Hand corrections keyed by the board's name, each with its reason. Fields: `city` (the row to
# keep when the board is listed at more than one address), `place` (the city, when the City
# column is wrong).
OVERRIDES: dict[str, dict[str, str]] = {
    "Grandview School Authority": {
        "city": "Ajax",
        "reason": "listed twice; the Ajax row is the campus it moved to in 2024, Oshawa the old",
    },
}


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[InstitutionEntry]:  # noqa: ARG001 - the loader's signature
    """The boards, district school boards first, each group by name."""
    opened = files[CONTACTS.name]
    by_number: dict[str, list[Row]] = {}
    for row in opened.rows:
        by_number.setdefault(row["Board Number"], []).append(row)
    found: list[InstitutionEntry] = []
    applied: set[str] = set()
    for rows in by_number.values():
        name = " ".join(rows[0]["Board Name"].split())
        if name in LEFT_OUT:
            logger.info("left out %s: %s", name, LEFT_OUT[name])
            continue
        fields = OVERRIDES.get(name, {})
        if fields:
            applied.add(name)
            logger.info("override: %s: %s", name, fields["reason"])
        found.append(_entry(name, _address(name, rows, fields), fields))
    for name, fields in OVERRIDES.items():
        if name not in applied:
            logger.warning("override changed nothing: %s: %s (no such row)", name, fields["reason"])
    return sorted(found, key=lambda entry: (is_school_authority(entry), name_key(entry.name)))


def _address(name: str, rows: list[Row], fields: Mapping[str, str]) -> Row:
    """The board's row: when it is listed at more than one address, the one the override
    names, else the first."""
    if len(rows) == 1:
        return rows[0]
    wanted = [row for row in rows if row["City"] == fields.get("city")]
    row = wanted[0] if wanted else rows[0]
    logger.info("%s is listed %d times; kept at %s", name, len(rows), row["City"])
    return row


def _entry(name: str, row: Row, fields: Mapping[str, str]) -> InstitutionEntry:
    board_type = row["Board Type"]
    aliases: tuple[AliasEntry, ...] = ()
    if board_type in AUTHORITY_KINDS:
        aliases = (AliasEntry(text=AUTHORITY_KINDS[board_type]),)
    elif board_type not in DISTRICT_BOARD_TYPES:
        raise ListFileError(f"{CONTACTS.name}: {name} has an unknown board type {board_type!r}")
    website = row["Website"]
    homepage = normalize_url(website) if website else None
    where = location_of(fields.get("place") or row["City"])
    citation = Citation(source=CONTACTS.name, line=row.line)
    citations: dict[Fact, Citation] = {"institution": citation}
    if homepage is not None:
        citations["homepage"] = citation
    return InstitutionEntry(
        name=name,
        aliases=aliases,
        language="fr" if row["Board Language"] == "French" else "en",
        institution_type=SCHOOL_BOARD,
        place=where.place,
        place_level=where.level,
        place_parent=where.parent,
        homepage=homepage,
        citations=citations,
    )


def is_school_authority(entry: InstitutionEntry) -> bool:
    return any(alias.text in AUTHORITY_KINDS.values() for alias in entry.aliases)
