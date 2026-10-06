"""Ontario's places from Statistics Canada's 2021 Census and the province's list of
municipalities: 40 regions (30 upper-tier governments and 10 territorial districts that nothing
governs) and 414 municipalities, each with its code, its 2021 population, its government's legal
name and, where the province links one, the government's homepage as a candidate.

The census population table gives every unit's code, names and population; the census
geographic attribute file says what each unit is (a county, a township, a reserve); the
province's directory gives each government's legal name, its tier and its website. The rules:

- A county (`CTY`), regional municipality (`RM`), district municipality (`DM`) or united counties
  (`UC`) is a region with a government, named and linked from the directory's Upper Tier row. A
  territorial district (`DIS`) is a region with no government: the ten northern districts have
  no council, and the bodies at that level need the place as a parent. A division that is only a
  census unit (`CDR`: a city counted as its own division, or two single tiers counted together)
  is no place, and its municipalities sit under the province.
- The municipal subdivision types are municipalities. Indian reserves, Indian settlements and
  unorganized areas are not governments and are left out. A municipality's parent is the region
  its division is, or the province when the division is no place or an override says so (a
  separated city the census counts inside a county it does not belong to).
- The directory row is matched by name in any of its forms within the division's geographic
  area; the government's name is the row's legal name written out ("City of Kingston" from
  "Kingston, City of"). A place the directory does not list is named from its census type.
- The place keeps the census's name, with its French name as an alias where the census carries
  one. An override renames a place the directory knows under a newer name.

First Nations are deferred: a reserve is land, not a government, so the right list is
Indigenous Services Canada's First Nation Profiles, a later module.
"""

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.graph.service import normalize_url
from public_atlas.modules.imports.entries import (
    AliasEntry,
    Citation,
    Code,
    Fact,
    Figure,
    PlaceEntry,
)
from public_atlas.modules.imports.files import Format, ListFileError, OpenedFile, Source
from public_atlas.shared.text import repair_mojibake

if TYPE_CHECKING:
    from collections.abc import Mapping

    from public_atlas.modules.countries.naming import Naming
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = "CA"
PROVINCE = "Ontario"
PROVINCE_CODE = "35"
REGION = "region"
MUNICIPALITY = "municipality"
CENSUS_YEAR = 2021
# A division code is the province's two digits plus two; a subdivision's is longer and starts
# with its division's.
DIVISION_CODE_LENGTH = 4

POPULATION_COLUMN = "Population and dwelling counts (13): Population, 2021 [1]"
# A DGUID is the vintage, the geographic level and the code: 2021A0005 3510010 is Kingston.
# Ontario's rows only (35).
DGUID = re.compile(r"^2021A000[235](?P<code>35\d*)$")
# Between the names of a row that has two ("Greater Sudbury / Grand Sudbury").
NAME_SEPARATOR = " / "

POPULATION = Source(
    name="statcan_population_2021",
    title=(
        "Statistics Canada, table 98-10-0002-01: Population and dwelling counts, Canada and "
        "census subdivisions (municipalities), 2021 Census"
    ),
    url="https://www150.statcan.gc.ca/n1/tbl/csv/98100002-eng.zip",
    sha256="36ab6c8f3f6b82d70d9dea927cb5cf04f6fbf9b543a7ad543695e6ea70d22876",
    format=Format.CSV,
    member="98100002.csv",
    columns=("GEO", "DGUID", POPULATION_COLUMN),
)
# One row per dissemination block in the country (half a million); read for the division and
# subdivision columns, once per distinct unit.
ATTRIBUTES = Source(
    name="statcan_geographic_attributes_2021",
    title="Statistics Canada, 2021 Census Geographic Attribute File (92-151-X)",
    url=(
        "https://www12.statcan.gc.ca/census-recensement/2021/geo/aip-pia/attribute-attribs/"
        "files-fichiers/2021_92-151_X.zip"
    ),
    sha256="918aa8502d9d95b1ae5ce437ed9674e0977ec55977c08b8d01822a9dab6fe5da",
    format=Format.CSV,
    member="2021_92-151_X.csv",
    encoding="cp1252",
    columns=(
        "PRUID_PRIDU",
        "CDUID_DRIDU",
        "CDNAME_DRNOM",
        "CDTYPE_DRGENRE",
        "CSDUID_SDRIDU",
        "CSDNAME_SDRNOM",
        "CSDTYPE_SDRGENRE",
    ),
    distinct=True,
)
DIRECTORY = Source(
    name="ontario_municipal_directory_2026_05",
    title=(
        "Ontario Ministry of Municipal Affairs and Housing, List of Ontario municipalities, "
        "release of 2026-05-26"
    ),
    url=(
        "https://data.ontario.ca/dataset/62e83cbc-0731-4d66-abdc-2f2b31bcd76c/resource/"
        "6783a586-6b05-4a73-9663-e60a6963c91e/download/municipalities_-_en_2026-0526.csv"
    ),
    sha256="5370b4e1b3804d10059c67513db9ea59d61bba964096f8e5b35f4a8afd973196",
    format=Format.CSV,
)
SOURCES = (POPULATION, ATTRIBUTES, DIRECTORY)

# Census division types (SGC 2021): a government, a territorial district, or a unit the census
# counts and nothing governs.
UPPER_TIER_TYPES = {
    "CTY": "County",
    "RM": "Regional Municipality",
    "UC": "United Counties",
    "DM": "District Municipality",
}
DISTRICT_TYPE = "DIS"
CENSUS_ONLY_TYPE = "CDR"
# Census subdivision types that are municipalities, with the designator each gives a
# government's name when the directory has no row for it.
MUNICIPAL_TYPES = {
    "C": "City",
    "CV": "City",
    "CY": "City",
    "T": "Town",
    "TV": "Town",
    "TP": "Township",
    "VL": "Village",
    "M": "Municipality",
    "MU": "Municipality",
}
DROPPED_TYPES = {
    "IRI": "Indian reserve",
    "NO": "unorganized area",
    "S-É": "Indian settlement",
}

UPPER_TIER = "Upper Tier"
# A directory cell is a link whose title is the legal name.
ANCHOR = re.compile(r'^<a title="(?P<title>[^"]*)"(?: href="(?P<href>[^"]*)")?>(?P<text>.*)</a>')

# Hand corrections, keyed by census code, each with its reason. Fields: `parent` (the place the
# place belongs to, when it is not the division it is counted in), `directory` (the title of
# the directory row to take the government's name and homepage from, when the census writes the
# name otherwise), `name`, `government`, `homepage`.
OVERRIDES: dict[str, dict[str, str]] = {
    # Separated municipalities: single tiers the census counts inside the county or region they
    # are geographically within but do not belong to. The directory has them as Single Tier.
    "3543042": {"parent": PROVINCE, "reason": "Barrie is a separated city inside Simcoe County"},
    "3512005": {
        "parent": PROVINCE,
        "reason": "Belleville is a separated city inside Hastings County",
    },
    "3507015": {
        "parent": PROVINCE,
        "reason": "Brockville is a separated city inside Leeds and Grenville",
    },
    "3501012": {
        "parent": PROVINCE,
        "reason": "Cornwall is a separated city inside Stormont, Dundas and Glengarry",
    },
    "3507024": {
        "parent": PROVINCE,
        "reason": "Gananoque is a separated town inside Leeds and Grenville",
    },
    "3523008": {
        "parent": PROVINCE,
        "reason": "Guelph is a separated city inside Wellington County",
    },
    "3510010": {
        "parent": PROVINCE,
        "reason": "Kingston is a separated city inside Frontenac County",
    },
    "3539036": {"parent": PROVINCE, "reason": "London is a separated city inside Middlesex County"},
    "3543052": {"parent": PROVINCE, "reason": "Orillia is a separated city inside Simcoe County"},
    "3537001": {"parent": PROVINCE, "reason": "Pelee is a separated township inside Essex County"},
    "3547064": {"parent": PROVINCE, "reason": "Pembroke is a separated city inside Renfrew County"},
    "3515014": {
        "parent": PROVINCE,
        "reason": "Peterborough is a separated city inside Peterborough County",
    },
    "3507008": {
        "parent": PROVINCE,
        "reason": "Prescott is a separated town inside Leeds and Grenville",
    },
    "3512015": {
        "parent": PROVINCE,
        "reason": "Quinte West is a separated city inside Hastings County",
    },
    "3509004": {
        "parent": PROVINCE,
        "reason": "Smiths Falls is a separated town inside Lanark County",
    },
    "3531016": {"parent": PROVINCE, "reason": "St. Marys is a separated town inside Perth County"},
    "3534021": {"parent": PROVINCE, "reason": "St. Thomas is a separated city inside Elgin County"},
    "3531011": {"parent": PROVINCE, "reason": "Stratford is a separated city inside Perth County"},
    "3537039": {"parent": PROVINCE, "reason": "Windsor is a separated city inside Essex County"},
    # Renamed since the 2021 Census.
    "3557014": {
        "directory": "Tarbutt, Township of",
        "name": "Tarbutt",
        "reason": (
            "the census writes 'Tarbutt and Tarbutt Additional'; the township is Tarbutt since 2022"
        ),
    },
}


# --- The files ---


@dataclass
class Counted:
    """A census unit: a division or a subdivision."""

    code: str
    names: tuple[str, ...]
    population: int | None
    # The population table's line.
    line: int
    type_: str = ""
    # The division's code for a subdivision; None for a division.
    division: str | None = None


@dataclass(frozen=True)
class DirectoryRow:
    # The legal name in the list's inverted form: "Kingston, City of".
    name: str
    status: str
    area: str
    homepage: str | None
    line: int


def _read_population(opened: OpenedFile) -> dict[str, Counted]:
    """The province, its divisions and subdivisions, with their names and 2021 population."""
    counted: dict[str, Counted] = {}
    for row in opened.rows:
        match = DGUID.match(row["DGUID"])
        if match is None:
            continue
        code = match.group("code")
        names = tuple(part.strip() for part in row["GEO"].split(NAME_SEPARATOR) if part.strip())
        figure = row[POPULATION_COLUMN].replace(",", "")
        counted[code] = Counted(
            code=code,
            names=names,
            population=int(figure) if figure.isdigit() else None,
            line=row.line,
        )
    return counted


def _read_types(counted: dict[str, Counted], opened: OpenedFile) -> None:
    """The type of each division and subdivision, and which division a subdivision is in."""
    for row in opened.rows:
        if row["PRUID_PRIDU"] != PROVINCE_CODE:
            continue
        for code, type_ in (
            (row["CDUID_DRIDU"], row["CDTYPE_DRGENRE"]),
            (row["CSDUID_SDRIDU"], row["CSDTYPE_SDRGENRE"]),
        ):
            unit = counted.get(code)
            if unit is not None and not unit.type_:
                unit.type_ = type_
                unit.division = (
                    code[:DIVISION_CODE_LENGTH] if len(code) > DIVISION_CODE_LENGTH else None
                )
    missing = [
        unit.code for unit in counted.values() if not unit.type_ and unit.code != PROVINCE_CODE
    ]
    if missing:
        raise ListFileError(
            f"no type in the attribute file for {len(missing)} census codes: {missing[:5]}"
        )


def _read_directory(opened: OpenedFile) -> list[DirectoryRow]:
    """Each row's legal name, tier, geographic area and website, read from the link the cell
    holds. UTF-8 that was read as Windows-1252 is put right."""
    rows = []
    for row in opened.rows:
        cell = row["Municipality"]
        match = ANCHOR.match(cell)
        if match is None:
            raise ListFileError(f"{DIRECTORY.name}: a directory cell is not a link: {cell!r}")
        name = repair_mojibake(" ".join(match.group("title").split()))
        href = (match.group("href") or "").strip()
        rows.append(
            DirectoryRow(
                name=name,
                status=row["Municipal status"],
                area=row["Geographic area"],
                homepage=normalize_url(href) if href else None,
                line=row.line,
            )
        )
    return rows


class Directory:
    """The directory's rows, indexed by the forms of their names."""

    def __init__(self, rows: list[DirectoryRow], naming: Naming) -> None:
        self.naming = naming
        self.rows = rows
        self.by_form: dict[str, list[DirectoryRow]] = {}
        for row in rows:
            for form in naming.forms(row.name):
                self.by_form.setdefault(form, []).append(row)
        self.taken: set[str] = set()

    def find(
        self, unit: Counted, *, upper: bool, area_names: tuple[str, ...]
    ) -> list[DirectoryRow]:
        """The rows that name `unit` at the tier asked for. When several do, those in the
        geographic area of its division are kept, then those of the same kind of body as the
        census type says."""
        forms = {form for name in unit.names for form in self.naming.forms(name)}
        found = {
            id(row): row
            for form in forms
            for row in self.by_form.get(form, [])
            if (row.status == UPPER_TIER) == upper
        }
        rows = list(found.values())
        if len(rows) > 1:
            areas = {form for name in area_names for form in self.naming.forms(name)}
            in_area = [row for row in rows if self.naming.forms(row.area) & areas]
            rows = in_area or rows
        if len(rows) > 1:
            same_kind = [
                row
                for row in rows
                if not self.naming.designators_differ([row.name], [fallback_government(unit)])
            ]
            rows = same_kind or rows
        return rows

    def named(self, title: str) -> DirectoryRow:
        for row in self.rows:
            if row.name == title:
                return row
        raise ListFileError(f"an override names a directory row that is not there: {title!r}")


def fallback_government(unit: Counted) -> str:
    """The government's name the census type gives when the directory has no row: "Township of
    Elmwood"."""
    designator = MUNICIPAL_TYPES.get(unit.type_) or UPPER_TIER_TYPES.get(unit.type_)
    return unit.names[0] if designator is None else f"{designator} of {unit.names[0]}"


# --- Building ---


@dataclass
class Draft:
    """One place as it is put together, before it becomes a `PlaceEntry`."""

    unit: Counted
    level: str
    parent: str
    name: str
    aliases: list[AliasEntry] = field(default_factory=list)
    government: str | None = None
    homepage: str | None = None
    row: DirectoryRow | None = None

    def take(self, row: DirectoryRow, naming: Naming) -> None:
        """The government's name and homepage from the directory's row."""
        written = naming.written_forms(row.name)
        self.row = row
        self.government = written[0]
        self.homepage = row.homepage
        if len(written) > 1:
            self.alias(written[-1])

    def alias(self, text: str, language: str = "en") -> None:
        if text != self.name and all(alias.text != text for alias in self.aliases):
            self.aliases.append(AliasEntry(text=text, language=language))

    def entry(self) -> PlaceEntry:
        place = Citation(source=POPULATION.name, line=self.unit.line)
        citations: dict[Fact, Citation] = {"place": place}
        if self.row is not None:
            directory = Citation(source=DIRECTORY.name, line=self.row.line)
            citations["government"] = directory
            if self.homepage is not None:
                citations["homepage"] = directory
        figures = ()
        if self.unit.population is not None:
            figures = (
                Figure(
                    name=MetricName.POPULATION,
                    year=CENSUS_YEAR,
                    value=Decimal(self.unit.population),
                    citation=place,
                ),
            )
        return PlaceEntry(
            name=self.name,
            aliases=tuple(self.aliases),
            level=self.level,
            parent=self.parent,
            government=self.government,
            code=Code(scheme=IdentifierScheme.STATCAN_SGC, value=self.unit.code),
            figures=figures,
            homepage=self.homepage if self.row is not None else None,
            citations=citations,
        )


@dataclass
class Notes:
    """What the build dropped, could not match or corrected, logged for the operator."""

    dropped: Counter[str] = field(default_factory=Counter)
    census_only: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)
    overrides: list[str] = field(default_factory=list)
    idle_overrides: list[str] = field(default_factory=list)

    def log(self, directory: Directory) -> None:
        for type_, count in sorted(self.dropped.items()):
            logger.info(
                "left out %d %s subdivisions (%s)", count, DROPPED_TYPES.get(type_, type_), type_
            )
        for line in self.census_only:
            logger.info("no place for census-only division %s", line)
        for line in self.unmatched:
            logger.info("no directory row for %s", line)
        for line in self.ambiguous:
            logger.warning("several directory rows name %s", line)
        for line in self.overrides:
            logger.info("override: %s", line)
        for line in self.idle_overrides:
            logger.warning("override changed nothing: %s", line)
        for row in directory.rows:
            if row.name not in directory.taken:
                logger.info(
                    "directory row no place took: %s (%s, %s)", row.name, row.status, row.area
                )


class Builder:
    def __init__(self, naming: Naming, directory: Directory, notes: Notes) -> None:
        self.naming = naming
        self.directory = directory
        self.notes = notes
        self.applied: set[str] = set()

    def draft(self, unit: Counted, *, level: str, parent: str) -> Draft:
        """A place named as the census does, with its French name as an alias."""
        draft = Draft(unit=unit, level=level, parent=parent, name=unit.names[0])
        for name in unit.names[1:]:
            draft.alias(name, "fr")
        return draft

    def from_directory(
        self, unit: Counted, found: list[DirectoryRow], *, level: str, parent: str
    ) -> Draft:
        """A place with its government named and linked as the directory does, or, when no row or
        several name it, named from its census type."""
        draft = self.draft(unit, level=level, parent=parent)
        if len(found) == 1:
            self.directory.taken.add(found[0].name)
            draft.take(found[0], self.naming)
            return draft
        draft.government = fallback_government(unit)
        label = f"{unit.code} {unit.names[0]} ({unit.type_})"
        if found:
            self.notes.ambiguous.append(f"{label}: {', '.join(row.name for row in found)}")
        else:
            self.notes.unmatched.append(f"{label}, written as {draft.government!r}")
        return draft

    def override(self, draft: Draft) -> None:
        fields = OVERRIDES.get(draft.unit.code)
        if fields is None:
            return
        before = (draft.name, draft.parent, draft.government, draft.homepage)
        if "directory" in fields:
            row = self.directory.named(fields["directory"])
            self.directory.taken.add(row.name)
            draft.take(row, self.naming)
            self.notes.unmatched = [
                line for line in self.notes.unmatched if not line.startswith(draft.unit.code)
            ]
        if "name" in fields:
            census_name = draft.name
            draft.name = fields["name"]
            draft.alias(census_name)
            draft.aliases = [alias for alias in draft.aliases if alias.text != draft.name]
        if "parent" in fields:
            draft.parent = fields["parent"]
        if "government" in fields:
            draft.government = fields["government"]
        if "homepage" in fields:
            draft.homepage = fields["homepage"]
        after = (draft.name, draft.parent, draft.government, draft.homepage)
        label = f"{draft.unit.code} {draft.name}: {fields['reason']}"
        if before == after:
            self.notes.idle_overrides.append(label)
        else:
            self.notes.overrides.append(label)
        self.applied.add(draft.unit.code)


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[PlaceEntry]:
    """Ontario's regions and municipalities, regions first."""
    naming = rules.naming
    counted = _read_population(files[POPULATION.name])
    _read_types(counted, files[ATTRIBUTES.name])
    notes = Notes()
    directory = Directory(_read_directory(files[DIRECTORY.name]), naming)
    builder = Builder(naming, directory, notes)

    divisions = {
        unit.code: unit
        for unit in counted.values()
        if unit.division is None and unit.code != PROVINCE_CODE
    }
    subdivisions = sorted(
        (unit for unit in counted.values() if unit.division is not None), key=lambda u: u.code
    )

    regions: list[PlaceEntry] = []
    region_names: dict[str, str] = {}
    for code, division in sorted(divisions.items()):
        if division.type_ == CENSUS_ONLY_TYPE:
            inside = sorted(
                unit.names[0]
                for unit in subdivisions
                if unit.division == code and unit.type_ in MUNICIPAL_TYPES
            )
            notes.census_only.append(f"{code} {division.names[0]}: {', '.join(inside)}")
            continue
        if division.type_ == DISTRICT_TYPE:
            draft = builder.draft(division, level=REGION, parent=PROVINCE)
        elif division.type_ in UPPER_TIER_TYPES:
            found = directory.find(division, upper=True, area_names=division.names)
            draft = builder.from_directory(division, found, level=REGION, parent=PROVINCE)
        else:
            raise ListFileError(f"census division {code} has an unknown type {division.type_!r}")
        builder.override(draft)
        region_names[code] = draft.name
        regions.append(draft.entry())

    municipalities: list[PlaceEntry] = []
    for unit in subdivisions:
        if unit.type_ not in MUNICIPAL_TYPES:
            notes.dropped[unit.type_] += 1
            continue
        division_code = unit.division or ""
        division = divisions[division_code]
        parent = region_names.get(division_code, PROVINCE)
        found = directory.find(unit, upper=False, area_names=division.names)
        draft = builder.from_directory(unit, found, level=MUNICIPALITY, parent=parent)
        builder.override(draft)
        municipalities.append(draft.entry())

    for code, fields in OVERRIDES.items():
        if code not in builder.applied:
            notes.idle_overrides.append(f"{code}: {fields['reason']} (no such place)")
    notes.log(directory)
    return [*sorted(regions, key=lambda e: e.name), *sorted(municipalities, key=lambda e: e.name)]
