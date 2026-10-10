"""Prince Edward Island's places from Statistics Canada's 2021 Census and the province's
Municipal Directory: the 57 municipalities, each with its code, its 2021 population, its
government's composed name and, where the directory links one, its website as a candidate
homepage. The province is single-tier: every municipality sits under Prince Edward Island, and
a county is only a census unit.

The census population table gives every unit's code, names and population and the geographic
attribute file says what each unit is (`canada/statcan.py`, shared with every province). The
directory on princeedwardisland.ca is a single-page application with no export, so it is a
manual file (`DIRECTORY.instructions`): a CSV derived by hand from the 57 detail views, one row
per municipality with the name, the kind, the population, the website, the URL of its detail
view and the saved page it was read from. The rules:

- A municipality (`CY`, `T`, `RM`, `RMU`) is matched to the directory's row by name. The
  directory's name is the place's and the census's an alias where the two differ (St. Peter's
  Bay); the directory writes the resort municipality's name as "Resort Municipality" alone, so
  that one keeps the census's name. The government's name is composed from the directory's
  kind and the name: "Rural Municipality of Belfast", "Town of Souris", "City of Charlottetown",
  and "Resort Municipality of Stanley Bridge, Hope River, Bayview, Cavendish and North Rustico"
  from the census type.
- A census municipality the directory no longer lists has dissolved since the census;
  `OVERRIDES` says when, and an unexplained one is an error.
- Fire districts and Indian reserves are not governments and are left out.
- The website is the directory's link; "n/a" is none.
"""

import logging
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from public_atlas.modules.graph.service import normalize_url
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.files import Format, ListFile, ListFileError, OpenedFile
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.statcan import (
    ATTRIBUTES,
    POPULATION,
    Citation,
    Draft,
    census_name,
)
from public_atlas.modules.imports.models import Retrieval

if TYPE_CHECKING:
    from public_atlas.modules.countries.naming import Naming
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = statcan.COUNTRY
PROVINCE = "Prince Edward Island"
PROVINCE_CODE = "11"
PRINCE_EDWARD_ISLAND = statcan.Province(PROVINCE_CODE)

DIRECTORY = ListFile(
    name="pei_municipal_directory_2026_10_09",
    title=(
        "Government of Prince Edward Island, Municipal Directory, the 57 municipalities' detail "
        "views as read on 2026-10-09"
    ),
    url="https://www.princeedwardisland.ca/en/feature/municipal-directory/",
    format=Format.CSV,
    retrieval=Retrieval.MANUAL,
    instructions=(
        "The directory is a single-page application with no export. Open it, run a blank "
        "search (57 results over three pages), open each result's detail view "
        "(MunicipalityInfoView;municipality_id=<id>) and save its HTML; then write one CSV row "
        "per municipality from the detail view's table, with the columns municipality_id, "
        "Municipality Name, Municipality Type, Date Incorporated, Population, Website (the "
        "link's href; 'n/a' when there is none), the officials and contact fields, source_url "
        "(the detail view's URL), captured_at_utc and html_snapshot_file. Save it as "
        "pei_municipal_directory_2026_10_09.csv; the saved pages and the per-field evidence log "
        "stay beside it outside the repository. Expect 57 rows: 2 cities, 10 towns and 45 "
        "rural municipalities (the resort municipality among them)."
    ),
    min_rows=57,
    filename_override="pei_municipal_directory_2026_10_09.csv",
    # The officials, the contact details and the meeting schedules stay out of the stored text.
    columns=(
        "municipality_id",
        "Municipality Name",
        "Municipality Type",
        "Population",
        "Website",
        "source_url",
        "html_snapshot_file",
    ),
)
SOURCES = (POPULATION, ATTRIBUTES, DIRECTORY)

MUNICIPAL_TYPES = PRINCE_EDWARD_ISLAND.municipal_types
DROPPED_TYPES = PRINCE_EDWARD_ISLAND.dropped_types
RESORT_MUNICIPALITY = "RMU"
# The directory writes the resort municipality's name as its kind alone.
GENERIC_NAME = "Resort Municipality"
NO_WEBSITE = "n/a"

# Hand corrections keyed by census code, each with its reason: `dissolved`, for a census
# municipality the directory no longer lists; `directory`, the directory's name for a
# municipality whose name the census writes otherwise.
OVERRIDES: dict[str, dict[str, str]] = {
    "1102035": {
        "dissolved": "2022-12-31",
        "reason": "the Rural Municipality of Darlington dissolved on 2022-12-31 (IRAC file "
        "LAM21002; the Canada Revenue Agency's list records the termination)",
    },
    "1103057": {
        "dissolved": "since 2021",
        "reason": "the Rural Municipality of St. Louis proposed its dissolution to IRAC in "
        "November 2021 and is not in the 2026 directory",
    },
    "1101044": {
        "directory": "St. Peter's Bay",
        "reason": "the census writes 'St. Peters Bay'; the directory and the municipality write "
        "the apostrophe",
    },
    "1102045": {
        "directory": GENERIC_NAME,
        "reason": "the directory names the resort municipality by its kind alone",
    },
}


@dataclass(frozen=True)
class Row:
    name: str
    kind: str
    homepage: str | None
    line: int


def read_rows(opened: OpenedFile) -> list[Row]:
    rows = []
    for row in opened.rows:
        site = row["Website"].strip()
        rows.append(
            Row(
                name=" ".join(row["Municipality Name"].split()),
                kind=row["Municipality Type"],
                homepage=normalize_url(site) if site and site.lower() != NO_WEBSITE else None,
                line=row.line,
            )
        )
    return rows


@dataclass
class Notes:
    dropped: Counter[str] = field(default_factory=Counter)
    dissolved: list[str] = field(default_factory=list)
    renamed: list[str] = field(default_factory=list)

    def log(self) -> None:
        for type_, count in sorted(self.dropped.items()):
            logger.info(
                "left out %d %s subdivisions (%s)", count, DROPPED_TYPES.get(type_, type_), type_
            )
        for line in self.dissolved:
            logger.info("override: %s", line)
        for line in self.renamed:
            logger.info("the directory names otherwise than the census: %s", line)


def government_name(row: Row, type_: str, name: str) -> str:
    designator = MUNICIPAL_TYPES[RESORT_MUNICIPALITY] if type_ == RESORT_MUNICIPALITY else row.kind
    return f"{designator} of {name}"


def build(files: Mapping[str, OpenedFile], naming: Naming) -> tuple[list[PlaceEntry], Notes]:
    census = PRINCE_EDWARD_ISLAND.read(files)
    rows = read_rows(files[DIRECTORY.name])
    by_key = {naming.key(row.name): row for row in rows}
    notes = Notes()
    found = []
    taken: set[int] = set()
    for unit in census.subdivisions:
        if unit.type_ not in MUNICIPAL_TYPES:
            notes.dropped[unit.type_] += 1
            continue
        fields = OVERRIDES.get(unit.code, {})
        if "dissolved" in fields:
            notes.dissolved.append(f"{unit.code} {unit.names[0]}: {fields['reason']}")
            continue
        row = by_key.get(naming.key(fields.get("directory", census_name(unit))))
        if row is None:
            raise ListFileError(
                f"{DIRECTORY.name}: no row for census municipality {unit.code} {unit.names[0]} "
                f"({unit.type_}) and no override says what became of it"
            )
        taken.add(row.line)
        name = census_name(unit) if row.name == GENERIC_NAME else row.name
        draft = Draft(unit=unit, name=name, parent=PROVINCE)
        if name != census_name(unit):
            notes.renamed.append(f"{unit.code} {census_name(unit)} -> {name}")
            draft.alias(census_name(unit))
        citation = Citation(source=DIRECTORY.name, line=row.line)
        draft.government = government_name(row, unit.type_, name)
        draft.government_citation = citation
        draft.homepage = row.homepage
        draft.homepage_citation = citation
        found.append(draft.entry())
    untaken = [row.name for row in rows if row.line not in taken]
    if untaken:
        raise ListFileError(f"{DIRECTORY.name}: rows no census municipality took: {untaken}")
    return sorted(found, key=lambda entry: entry.name), notes


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[PlaceEntry]:
    """Prince Edward Island's 57 municipalities, under the province."""
    found, notes = build(files, rules.naming)
    notes.log()
    return found
