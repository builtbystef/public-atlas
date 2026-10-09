"""The places the two places lists load (`us/states_counties`, `us/municipalities`), read
again from SUB-EST2025 for the lists that attach bodies to them: a school district to the
county of its office, a special district to its county, a transit agency to the city of its
address or to the government it is a department of. A body names its place as the loader
finds it (by name, level and parent), so this index answers with the loaded place's own name
and tells when a name is not one place's.

A body's county is the loaded county place when the county is a government or is consolidated
with its city (`census.ACTIVE`). When it is not (the planning regions of Connecticut, the
counties of Massachusetts and Rhode Island that no longer govern, the census areas of Alaska's
Unorganized Borough, the independent cities of Virginia, Baltimore, St. Louis and Carson City,
the District of Columbia), the body sits under the municipality of its address when one loaded
municipality under the state goes by that name (an independent city's county row names the
city itself), else under the state. Puerto Rico is a state here though the estimates leave it
out; its municipios are not indexed, so a body there sits under Puerto Rico.
"""

from collections import defaultdict
from dataclasses import dataclass

from public_atlas.modules.countries.naming import Naming
from public_atlas.modules.imports.lists.us import (
    census,
    government_units,
    municipalities,
    states_counties,
)
from public_atlas.modules.imports.lists.us.census import (
    COUNTY_LEVEL,
    MUNICIPALITY_LEVEL,
    PUERTO_RICO,
    PUERTO_RICO_CODE,
    STATE_LEVEL,
    SUMLEV_CONSOLIDATED_CITY,
    SUMLEV_COUNTY,
    SUMLEV_PLACE,
    SUMLEV_SUBDIVISION,
    Estimates,
    Unit,
)

# A row the counties list drops, whose name is the place that stands in for it.
FILLER = "F"


@dataclass(frozen=True, slots=True)
class Attachment:
    """A loaded place as an entry names it: by name, level and the name of its parent (None
    for a state). A county may stand in for a municipality the loader cannot tell from
    another of its name (the city and the charter township of Grand Rapids, both under Kent
    County); `instead_of` then names that municipality."""

    name: str
    level: str
    parent: str | None
    instead_of: str | None = None


@dataclass(frozen=True, slots=True)
class Municipality:
    """A loaded municipality: its code (a town and the city inside it share a name, not a
    code), its name, the state and, when it sits under a county, that county's code and name;
    its census kind ("city", "charter township") and the designator groups of its government's
    name, which tell the town from the village of its name."""

    code: str
    name: str
    state: str
    county: str | None
    county_name: str | None
    kind: str | None
    groups: frozenset[int]


class Places:
    """The loaded places, indexed for attaching bodies to them."""

    def __init__(self, estimates: Estimates, naming: Naming) -> None:
        self.naming = naming
        # The estimates leave Puerto Rico out; its places list loads it all the same.
        self.states = {**estimates.state_names, PUERTO_RICO_CODE: PUERTO_RICO}
        self.counties = estimates.active_counties()
        self.county_rows = {unit.fips: unit for unit in estimates.units(SUMLEV_COUNTY)}
        # The loaded municipalities by the forms of their names and aliases, as the loader
        # knows them: those under their state, by state and form; those under a county, by
        # county code and form; and all of them by form and a form of their county's name,
        # which is how the loader reads the parent a served place names ('Union County' finds
        # the places under Union Parish too).
        self.under_state: dict[tuple[str, str], set[Municipality]] = defaultdict(set)
        self.in_county: dict[tuple[str, str], set[Municipality]] = defaultdict(set)
        self.by_county_name: dict[tuple[str, str], set[Municipality]] = defaultdict(set)
        # Every loaded municipality by state and form, wherever it sits, for a body that names
        # its city and state and nothing more.
        self.in_state: dict[tuple[str, str], set[Municipality]] = defaultdict(set)
        # The loaded counties by state and a form of their name, for a body named after one.
        self.counties_in_state: dict[tuple[str, str], set[str]] = defaultdict(set)
        for code, unit in self.counties.items():
            for form in naming.forms(census.split_name(unit.name)[0]):
                self.counties_in_state[unit.state, form].add(code)
        for unit, county in self._municipalities(estimates):
            names = self._names(unit)
            county_name = self.counties[county].name if county is not None else None
            kind = census.split_name(unit.name)[1]
            found = Municipality(
                unit.fips,
                names[0],
                unit.state,
                county,
                county_name,
                kind,
                self._groups(census.legal_name(names[0], kind)),
            )
            for form in self._forms(names):
                self.in_state[unit.state, form].add(found)
                if county is None:
                    self.under_state[unit.state, form].add(found)
                else:
                    self.in_county[county, form].add(found)
                    assert county_name is not None  # noqa: S101 - set with the county
                    for county_form in naming.forms(county_name):
                        self.by_county_name[form, county_form].add(found)

    @staticmethod
    def _names(unit: Unit) -> list[str]:
        """The municipality's loaded name first, then its aliases, as the municipalities list
        gives them: the census name when the list renames the place, and the city's plain name
        for a consolidated government known by it."""
        name, _ = census.split_name(unit.name)
        fields = municipalities.OVERRIDES.get(unit.fips, {})
        names = [fields.get("name", name)]
        if "name" in fields:
            names.append(unit.name)
        if "alias" in fields:
            names.append(fields["alias"])
        return names

    def _groups(self, government: str) -> frozenset[int]:
        return frozenset(self.naming.designators_in(self.naming.key(government)))

    def _forms(self, names: list[str]) -> set[str]:
        found: set[str] = set()
        for name in names:
            found |= self.naming.forms(name)
        return found

    def _municipalities(self, estimates: Estimates) -> list[tuple[Unit, str | None]]:
        """Each loaded municipality with the code of the county it sits under, None for one
        under its state: the places and subdivisions that are governments of their own and the
        consolidated cities, as the municipalities list loads them."""
        found: list[tuple[Unit, str | None]] = [
            (unit, self._county_of(unit.state, estimates.main_county(unit)))
            for unit in estimates.units(SUMLEV_PLACE)
            if unit.active
        ]
        found.extend(
            (unit, self._county_of(unit.state, unit.county))
            for unit in estimates.units(SUMLEV_SUBDIVISION)
            if unit.active and unit.funcstat != "C"
        )

        for unit in estimates.units(SUMLEV_CONSOLIDATED_CITY):
            if not unit.active:
                continue
            parts = estimates.consolidated_parts.get((unit.state, unit.concit), [])
            balance = next((part for part in parts if census.is_part(part.name)), None)
            county = estimates.main_county(balance) if balance is not None else None
            found.append((unit, self._county_of(unit.state, county)))
        return found

    def _county_of(self, state: str, county: str | None) -> str | None:
        """The county code when the county is a loaded county place."""
        if county is None:
            return None
        code = state + county
        if code in self.counties and code not in states_counties.PROMOTED_COUNTIES:
            return code
        return None

    def state(self, fips: str) -> Attachment | None:
        """The state by its FIPS code; None for a territory the seed does not have."""
        name = self.states.get(fips)
        return Attachment(name, STATE_LEVEL, None) if name is not None else None

    def attach(self, state: str, county: str, city: str | None = None) -> Attachment | None:
        """The place a body in the county (and, when given, the city) is attached to: the
        county when it is loaded, else the one loaded municipality under the state the county
        row or the city names, else the state. None for a territory."""
        code = state + county
        unit = self.counties.get(code)
        if unit is not None:
            level = (
                MUNICIPALITY_LEVEL if code in states_counties.PROMOTED_COUNTIES else COUNTY_LEVEL
            )
            return Attachment(unit.name, level, self.states[state])
        row = self.county_rows.get(code)
        for name in (
            census.split_name(row.name)[0] if row is not None and row.funcstat == FILLER else None,
            city,
        ):
            if name is None:
                continue
            found = self._one(self.under_state, state, name)
            if found is not None:
                return Attachment(found.name, MUNICIPALITY_LEVEL, self.states[state])
        return self.state(state)

    def city(self, state: str, name: str) -> Attachment | None:
        """The one loaded municipality in the state that goes by `name`, wherever it sits (a
        body that gives its city and state alone): of several, the city of that name over the
        town or township around it; None when none or several remain. When the loader cannot
        tell the municipality from another of its name, its county stands in."""
        found: set[Municipality] = set()
        for form in self.naming.forms(name):
            found |= self.in_state.get((state, form), set())
        if len(found) > 1:
            cities = {municipality for municipality in found if municipality.kind == "city"}
            found = cities or found
        if len(found) != 1:
            return None
        return self._attachment(found.pop())

    def government(self, state: str, name: str) -> Attachment | None:
        """The place of the one loaded government in the state that `name` names, by the place
        name inside it and its designator group, with a trailing state or body name taken off
        as the .gov registry's organization names are read ("City of Owensboro", "Montezuma
        County", "Forsyth County Board of Commissioners", "City of Springfield, Ohio"); None
        when none or several do. When the loader cannot tell a municipality from another of
        its name, its county stands in."""
        key = government_units.registry_key(self.naming, name)
        if key is None:
            return None
        core, groups = key
        municipalities = {
            municipality
            for municipality in self.in_state.get((state, core), set())
            if municipality.groups & groups
        }
        counties = {
            code
            for code in self.counties_in_state.get((state, core), set())
            - states_counties.PROMOTED_COUNTIES
            if self._groups(self.counties[code].name) & groups
        }
        if len(municipalities) + len(counties) != 1:
            return None
        if municipalities:
            return self._attachment(municipalities.pop())
        return Attachment(self.counties[counties.pop()].name, COUNTY_LEVEL, self.states[state])

    def _attachment(self, found: Municipality) -> Attachment | None:
        """The municipality as the loader finds it, or, when the loader would find another of
        its name too, its county standing in for it; a municipality under its state that
        shares its name is no one place (None)."""
        if self._alone(found):
            parent = (
                found.county_name if found.county_name is not None else self.states[found.state]
            )
            return Attachment(found.name, MUNICIPALITY_LEVEL, parent)
        if found.county_name is None:
            return None
        return Attachment(
            found.county_name, COUNTY_LEVEL, self.states[found.state], instead_of=found.name
        )

    def _alone(self, found: Municipality) -> bool:
        """Whether the loader, given the municipality's name, level and parent, finds it and
        nothing else: under its state, no other municipality of the state goes by the name;
        under a county, none under a county of the same name anywhere does ("Union County"
        finds the places under Union Parish too)."""
        same_name: set[Municipality] = set()
        for form in self.naming.forms(found.name):
            if found.county_name is None:
                same_name |= self.under_state.get((found.state, form), set())
                continue
            for county_form in self.naming.forms(found.county_name):
                same_name |= self.by_county_name.get((form, county_form), set())
        return same_name == {found}

    def municipality(self, state: str, county: str, name: str) -> Attachment | None:
        """The one loaded municipality under the county that goes by `name`, when no other
        municipality under a county of the same name anywhere does: what the loader finds for a
        served place named with its county."""
        found = self._one(self.in_county, state + county, name)
        if found is None or found.county_name is None or not self._alone(found):
            return None
        return Attachment(found.name, MUNICIPALITY_LEVEL, found.county_name)

    def _one(
        self, index: dict[tuple[str, str], set[Municipality]], under: str, name: str
    ) -> Municipality | None:
        found: set[Municipality] = set()
        for form in self.naming.forms(name):
            found |= index.get((under, form), set())
        return next(iter(found)) if len(found) == 1 else None
