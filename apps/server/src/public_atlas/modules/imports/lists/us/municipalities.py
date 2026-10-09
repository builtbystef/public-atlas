"""The United States' municipalities from the Census Bureau's Vintage 2025 population estimates
(SUB-EST2025): the incorporated places (summary level 162), the towns and townships of the
twenty states where county subdivisions are governments (061) and the consolidated cities
(170), each with its FIPS code, its 2025 population, a government name composed from its census
kind ("Springfield city" is the place Springfield and the City of Springfield) and its parent:
the county holding most of its population when the states and counties list loads that county,
else the state. The 2020 ANSI code files give each unit's class, which the rule test pins per
exception class. The files and their readers are shared with the states and counties list
(`us/census.py`).

Which rows are governments is their functional status (A, B or C; `census.ACTIVE`). The
exception classes of lists-research section 1.3, as rules:

1. Independent cities (class C7, 41: thirty-eight in Virginia, Baltimore, St. Louis and Carson
   City) are places whose county row is a filler the counties list drops, so the city sits under
   its state. The county code (51510 for Alexandria beside its place code 5101000) is not kept:
   a place holds one code per scheme, and the place code is the one the Gazetteer and the Census
   of Governments key on.
2. Consolidated city-counties, two patterns. (a) A consolidated city row (170, eight:
   Indianapolis, Louisville, Nashville, Athens, Augusta, Butte, Greeley County, Milford) is the
   government, loaded with its consolidated-city code; its "(balance)" place (C8, a filler) is
   not loaded, and the places still incorporated inside it stay governments. Its parent is the
   county of its balance. (b) A county consolidated with a place (status C, 33) is loaded by
   the counties list with no government; the place carries the government here (San Francisco,
   Denver, Philadelphia, New Orleans, Anchorage; New York city under Kings County, with the
   other four boroughs as counties nothing governs).
3. A place and the county subdivision coextensive with it: the subdivision row of a city is a
   filler (C5 or C2, status F) and is dropped; a subdivision consolidated with the place inside
   it (T5, status C: 29, Connecticut's twenty cities, Cicero, three Westchester and Monroe
   villages, five Ohio townships absorbed by a city) is merged: the place is the government, the
   subdivision row is not loaded. A town or township that stays a government beside the villages
   inside it (T1) is a place of its own: a town and a village of one name under one county are
   two places, told apart by their governments' designators.
4. Nonfunctioning, inactive and statistical subdivisions (F, I, N, S) are dropped by status.
5. Connecticut: the planning regions are no places, so its 169 towns sit under the state. The
   2020 code file keys its subdivisions by the counties abolished since, so a Connecticut
   subdivision's class is found by state and subdivision code alone.
6. Massachusetts and Rhode Island: a town whose county is no government sits under the state.
7. Alaska: a city in a census area of the Unorganized Borough sits under the state.
8. The District of Columbia: "Washington city" (162, status N) is dropped by status; the
   District is its state-level anchor, which the counties list codes.
9. A place in several counties sits under the one holding most of its population
   (`Estimates.main_county`): the layout's PRIMGEO_FLAG marks the estimates' primitive
   geographies, not a primary county.
10. Louisiana: Baton Rouge and Lafayette (162, status B) are governments beside their parishes.
11. Kalawao County is the counties list's; it holds no municipality.
12. Names collide everywhere (seven cities named Jacksonville): entries are keyed by code, and a
    county parent is named with its state.

A government's name is composed from the kind ("City of X", "Town of X", "Village of X",
"Borough of X", "Township of X", "Charter Township of X", "Municipality of X", "City and Borough
of X", "X Plantation", "X Unified Government"); a unit with no kind (Carson City, Kansas's
numbered townships) is its own name. The overrides name the few the composition gets wrong and
give the consolidated governments the city's plain name as an alias. The Census of Governments'
legal names and websites are the next list's (lists-todo session 5).
"""

import logging
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field

from public_atlas.modules.countries.service import CountryRules
from public_atlas.modules.graph.models import IdentifierScheme
from public_atlas.modules.imports.entries import AliasEntry, Code, PlaceEntry
from public_atlas.modules.imports.files import ListFileError, OpenedFile
from public_atlas.modules.imports.lists.us import census, states_counties
from public_atlas.modules.imports.lists.us.census import (
    COUNTY_LEVEL,
    COUSUB_CODES,
    MUNICIPALITY_LEVEL,
    PLACE_CODES,
    STATE_LEVEL,
    SUB_EST,
    SUMLEV_CONSOLIDATED_CITY,
    SUMLEV_PLACE,
    SUMLEV_SUBDIVISION,
    Estimates,
    Unit,
)

logger = logging.getLogger(__name__)

COUNTRY = "US"
SOURCES = (SUB_EST, PLACE_CODES, COUSUB_CODES)
CONNECTICUT = "09"
CONSOLIDATED = "C"
BALANCE = "F"
# The class of a place independent of any county.
INDEPENDENT_CITY = "C7"


@dataclass(frozen=True, slots=True)
class Parent:
    """A place's parent as the entry names it: by name, level and the parent's own parent."""

    name: str
    level: str
    parent: str | None


# Hand corrections, keyed by FIPS code, each with its reason. Fields: `name`, `government`,
# `alias` (a further name of the place).
OVERRIDES: dict[str, dict[str, str]] = {
    "3460900": {
        "government": "Municipality of Princeton",
        "reason": "the census writes 'Princeton' with no kind; the merged borough and township "
        "are the Municipality of Princeton",
    },
    "5466988": {
        "name": "Ranson",
        "government": "City of Ranson",
        "reason": "the census writes 'Ranson corporation'; the city styles itself the City of "
        "Ranson",
    },
    "3011390": {
        "government": "City and County of Butte-Silver Bow",
        "alias": "Butte",
        "reason": "the census writes 'Butte-Silver Bow' with no kind",
    },
    "0667000": {
        "government": "City and County of San Francisco",
        "reason": "the city is consolidated with its county; the census writes 'San Francisco "
        "city'",
    },
    "0820000": {
        "government": "City and County of Denver",
        "reason": "the city is consolidated with its county; the census writes 'Denver city'",
    },
    "0809280": {
        "government": "City and County of Broomfield",
        "reason": "the city is consolidated with its county; the census writes 'Broomfield city'",
    },
    "1319000": {
        "government": "Columbus Consolidated Government",
        "reason": "the city is consolidated with Muscogee County; the census writes 'Columbus "
        "city'",
    },
    "2036000": {
        "government": "Unified Government of Wyandotte County and Kansas City",
        "reason": "the city is consolidated with Wyandotte County; the census writes 'Kansas "
        "City city'",
    },
    "1303436": {"alias": "Athens", "reason": "the consolidated city is known by its city's name"},
    "1304200": {"alias": "Augusta", "reason": "the consolidated city is known by its city's name"},
    "2148003": {
        "alias": "Louisville",
        "reason": "the consolidated city is known by its city's name",
    },
    "4752004": {
        "alias": "Nashville",
        "reason": "the consolidated city is known by its city's name",
    },
    "2146027": {
        "alias": "Lexington",
        "reason": "the urban county government is known by its city's name",
    },
    "1349008": {
        "alias": "Macon",
        "reason": "the consolidated government is known by its city's name",
    },
    "3001675": {
        "alias": "Anaconda",
        "reason": "the consolidated government is known by its city's name",
    },
    "4732742": {
        "alias": "Hartsville",
        "reason": "the consolidated government is known by its city's name",
    },
    "4744382": {
        "alias": "Lynchburg",
        "reason": "the metropolitan government is known by its city's name",
    },
    "1321017": {"alias": "Cusseta", "reason": "the unified government is known by its city's name"},
    "1332528": {
        "alias": "Georgetown",
        "reason": "the unified government is known by its city's name",
    },
}


@dataclass
class Notes:
    """What the build dropped, merged or corrected, logged for the operator and pinned by the
    rule test."""

    # Places and subdivisions by their 2020 class and functional status.
    place_classes: Counter[tuple[str, str]] = field(default_factory=Counter)
    subdivision_classes: Counter[tuple[str, str]] = field(default_factory=Counter)
    # The loaded units by the census kind of their name.
    kinds: Counter[str | None] = field(default_factory=Counter)
    # The units dropped, by summary level and functional status.
    dropped: Counter[tuple[str, str]] = field(default_factory=Counter)
    # Subdivisions consolidated with the place inside them, with that place.
    merged: list[str] = field(default_factory=list)
    # Places under their state, by why: their county is no loaded place.
    under_state: list[str] = field(default_factory=list)
    independent_cities: list[str] = field(default_factory=list)
    # Places under a county consolidated with its city (rule 2b): the city and any place still
    # incorporated beside it.
    in_consolidated_county: list[str] = field(default_factory=list)
    # The consolidated city rows (rule 2a).
    consolidated_cities: list[str] = field(default_factory=list)
    overrides: list[str] = field(default_factory=list)

    def log(self) -> None:
        for (sumlev, status), count in sorted(self.dropped.items()):
            logger.info(
                "left out %d rows of level %s (%s)",
                count,
                sumlev,
                census.FUNCTIONAL_STATUS.get(status, status),
            )
        for line in self.merged:
            logger.info("merged into its place: %s", line)
        logger.info(
            "%d places sit under their state, %d of them independent cities",
            len(self.under_state),
            len(self.independent_cities),
        )
        for line in self.overrides:
            logger.info("override: %s", line)


class Builder:
    def __init__(self, estimates: Estimates, notes: Notes) -> None:
        self.estimates = estimates
        self.notes = notes
        # The counties a municipality may sit under: loaded by the counties list at the county
        # level.
        self.counties = {
            code: unit
            for code, unit in estimates.active_counties().items()
            if code not in states_counties.PROMOTED_COUNTIES
        }

    def parent(self, unit: Unit, county: str | None) -> Parent:
        """The place's parent: the county when it is a loaded county place, else the state."""
        label = f"{unit.fips} {unit.name}, {unit.state_name}"
        if county is not None and unit.state + county in self.counties:
            found = self.counties[unit.state + county]
            if found.funcstat == CONSOLIDATED:
                self.notes.in_consolidated_county.append(label)
            return Parent(found.name, COUNTY_LEVEL, unit.state_name)
        self.notes.under_state.append(label)
        return Parent(unit.state_name, STATE_LEVEL, None)

    def entry(self, unit: Unit, county: str | None, code: str) -> PlaceEntry:
        base, kind = census.split_name(unit.name)
        self.notes.kinds[kind] += 1
        name = base
        government = census.legal_name(base, kind)
        aliases: list[AliasEntry] = []
        fields = OVERRIDES.get(code, {})
        if "name" in fields:
            name = fields["name"]
            aliases.append(AliasEntry(text=unit.name))
        if "government" in fields:
            government = fields["government"]
        if "alias" in fields:
            aliases.append(AliasEntry(text=fields["alias"]))
        if fields:
            self.notes.overrides.append(f"{code} {unit.name}: {fields['reason']}")
        parent = self.parent(unit, county)
        return PlaceEntry(
            name=name,
            aliases=tuple(aliases),
            level=MUNICIPALITY_LEVEL,
            parent=parent.name,
            parent_level=parent.level,
            parent_parent=parent.parent,
            government=government,
            code=Code(scheme=IdentifierScheme.FIPS, value=code),
            figures=(unit.figure,),
            citations={"place": unit.citation},
        )

    def place(self, unit: Unit, class_: str) -> PlaceEntry:
        county = self.estimates.main_county(unit)
        label = f"{unit.fips} {unit.name}, {unit.state_name}"
        if county is None:
            raise ListFileError(f"{SUB_EST.name}: no county part for {label}")
        if class_ == INDEPENDENT_CITY:
            self.notes.independent_cities.append(label)
        return self.entry(unit, county, unit.fips)

    def subdivision(self, unit: Unit) -> PlaceEntry:
        return self.entry(unit, unit.county, unit.fips)

    def consolidated_city(self, unit: Unit) -> PlaceEntry:
        """The government of a consolidated city, under the county of its balance."""
        parts = self.estimates.consolidated_parts.get((unit.state, unit.concit), [])
        balances = [
            part for part in parts if part.funcstat == BALANCE and census.is_part(part.name)
        ]
        if len(balances) != 1:
            raise ListFileError(f"{SUB_EST.name}: {unit.name} has {len(balances)} balance rows")
        self.notes.consolidated_cities.append(f"{unit.fips} {unit.name}, {unit.state_name}")
        return self.entry(unit, self.estimates.main_county(balances[0]), unit.fips)

    def places(self, classes: Mapping[tuple[str, ...], str]) -> list[PlaceEntry]:
        """The incorporated places that are governments."""
        found = []
        for unit in self.estimates.units(SUMLEV_PLACE):
            class_ = classes.get((unit.state, unit.place), "?")
            self.notes.place_classes[class_, unit.funcstat] += 1
            if not unit.active:
                self.notes.dropped[SUMLEV_PLACE, unit.funcstat] += 1
                continue
            found.append(self.place(unit, class_))
        return found

    def subdivisions(self, classes: Mapping[tuple[str, ...], str]) -> list[PlaceEntry]:
        """The county subdivisions that are governments of their own; one consolidated with the
        place inside it is merged (rule 3)."""
        # Connecticut's by state and subdivision alone (rule 5).
        connecticut = {
            (state, cousub): class_
            for (state, _, cousub), class_ in classes.items()
            if state == CONNECTICUT
        }
        found = []
        for unit in self.estimates.units(SUMLEV_SUBDIVISION):
            class_ = classes.get(
                (unit.state, unit.county, unit.cousub),
                connecticut.get((unit.state, unit.cousub), "?"),
            )
            self.notes.subdivision_classes[class_, unit.funcstat] += 1
            if not unit.active:
                self.notes.dropped[SUMLEV_SUBDIVISION, unit.funcstat] += 1
                continue
            if unit.funcstat == CONSOLIDATED:
                if not self.merged(unit):
                    raise ListFileError(
                        f"{SUB_EST.name}: {unit.name}, {unit.state_name} is consolidated with "
                        "no place covering it"
                    )
                continue
            found.append(self.subdivision(unit))
        return found

    def consolidated_cities(self) -> list[PlaceEntry]:
        found = []
        for unit in self.estimates.units(SUMLEV_CONSOLIDATED_CITY):
            if not unit.active:
                self.notes.dropped[SUMLEV_CONSOLIDATED_CITY, unit.funcstat] += 1
                continue
            found.append(self.consolidated_city(unit))
        return found

    def merged(self, unit: Unit) -> bool:
        """Whether a consolidated subdivision is covered by the places inside it, whose
        government is its own: the places' population is the subdivision's."""
        inside = self.estimates.places_within.get((unit.state, unit.county, unit.cousub), [])
        if not inside or sum(part.population for part in inside) != unit.population:
            return False
        self.notes.merged.append(
            f"{unit.fips} {unit.name}, {unit.state_name} -> "
            + ", ".join(part.name for part in inside)
        )
        return True


def build(files: Mapping[str, OpenedFile]) -> tuple[list[PlaceEntry], Notes]:
    """The entries and the notes of the build."""
    notes = Notes()
    builder = Builder(Estimates(files[SUB_EST.name]), notes)
    found = [
        *builder.places(census.read_classes(files[PLACE_CODES.name], "STATEFP", "PLACEFP")),
        *builder.subdivisions(
            census.read_classes(files[COUSUB_CODES.name], "STATEFP", "COUNTYFP", "COUSUBFP")
        ),
        *builder.consolidated_cities(),
    ]
    for code, fields in OVERRIDES.items():
        if not any(line.startswith(f"{code} ") for line in notes.overrides):
            logger.warning("override changed nothing: %s (%s)", code, fields["reason"])
    return found, notes


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[PlaceEntry]:
    """Every municipality, in the files' order."""
    del rules  # The names are composed by the census kind alone.
    found, notes = build(files)
    notes.log()
    return found
