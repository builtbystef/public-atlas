"""The places the two places lists load (`us/states_counties`, `us/municipalities`), read
again from SUB-EST2025 for the lists that attach bodies to them: a school district to the
county of its office, a special district to its county. A body names its place as the loader
finds it (by name, level and parent), so this index answers with the loaded place's own name
and tells when a name is not one place's.

A body's county is the loaded county place when the county is a government or is consolidated
with its city (`census.ACTIVE`). When it is not (the planning regions of Connecticut, the
counties of Massachusetts and Rhode Island that no longer govern, the census areas of Alaska's
Unorganized Borough, the independent cities of Virginia, Baltimore, St. Louis and Carson City,
the District of Columbia), the body sits under the municipality of its address when one loaded
municipality under the state goes by that name (an independent city's county row names the
city itself), else under the state.
"""

from collections import defaultdict
from dataclasses import dataclass

from public_atlas.modules.countries.naming import Naming
from public_atlas.modules.imports.lists.us import census, municipalities, states_counties
from public_atlas.modules.imports.lists.us.census import (
    COUNTY_LEVEL,
    MUNICIPALITY_LEVEL,
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
    for a state)."""

    name: str
    level: str
    parent: str | None


@dataclass(frozen=True, slots=True)
class Municipality:
    """A loaded municipality: its code (a town and the city inside it share a name, not a
    code), its name, the state and, when it sits under a county, that county's code and name."""

    code: str
    name: str
    state: str
    county: str | None
    county_name: str | None


class Places:
    """The loaded places, indexed for attaching bodies to them."""

    def __init__(self, estimates: Estimates, naming: Naming) -> None:
        self.naming = naming
        self.states = estimates.state_names
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
        for unit, county in self._municipalities(estimates):
            names = self._names(unit)
            county_name = self.counties[county].name if county is not None else None
            found = Municipality(unit.fips, names[0], unit.state, county, county_name)
            for form in self._forms(names):
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

    def municipality(self, state: str, county: str, name: str) -> Attachment | None:
        """The one loaded municipality under the county that goes by `name`, when no other
        municipality under a county of the same name anywhere does: what the loader finds for a
        served place named with its county."""
        found = self._one(self.in_county, state + county, name)
        if found is None or found.county_name is None:
            return None
        same_name = set()
        for form in self.naming.forms(name):
            for county_form in self.naming.forms(found.county_name):
                same_name |= self.by_county_name.get((form, county_form), set())
        if same_name != {found}:
            return None
        return Attachment(found.name, MUNICIPALITY_LEVEL, found.county_name)

    def _one(
        self, index: dict[tuple[str, str], set[Municipality]], under: str, name: str
    ) -> Municipality | None:
        found: set[Municipality] = set()
        for form in self.naming.forms(name):
            found |= index.get((under, form), set())
        return next(iter(found)) if len(found) == 1 else None
