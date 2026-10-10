"""Alberta's places from Statistics Canada's 2021 Census and the province's *Local Authority
Contact Information* export: about 320 municipalities, each with its code, its 2021 population,
its government's legal name and, where the export links one, its website as a candidate
homepage; the three special areas as places the Special Areas Board governs; and the regional
services commissions as institutions under the province. The province is single-tier: every
municipality sits under Alberta, and a census division is only a census unit.

The census population table gives every unit's code, names and population and the geographic
attribute file says what each unit is (`canada/statcan.py`, shared with every province). The
export is a manual file (`CONTACTS.instructions`): the "Find a municipal official" dashboard
on visualizations.alberta.ca sits behind a captcha and exports its table only by hand, one row
per local authority with its name, kind and website. The province's *Municipal Codes* PDF
(open.alberta.ca) is the official list of the same bodies by kind, but the parser renders each
of its tables as one line per page (table structure is off, spec section 8.3), so no line can
cite one municipality and it is not a source yet; the export carries the kind. The rules:

- A city, town, village, summer village, municipal district or specialized municipality is
  matched to the export's row by name and kind. The government's name is the export's legal
  name ("County of Grande Prairie No. 1", "Municipal District of Pincher Creek No. 9",
  "Regional Municipality of Wood Buffalo", "Strathcona County", "Municipality of Jasper"),
  composed from the kind where the export writes the bare name (Alberta Beach). The place keeps
  the census's name.
- An improvement district (`ID`) is a municipality the province administers: the Minister is
  its council, and it buys as a municipality does (the Improvement District No. 9 of Banff). It
  is loaded as a municipality with the export's name.
- The three special areas (`SA`) are places with no government of their own: the Special Areas
  Board, one body for the three, administers them and is loaded as a `regional_government`
  institution under Alberta serving them, with the export's website.
- A census municipality the export no longer lists has dissolved or amalgamated since the
  census; `OVERRIDES` names each, and an unexplained one is an error. The Town of Diamond
  Valley (Black Diamond and Turner Valley, 2023-01-01) has no census code yet and waits for one.
- Lloydminster is one city in two provinces, incorporated under Alberta's Municipal Government
  Act with its city hall in Alberta: one place under Alberta with the Alberta part's code and
  the two parts' population summed; Saskatchewan's list leaves its part out.
- The export's regional services commissions (water, wastewater and solid waste commissions,
  emergency services commissions, a transit and an airport commission, assessment and planning
  services) are public bodies several municipalities own: each is an institution under Alberta,
  typed by what its name says it does (`public_utility`, `fire_service`, `transit_agency`,
  `airport_authority`), else `other` with the kind as the suggested type. The Métis settlements
  and their General Council are Indigenous governments for a later list, and the local
  government associations are member associations, not public bodies: both are left out and
  counted.
- Indian reserves and Indian settlements are not governments and are left out.
- The website is the export's, given a scheme.

The province refreshes the table weekly, so a re-export differs: a manual file pins no hash.
"""

import logging
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from public_atlas.modules.graph.service import normalize_url
from public_atlas.modules.imports.entries import (
    Citation,
    Fact,
    InstitutionEntry,
    PlaceEntry,
    ServedPlace,
)
from public_atlas.modules.imports.files import Format, ListFile, ListFileError, OpenedFile
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.statcan import (
    ATTRIBUTES,
    MUNICIPALITY,
    POPULATION,
    PROVINCE_LEVEL,
    Counted,
    Draft,
    census_name,
)
from public_atlas.modules.imports.models import Retrieval

if TYPE_CHECKING:
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = statcan.COUNTRY
PROVINCE = "Alberta"
PROVINCE_CODE = "48"
ALBERTA = statcan.Province(PROVINCE_CODE)
SASKATCHEWAN = statcan.Province("47")

CONTACTS = ListFile(
    name="alberta_local_authority_contacts_2026_10_09",
    title=(
        "Alberta Municipal Affairs, Find a municipal official: the Local Authority Contact "
        "Information table, exported 2026-10-09"
    ),
    url="https://visualizations.alberta.ca/t/Municipal-Affairs/views/MunicipalOfficialsSearch",
    format=Format.SPREADSHEET,
    retrieval=Retrieval.MANUAL,
    instructions=(
        "Open the Find a municipal official dashboard on visualizations.alberta.ca (report "
        "41a37e88-38b3-4c10-b685-50ee51675369), tab Contact Info for Official and Organization, "
        "object Local Authority Contact Information, its vertical-ellipsis menu, Export data, "
        "all rows, Excel. Save the file as alberta_local_authority_contacts_2026_10_09.xlsx. "
        "Expect sheet Results with about 427 rows and the columns Name, Type, Website, Email, "
        "Phone, Address, Address (line 2), Municipality, Postal Code, Frequency: 19 cities, 105 "
        "towns, 78 villages, 51 summer villages (two rows twice), 63 municipal districts, 6 "
        "specialized municipalities, 7 improvement districts, the Special Areas Board, 77 "
        "regional services commissions, 8 Métis settlements and their council, and 9 local "
        "government associations. The province refreshes the table weekly, so a re-export "
        "differs; the Website column is what this list is for."
    ),
    min_rows=400,
    filename_override="alberta_local_authority_contacts_2026_10_09.xlsx",
    sheets=("Results",),
    # The e-mail addresses, phone numbers and addresses stay out of the stored text.
    columns=("Name", "Type", "Website"),
)
SOURCES = (POPULATION, ATTRIBUTES, CONTACTS)

MUNICIPAL_TYPES = ALBERTA.municipal_types
DROPPED_TYPES = ALBERTA.dropped_types
IMPROVEMENT_DISTRICT = "ID"
SPECIAL_AREA = "SA"
# The export's kinds, each with the census type it answers to.
KINDS: dict[str, str] = {
    "City": "CY",
    "Town": "T",
    "Village": "VL",
    "Summer Village": "SV",
    "Municipal District": "MD",
    "Specialized Municipality": "SM",
    "Improvement District": IMPROVEMENT_DISTRICT,
}
SPECIAL_AREAS_BOARD = "Special Areas Board"
SPECIAL_AREA_KIND = "Special Area"
COMMISSION = "Regional Services Commission"
METIS_SETTLEMENT = "Metis Settlement"
ASSOCIATION = "Local Government Association"
REGIONAL_GOVERNMENT = "regional_government"
# What a commission's name says it does, in the order tried; a name saying none is `other`.
COMMISSION_TYPES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\b(?:water|wastewater|sewage|sewer|lagoon|utilit)", re.IGNORECASE),
        "public_utility",
    ),
    (re.compile(r"\b(?:waste|landfill)\b", re.IGNORECASE), "public_utility"),
    (re.compile(r"\b(?:fire|emergency|public safety)\b", re.IGNORECASE), "fire_service"),
    (re.compile(r"\btransit\b", re.IGNORECASE), "transit_agency"),
    (re.compile(r"\bairport\b", re.IGNORECASE), "airport_authority"),
)
# The export's leading designators, taken off to find the census name inside a legal name.
_DESIGNATOR = re.compile(
    r"^(?:City|Town|Village|Summer Village|Municipal District|County|Municipality|"
    r"Regional Municipality|Improvement District) of (?:the )?",
    re.IGNORECASE,
)
_NOISE = re.compile(r"\b(?:county|improvement district|no\.?)\b|[()]", re.IGNORECASE)
# A name that carries a designator of its own; one that does not (Alberta Beach) is composed.
_DESIGNATED = re.compile(r"\b(?:County|City|Town|Village|Municipality|District)\b", re.IGNORECASE)
# A numbered improvement district is known by its number: the census writes "Improvement
# District No. 12 Jasper Park", the export "Improvement District No. 12 (Jasper National Park)".
_IMPROVEMENT_DISTRICT = re.compile(r"^Improvement District No\.?\s*(?P<number>\d+)", re.IGNORECASE)
# The city shared with Saskatchewan: the Alberta part's census code and the Saskatchewan part's.
LLOYDMINSTER = "4810039"
LLOYDMINSTER_SASKATCHEWAN = "4717029"

# Hand corrections keyed by census code, each with its reason: `dissolved`, for a census
# municipality the export no longer lists, with what it became part of.
OVERRIDES: dict[str, dict[str, str]] = {
    "4819008": {
        "dissolved": "County of Grande Prairie No. 1",
        "reason": "the Village of Hythe dissolved into the County of Grande Prairie No. 1 on "
        "2021-07-01, after the census",
    },
    "4806011": {
        "dissolved": "Town of Diamond Valley",
        "reason": "the Town of Black Diamond amalgamated with Turner Valley as the Town of "
        "Diamond Valley on 2023-01-01; the new town has no census code yet",
    },
    "4806009": {
        "dissolved": "Town of Diamond Valley",
        "reason": "the Town of Turner Valley amalgamated with Black Diamond as the Town of "
        "Diamond Valley on 2023-01-01; the new town has no census code yet",
    },
    "4809010": {
        "dissolved": "Clearwater County",
        "reason": "the Village of Caroline dissolved into Clearwater County on 2025-01-01",
    },
    "4807016": {
        "dissolved": "County of Paintearth No. 18",
        "reason": "the Village of Halkirk dissolved into the County of Paintearth No. 18 on "
        "2025-01-01",
    },
    "4812038": {
        "dissolved": "Municipal District of Bonnyville No. 87",
        "reason": "Improvement District No. 349 dissolved into the Municipal District of "
        "Bonnyville No. 87 on 2021-05-01, after the census",
    },
}


@dataclass(frozen=True)
class Row:
    name: str
    kind: str
    homepage: str | None
    line: int

    @property
    def census_type(self) -> str | None:
        return KINDS.get(self.kind)


def read_rows(opened: OpenedFile) -> list[Row]:
    """The export's rows, each once: the export repeats two summer villages."""
    rows: list[Row] = []
    seen: set[tuple[str, str]] = set()
    for row in opened.rows:
        name = " ".join(row["Name"].split())
        if (name, row["Type"]) in seen:
            continue
        seen.add((name, row["Type"]))
        site = row["Website"].strip()
        rows.append(
            Row(
                name=name,
                kind=row["Type"],
                homepage=normalize_url(site) if site else None,
                line=row.line,
            )
        )
    return rows


def key(name: str) -> str:
    """A name as the census and the export are compared: the designator and the words that
    vary between the two taken off ("Municipal District of Pincher Creek No. 9" and "Pincher
    Creek No. 9" are "pincher creek 9"); a numbered improvement district by its number."""
    numbered = _IMPROVEMENT_DISTRICT.match(name)
    if numbered is not None:
        return f"improvement district {int(numbered.group('number'))}"
    name = _NOISE.sub(" ", _DESIGNATOR.sub("", name))
    words = [word.lstrip("0") or "0" if word.isdigit() else word for word in name.lower().split()]
    return " ".join(re.sub(r"[^a-z0-9]+", " ", " ".join(words)).split())


def commission_type(name: str) -> str | None:
    for pattern, institution_type in COMMISSION_TYPES:
        if pattern.search(name):
            return institution_type
    return None


@dataclass
class Notes:
    dropped: Counter[str] = field(default_factory=Counter)
    dissolved: list[str] = field(default_factory=list)
    composed: list[str] = field(default_factory=list)
    special_areas: list[str] = field(default_factory=list)
    commissions: Counter[str] = field(default_factory=Counter)
    export_dropped: Counter[str] = field(default_factory=Counter)
    untaken: list[str] = field(default_factory=list)

    def log(self) -> None:
        for type_, count in sorted(self.dropped.items()):
            logger.info(
                "left out %d %s subdivisions (%s)", count, DROPPED_TYPES.get(type_, type_), type_
            )
        for line in self.dissolved:
            logger.info("override: %s", line)
        for line in self.composed:
            logger.info("government composed from the kind: %s", line)
        for line in self.special_areas:
            logger.info("special area, governed by the Special Areas Board: %s", line)
        for type_, count in sorted(self.commissions.items()):
            logger.info("%d regional services commissions typed %s", count, type_)
        for kind, count in sorted(self.export_dropped.items()):
            logger.info("left out %d export rows of kind %r", count, kind)
        for line in self.untaken:
            logger.warning("export row no place took: %s", line)


class Builder:
    def __init__(self, files: Mapping[str, OpenedFile]) -> None:
        self.census = ALBERTA.read(files)
        self.saskatchewan = SASKATCHEWAN.read(files)
        self.rows = read_rows(files[CONTACTS.name])
        self.notes = Notes()
        self.by_key: dict[tuple[str, str], Row] = {}
        for row in self.rows:
            type_ = row.census_type
            if type_ is not None:
                self.by_key[(key(row.name), type_)] = row
        self.taken: set[int] = set()

    def places(self) -> list[PlaceEntry]:
        found = []
        for unit in self.census.subdivisions:
            if unit.type_ == SPECIAL_AREA:
                self.notes.special_areas.append(f"{unit.code} {unit.names[0]}")
                found.append(Draft(unit=unit, name=census_name(unit), parent=PROVINCE).entry())
                continue
            if unit.type_ not in MUNICIPAL_TYPES and unit.type_ != IMPROVEMENT_DISTRICT:
                self.notes.dropped[unit.type_] += 1
                continue
            fields = OVERRIDES.get(unit.code, {})
            if "dissolved" in fields:
                self.notes.dissolved.append(f"{unit.code} {unit.names[0]}: {fields['reason']}")
                continue
            row = self.by_key.get((key(census_name(unit)), unit.type_))
            if row is None:
                raise ListFileError(
                    f"{CONTACTS.name}: no row for census municipality {unit.code} "
                    f"{unit.names[0]} ({unit.type_}) and no override says what became of it"
                )
            self.taken.add(row.line)
            found.append(self._municipality(unit, row))
        for row in self.rows:
            if row.census_type is not None and row.line not in self.taken:
                self.notes.untaken.append(f"{row.name} ({row.kind})")
        return sorted(found, key=lambda entry: entry.name)

    def _municipality(self, unit: Counted, row: Row) -> PlaceEntry:
        name = census_name(unit)
        draft = Draft(unit=unit, name=name, parent=PROVINCE)
        citation = Citation(source=CONTACTS.name, line=row.line)
        if _DESIGNATED.search(row.name) is None:
            draft.government = f"{row.kind} of {name}"
            self.notes.composed.append(f"{unit.code} {row.name} -> {draft.government}")
        else:
            draft.government = row.name
        draft.government_citation = citation
        draft.homepage = row.homepage
        draft.homepage_citation = citation
        if unit.code == LLOYDMINSTER:
            part = self.saskatchewan.unit(LLOYDMINSTER_SASKATCHEWAN)
            if unit.population is None or part.population is None:
                raise ListFileError("Lloydminster: a part has no population")
            draft.population = unit.population + part.population
        return draft.entry()

    def institutions(self) -> list[InstitutionEntry]:
        """The Special Areas Board and the regional services commissions."""
        found = []
        special_areas = [unit for unit in self.census.subdivisions if unit.type_ == SPECIAL_AREA]
        for row in self.rows:
            if row.census_type is not None:
                continue
            citation = Citation(source=CONTACTS.name, line=row.line)
            citations: dict[Fact, Citation] = {"institution": citation}
            if row.homepage is not None:
                citations["homepage"] = citation
            if row.kind == SPECIAL_AREA_KIND:
                if row.name != SPECIAL_AREAS_BOARD:
                    raise ListFileError(
                        f"{CONTACTS.name}: unexpected special area row {row.name!r}"
                    )
                found.append(
                    InstitutionEntry(
                        name=row.name,
                        institution_type=REGIONAL_GOVERNMENT,
                        place=PROVINCE,
                        place_level=PROVINCE_LEVEL,
                        served_places=tuple(
                            ServedPlace(name=census_name(unit), level=MUNICIPALITY, parent=PROVINCE)
                            for unit in special_areas
                        ),
                        homepage=row.homepage,
                        citations=citations,
                    )
                )
            elif row.kind == COMMISSION:
                institution_type = commission_type(row.name)
                self.notes.commissions[institution_type or "other"] += 1
                found.append(
                    InstitutionEntry(
                        name=row.name,
                        institution_type=institution_type or "other",
                        suggested_type=None if institution_type else COMMISSION,
                        place=PROVINCE,
                        place_level=PROVINCE_LEVEL,
                        homepage=row.homepage,
                        citations=citations,
                    )
                )
            else:
                self.notes.export_dropped[row.kind] += 1
        return sorted(found, key=lambda entry: entry.name)


def build(files: Mapping[str, OpenedFile]) -> tuple[list[PlaceEntry | InstitutionEntry], Notes]:
    builder = Builder(files)
    places = builder.places()
    institutions = builder.institutions()
    return [*places, *institutions], builder.notes


def entries(
    files: Mapping[str, OpenedFile], rules: CountryRules
) -> list[PlaceEntry | InstitutionEntry]:
    """Alberta's municipalities and special areas, then the Special Areas Board and the
    regional services commissions."""
    del rules
    found, notes = build(files)
    notes.log()
    return found
