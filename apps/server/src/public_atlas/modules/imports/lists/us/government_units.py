"""The legal names and websites of the United States' county, municipal and township
governments from the 2022 Census of Governments' list of government units (the General Purpose
sheet, 38,736 rows), matched to the places the two places lists load, and a candidate homepage
from the .gov registry for a government the sheet gives none. The entries are the loaded places
again, each with its code, so the loader finds the place by code and adds only what is new: the
legal name as an alias of the government, the Census of Governments id as a `census_gid`
identifier, and the website as a candidate homepage.

The sheet keys a county by state and county code, a municipality by state and place code, and
a township by state, county and county subdivision code (its `FIPS_PLACE` is the subdivision
code). A row whose code the 2025 estimates no longer carry is matched by its name under its
county, else dropped as a unit gone since 2022. The rows the sheet keys otherwise (a consolidated
city by its balance's code, Honolulu by Urban Honolulu's) are overrides; the City of Washington
is the District's government, a state-level anchor, and is left out. A county consolidated with
its city (Echols County) has no government to name.

The legal name is composed from the sheet's designator and the census's spelling of the place
name where the two agree but for case and punctuation ("CITY OF ST MARTIN" is "City of St.
Martin"), else from the sheet's words recased ("CITY OF TEMPLE" beside the census's Temple
City). It is the government's name only as an alias: the loader never renames a government, and
the composed name stays. The sheet's name differs from the composed one in about a thousand
rows, mostly a designator the state's law gives ("TOWN OF LIBERTY" for a village so called by
the census).

The .gov registry (`current-full.csv`, pinned at a commit since the file changes daily) lists a
domain's organization, not an organization's homepage; its City and County rows are matched to
a loaded government by state, the place name inside the organization's name and the designator
group ("Abington Township" is the Township of Abington; "Adams County, IL", "Alachua County
BOCC" and "Ascension Parish Government" are their counties' governments), and the match must be
one government. A government with no website in the sheet takes the registry domain as its
candidate homepage (the first of several by name); one with a website keeps it.
"""

import logging
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field

from public_atlas.modules.countries.naming import Naming
from public_atlas.modules.countries.service import CountryRules
from public_atlas.modules.graph.models import IdentifierScheme
from public_atlas.modules.imports.entries import Citation, Code, Fact, PlaceEntry
from public_atlas.modules.imports.files import Format, ListFile, ListFileError, OpenedFile
from public_atlas.modules.imports.lists.us import governments, municipalities, states_counties
from public_atlas.modules.imports.lists.us.census import (
    COUNTY_LEVEL,
    COUSUB_CODES,
    PLACE_CODES,
    POSTAL_CODES,
)
from public_atlas.modules.imports.lists.us.governments import (
    COUNTY,
    GENERAL_PURPOSE,
    GOVT_UNITS,
    MUNICIPAL,
    GovernmentUnit,
)

logger = logging.getLogger(__name__)

COUNTRY = "US"
DOTGOV = ListFile(
    name="dotgov_registry_2026_10_09",
    title=(
        "Cybersecurity and Infrastructure Security Agency, the .gov registry's list of registered "
        "domains (current-full.csv), as of 2026-10-09"
    ),
    url=(
        "https://raw.githubusercontent.com/cisagov/dotgov-data/"
        "b4cb1970319c9621bb09e50da7cd6538610516a6/current-full.csv"
    ),
    sha256="fe844af95a86b32ef6aa8ffe6471eabf9f81a5817cb788b29b7c863d1422d1fa",
    format=Format.CSV,
    columns=("Domain name", "Domain type", "Organization name", "City", "State"),
    shared_host=True,
)
SOURCES = (GOVT_UNITS, DOTGOV, *states_counties.SOURCES, PLACE_CODES, COUSUB_CODES)
# The registry's domain types that are a government's own.
REGISTRY_TYPES = frozenset({"City", "County"})
# The length of a loaded place's FIPS code by its kind: a county's, a place's or consolidated
# city's, a county subdivision's.
COUNTY_CODE = 5
PLACE_CODE = 7
SUBDIVISION_CODE = 10


# Hand corrections keyed by the loaded place's FIPS code, each with its reason. Fields: `unit`
# (the key the sheet gives the row: state and place code).
OVERRIDES: dict[str, dict[str, str]] = {
    "0947500": {
        "unit": "0947515",
        "reason": "the sheet keys the City of Milford by a place code of its own; the "
        "municipalities list loads the consolidated city by its consolidated-city code",
    },
    "1836000": {
        "unit": "1836003",
        "reason": "the sheet keys Indianapolis by its balance's place code; the government is "
        "the consolidated city",
    },
    "1304200": {
        "unit": "1304204",
        "reason": "the sheet keys Augusta-Richmond County by its balance's place code; the "
        "government is the consolidated city",
    },
    "15003": {
        "unit": "1517000",
        "reason": "the sheet keys the City and County of Honolulu by Urban Honolulu's place "
        "code; the counties list loads it as a municipality by its county code",
    },
    "22109": {
        "unit": "2236255",
        "reason": "the sheet keys the Consolidated Government of Terrebonne by Houma's place "
        "code, a nonfunctioning city; the parish is the government",
    },
}
# Rows left out, by the sheet's key, with the reason.
LEFT_OUT: dict[str, str] = {
    "1150000": "the City of Washington is the District of Columbia's government, the "
    "state-level anchor the seed created",
}

# Words after a government's name in a registry organization name that name the government
# itself ("Adams County Government", "Alachua County BOCC", "Assumption Parish Police Jury").
_BODY_WORDS = (
    "board of county commissioners",
    "board of commissioners",
    "board of supervisors",
    "fiscal court",
    "police jury",
    "commissioners",
    "commission",
    "government",
    "corporation",
    "bocc",
)


@dataclass
class Notes:
    """What the build matched, dropped or corrected, logged for the operator and pinned by the
    rule test."""

    # Sheet rows matched to a loaded place, by unit type and how (code, name, override).
    matched: Counter[tuple[str, str]] = field(default_factory=Counter)
    inactive: int = 0
    left_out: list[str] = field(default_factory=list)
    # Active rows with no loaded place: units gone since 2022.
    no_unit: list[str] = field(default_factory=list)
    # Rows whose place has no government of its own.
    no_government: list[str] = field(default_factory=list)
    overrides: list[str] = field(default_factory=list)
    # Legal names that differ from the composed name, so are added as aliases.
    legal_names: int = 0
    # Governments with a candidate homepage, by level and where it came from.
    homepages: Counter[tuple[str, str]] = field(default_factory=Counter)
    # Loaded governments by level.
    governments: Counter[str] = field(default_factory=Counter)
    # Registry rows matched to one government, to several (skipped) and to none.
    registry: Counter[str] = field(default_factory=Counter)

    def log(self) -> None:
        for (unit_type, how), count in sorted(self.matched.items()):
            logger.info("%d %s rows matched by %s", count, unit_type, how)
        logger.info("left out %d inactive rows", self.inactive)
        for line in self.left_out:
            logger.info("left out %s", line)
        logger.info(
            "%d active rows name no 2025 unit: %s", len(self.no_unit), ", ".join(self.no_unit)
        )
        for line in self.no_government:
            logger.info("no government to name for %s", line)
        for line in self.overrides:
            logger.info("override: %s", line)
        logger.info("%d legal names differ from the composed name", self.legal_names)
        for how, count in sorted(self.registry.items()):
            logger.info("registry rows %s: %d", how, count)
        for level, total in sorted(self.governments.items()):
            sheet = self.homepages[level, GOVT_UNITS.name]
            registry = self.homepages[level, DOTGOV.name]
            logger.info(
                "%s governments: %d, with a candidate homepage %d (%d from the sheet, %d from "
                "the registry)",
                level,
                total,
                sheet + registry,
                sheet,
                registry,
            )


@dataclass(frozen=True, slots=True)
class RegistryRow:
    domain: str
    organization: str
    state: str
    line: int


def read_registry(opened: OpenedFile) -> list[RegistryRow]:
    """The registry's City and County rows."""
    return [
        RegistryRow(
            domain=row["Domain name"].lower(),
            organization=row["Organization name"],
            state=row["State"].upper(),
            line=row.line,
        )
        for row in opened.rows
        if row["Domain type"] in REGISTRY_TYPES
    ]


def registry_key(naming: Naming, organization: str) -> tuple[str, frozenset[int]] | None:
    """A registry organization as the place name inside it and its designator groups, with a
    trailing state or body name taken off; None when it names no government ("Alhambra Fire
    Department", "Arapahoe County Clerk Recorder")."""
    key = naming.without_leading(naming.key(organization))
    # Without a trailing state, then without a trailing body name too, then as written: the
    # first reading in which a designator surrounds a place name ("Lexington-Fayette Urban
    # County Government" keeps its last word, "Henry County Government" loses it, and "Town of
    # Maine" is read whole once "Maine" has been tried as a state).
    without_state = _STATE_SUFFIX.sub("", key)
    for reading in (without_state, _BODY_SUFFIX.sub("", without_state), key):
        groups = naming.designators_in(reading)
        core = naming.core(reading)
        if groups and core != reading:
            return core, frozenset(groups)
    return None


def government_key(naming: Naming, government: str) -> tuple[str, frozenset[int]] | None:
    """A government's name as `registry_key` reads it."""
    groups = naming.designators_in(government)
    if not groups:
        return None
    return naming.core(government), frozenset(groups)


_STATE_NAMES = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
    "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas",
    "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota", "tennessee", "texas",
    "utah", "vermont", "virginia", "washington", "west virginia", "wisconsin", "wyoming",
    "puerto rico",
]  # fmt: skip
_STATE_SUFFIX = re.compile(
    r",?\s+(?:(?:state|commonwealth) of\s+)?(?:"
    + "|".join([*_STATE_NAMES, *(code.lower() for code in POSTAL_CODES.values())])
    + r")$"
)
_BODY_SUFFIX = re.compile(r",?\s+(?:" + "|".join(_BODY_WORDS) + r")$")


def legal_name(unit: GovernmentUnit, place_name: str) -> str:
    """The government's legal name as a page writes it: the sheet's designator, then the
    census's spelling of the place name when it is the sheet's but for case and punctuation,
    else the sheet's words recased."""
    parts = governments.split_legal_name(unit.name)
    if parts is None:
        return governments.title_case(unit.name)
    designator, rest = parts
    base = (
        place_name if governments.same_letters(rest, place_name) else governments.title_case(rest)
    )
    return f"{designator} of {base}"


class Builder:
    def __init__(self, files: Mapping[str, OpenedFile], naming: Naming) -> None:
        self.naming = naming
        self.notes = Notes()
        counties, _ = states_counties.build(files)
        places, _ = municipalities.build(files)
        # The loaded places by code.
        self.loaded: dict[str, PlaceEntry] = {
            entry.code.value: entry for entry in [*counties, *places]
        }
        # The municipalities under a county by the county's code and the key of their name,
        # for the rows whose code the estimates no longer carry.
        county_codes = {
            (entry.parent, entry.name): entry.code.value
            for entry in counties
            if entry.level == COUNTY_LEVEL
        }
        self.by_name: dict[tuple[str, str], list[PlaceEntry]] = defaultdict(list)
        for entry in places:
            if entry.parent_level == COUNTY_LEVEL and entry.parent is not None:
                county = county_codes[entry.parent_parent, entry.parent]
                self.by_name[county, naming.key(entry.name)].append(entry)
        self.units = {fields["unit"]: code for code, fields in OVERRIDES.items()}

    def match(self, unit: GovernmentUnit) -> PlaceEntry | None:
        """The loaded place of a sheet row: by its key, by the override, by its name under its
        county."""
        if unit.key in self.units:
            code = self.units[unit.key]
            self.notes.overrides.append(f"{code} {unit.name}: {OVERRIDES[code]['reason']}")
            self.notes.matched[unit.type_name, "override"] += 1
            return self.loaded[code]
        key = unit.fips_state + unit.fips_county if unit.unit_type == COUNTY else unit.key
        found = self.loaded.get(key)
        if found is not None and self._same_kind(unit, found):
            self.notes.matched[unit.type_name, "code"] += 1
            return found
        parts = governments.split_legal_name(unit.name)
        if parts is not None and unit.unit_type != COUNTY:
            county = unit.fips_state + unit.fips_county
            named = [
                entry
                for entry in self.by_name.get((county, self.naming.key(parts[1])), [])
                if self._same_kind(unit, entry)
            ]
            if len(named) == 1:
                self.notes.matched[unit.type_name, "name"] += 1
                return named[0]
        return None

    @staticmethod
    def _same_kind(unit: GovernmentUnit, entry: PlaceEntry) -> bool:
        """Whether a row's unit type is the loaded place's kind: a county row is a county place
        (or Honolulu), a municipal row a place or consolidated city, a township row a county
        subdivision."""
        if unit.unit_type == COUNTY:
            return len(entry.code.value) == COUNTY_CODE
        if unit.unit_type == MUNICIPAL:
            return len(entry.code.value) == PLACE_CODE
        return len(entry.code.value) == SUBDIVISION_CODE

    def sheet_rows(self, units: list[GovernmentUnit]) -> dict[str, GovernmentUnit]:
        """The active rows by the code of their loaded place."""
        found: dict[str, GovernmentUnit] = {}
        for unit in units:
            label = f"{unit.key} {unit.name}, {unit.state}"
            if not unit.active:
                self.notes.inactive += 1
                continue
            if unit.key in LEFT_OUT:
                self.notes.left_out.append(f"{label}: {LEFT_OUT[unit.key]}")
                continue
            entry = self.match(unit)
            if entry is None:
                self.notes.no_unit.append(label)
                continue
            if entry.code.value in found:
                raise ListFileError(
                    f"{GOVT_UNITS.name}: two rows for {entry.name}: {found[entry.code.value].name} "
                    f"and {unit.name}"
                )
            found[entry.code.value] = unit
        return found

    def registry_matches(self, rows: list[RegistryRow]) -> dict[str, list[tuple[str, int]]]:
        """The registry domains of each loaded government, by the place's code: a row matches
        the one government in its state with the place name and a designator group of its
        organization's name."""
        index: dict[tuple[str, str], list[tuple[str, frozenset[int]]]] = defaultdict(list)
        for code, entry in self.loaded.items():
            postal = POSTAL_CODES.get(code[:2])
            if entry.government is None or postal is None:
                continue
            key = government_key(self.naming, entry.government)
            if key is not None:
                index[postal, key[0]].append((code, key[1]))
        matches: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for row in rows:
            key = registry_key(self.naming, row.organization)
            if key is None:
                self.notes.registry["naming no government"] += 1
                continue
            found = [code for code, groups in index.get((row.state, key[0]), []) if groups & key[1]]
            if len(found) == 1:
                matches[found[0]].append((row.domain, row.line))
                self.notes.registry["matched"] += 1
            elif found:
                self.notes.registry["naming several governments"] += 1
            else:
                self.notes.registry["naming no loaded government"] += 1
        return matches

    def entry(
        self, entry: PlaceEntry, unit: GovernmentUnit | None, domains: list[tuple[str, int]]
    ) -> PlaceEntry | None:
        """The loaded place again, with what the sheet and the registry add."""
        if entry.government is None:
            if unit is not None:
                self.notes.no_government.append(f"{entry.code.value} {unit.name}, {unit.state}")
            return None
        self.notes.governments[entry.level] += 1
        government = entry.government
        citations: dict[Fact, Citation] = {"place": entry.citations["place"]}
        codes: tuple[Code, ...] = ()
        homepage = None
        if unit is not None:
            legal = legal_name(unit, entry.name)
            if self.naming.key(legal) != self.naming.key(government):
                government = legal
                self.notes.legal_names += 1
            citations["government"] = Citation(source=GOVT_UNITS.name, line=unit.line)
            if unit.gid is not None:
                codes = (Code(scheme=IdentifierScheme.CENSUS_GID, value=unit.gid),)
            if unit.website is not None:
                homepage = unit.website
                citations["homepage"] = citations["government"]
                self.notes.homepages[entry.level, GOVT_UNITS.name] += 1
        if homepage is None and domains:
            domain, line = min(domains)
            homepage = f"https://{domain}/"
            citations["homepage"] = Citation(source=DOTGOV.name, line=line)
            self.notes.homepages[entry.level, DOTGOV.name] += 1
        return PlaceEntry(
            name=entry.name,
            aliases=entry.aliases,
            language=entry.language,
            level=entry.level,
            parent=entry.parent,
            parent_level=entry.parent_level,
            parent_parent=entry.parent_parent,
            government=government,
            code=entry.code,
            codes=codes,
            homepage=homepage,
            citations=citations,
        )


def build(files: Mapping[str, OpenedFile], rules: CountryRules) -> tuple[list[PlaceEntry], Notes]:
    """The entries and the notes of the build."""
    builder = Builder(files, rules.naming)
    rows = builder.sheet_rows(governments.read_units(files[GOVT_UNITS.name], GENERAL_PURPOSE))
    matches = builder.registry_matches(read_registry(files[DOTGOV.name]))
    found = []
    for code, entry in builder.loaded.items():
        unit = rows.get(code)
        domains = matches.get(code, [])
        if unit is None and not domains:
            continue
        made = builder.entry(entry, unit, domains)
        if made is not None:
            found.append(made)
    return found, builder.notes


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[PlaceEntry]:
    """Every loaded place the sheet or the registry adds to."""
    found, notes = build(files, rules)
    notes.log()
    return found
