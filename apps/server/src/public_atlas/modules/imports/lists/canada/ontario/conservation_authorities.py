"""Ontario's conservation authorities from the province's *Conservation Authority
Administrative Area* layer on Land Information Ontario's open data service: 36 authorities,
every one a `conservation_authority`, named as the layer's legal name with its common name as
an alias, attached to the municipality of its head office as the FIPPA/MFIPPA Directory of
Institutions gives it. No websites: no official list carries them.

The layer is one ArcGIS REST query of every record without its geometry, read in the
service's HTML rendering: the loader renders a JSON object as one line, and the layer's JSON is
one object holding the records, so each authority would have had to cite the whole file. The
HTML rendering is the same query's records as a page, one line per field, so each authority
cites the line that names it. Its rules:

- `LEGAL_NAME` is the name ("Nickel District Conservation Authority") and `COMMON_NAME` the
  alias ("Conservation Sudbury") when it differs by more than punctuation.
- The head office's municipality is the `City` of the directory's row of the same authority,
  found by its legal or common name (`DIRECTORY_NAMES` for the two the directory names
  otherwise), read through `communities.py` so a post office's community is its municipality.
- The province has announced the authorities' consolidation into regional authorities under a
  new provincial agency: a new release of the layer is the place to look for it.
"""

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from public_atlas.modules.imports.entries import AliasEntry, Citation, InstitutionEntry
from public_atlas.modules.imports.files import Format, ListFile, ListFileError, OpenedFile
from public_atlas.modules.imports.lists.canada.ontario.communities import location_of
from public_atlas.modules.imports.lists.canada.ontario.fippa_bodies import DIRECTORY, as_text
from public_atlas.shared.text import name_key

if TYPE_CHECKING:
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = "CA"
CONSERVATION_AUTHORITY = "conservation_authority"

LAYER = ListFile(
    name="lio_conservation_authority_admin_area",
    title=(
        "Land Information Ontario, Conservation Authority Administrative Area "
        "(LIO_Open03/MapServer/11), every record without geometry"
    ),
    url=(
        "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open03/"
        "MapServer/11/query?where=1%3D1&outFields=*&returnGeometry=false&f=html"
    ),
    sha256="87476f4c1acd6c9079872fc9071b822cadfddf17b006200b243c8b42d3b80516",
    format=Format.HTML,
    filename_override="conservation_authority_admin_area.html",
)
# The FIPPA/MFIPPA directory, as `fippa_bodies` reads it: its 36 Conservation Authority rows
# give each authority's city.
SOURCES = (LAYER, DIRECTORY)

DIRECTORY_TYPE = "Conservation Authority"
EXPECTED = 36

# The directory's name of an authority the layer names otherwise, to the layer's legal name.
DIRECTORY_NAMES: dict[str, str] = {
    "Lower Trent Region Conservation": "Lower Trent Conservation Authority",
    "South Nation Conservation Authority": "South Nation River Conservation Authority",
}

# Hand corrections keyed by the legal name, each with its reason. Fields: `place` (the city,
# when the directory's is wrong).
OVERRIDES: dict[str, dict[str, str]] = {
    "Long Point Region Conservation Authority": {
        "place": "Tillsonburg",
        "reason": "the directory writes 'Tilllsonburg'",
    },
}

_FIELD = re.compile(r"^(?P<field>[A-Z_.]+): (?P<value>.*)$")
_RECORDS = re.compile(r"^# records: (?P<count>\d+)$")


@dataclass(frozen=True, slots=True)
class Record:
    """One authority as the layer lists it, with the line its legal name is on."""

    legal_name: str
    common_name: str
    line: int


def read_layer(opened: OpenedFile) -> list[Record]:
    """The layer's records from the page's lines: a record per `OGF_ID` line, its fields on
    the lines after."""
    records: list[Record] = []
    fields: dict[str, tuple[str, int]] = {}
    count: int | None = None

    def close() -> None:
        if "LEGAL_NAME" in fields:
            legal, line = fields["LEGAL_NAME"]
            common, _ = fields.get("COMMON_NAME", ("", 0))
            records.append(Record(legal_name=legal, common_name=common, line=line))
        fields.clear()

    for number, text in enumerate(opened.lines, start=1):
        counted = _RECORDS.match(text)
        if counted:
            count = int(counted.group("count"))
            continue
        match = _FIELD.match(text)
        if match is None:
            continue
        if match.group("field") == "OGF_ID":
            close()
        fields[match.group("field")] = (" ".join(match.group("value").split()), number)
    close()
    if count is None or count != len(records):
        raise ListFileError(f"{LAYER.name}: the page says {count} records and lists {len(records)}")
    return records


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[InstitutionEntry]:  # noqa: ARG001 - the loader's signature
    """The authorities, by name."""
    records = read_layer(files[LAYER.name])
    cities = _cities(files[DIRECTORY.name], records)
    found: list[InstitutionEntry] = []
    applied: set[str] = set()
    for record in records:
        fields = OVERRIDES.get(record.legal_name, {})
        if fields:
            applied.add(record.legal_name)
            logger.info("override: %s: %s", record.legal_name, fields["reason"])
        city = fields.get("place") or cities.get(record.legal_name)
        if city is None:
            raise ListFileError(f"{DIRECTORY.name}: no row names {record.legal_name!r}")
        where = location_of(city)
        aliases = ()
        if record.common_name and _plain(record.common_name) != _plain(record.legal_name):
            aliases = (AliasEntry(text=record.common_name),)
        found.append(
            InstitutionEntry(
                name=record.legal_name,
                aliases=aliases,
                institution_type=CONSERVATION_AUTHORITY,
                place=where.place,
                place_level=where.level,
                place_parent=where.parent,
                citations={"institution": Citation(source=LAYER.name, line=record.line)},
            )
        )
    for name, fields in OVERRIDES.items():
        if name not in applied:
            logger.warning("override changed nothing: %s: %s (no such row)", name, fields["reason"])
    return sorted(found, key=lambda entry: name_key(entry.name))


def _plain(text: str) -> str:
    """A name as two spellings are compared: its key with the stops dropped, so "Sault Ste Marie"
    is "Sault Ste. Marie"."""
    return name_key(text.replace(".", ""))


def _cities(opened: OpenedFile, records: list[Record]) -> dict[str, str]:
    """Each authority's city from the directory's row that names it, by legal name. A row that
    names no authority, or an authority named twice, is an error: the two lists have drifted."""
    by_key: dict[str, str] = {}
    for record in records:
        by_key[name_key(record.legal_name)] = record.legal_name
        if record.common_name:
            by_key.setdefault(name_key(record.common_name), record.legal_name)
    cities: dict[str, str] = {}
    for row in opened.rows:
        if row["Institution type"] != DIRECTORY_TYPE:
            continue
        listed = as_text(row["Name of institution"])
        legal = by_key.get(name_key(DIRECTORY_NAMES.get(listed, listed)))
        if legal is None:
            raise ListFileError(f"{DIRECTORY.name}: {listed!r} is no authority the layer lists")
        if legal in cities:
            raise ListFileError(f"{DIRECTORY.name}: {legal!r} is listed twice")
        cities[legal] = as_text(row["City"])
    return cities
