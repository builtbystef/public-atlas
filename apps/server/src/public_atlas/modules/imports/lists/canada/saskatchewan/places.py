"""Saskatchewan's places from Statistics Canada's 2021 Census, its interim list of changes and
the province's Municipal Directory: about 757 municipalities, each with its code, its 2021
population, its government's legal name and, where the directory links one, its website as a
candidate homepage. The province is single-tier: every municipality sits under Saskatchewan,
and a census division is only a census unit.

The census population table gives every unit's code, names and population and the geographic
attribute file says what each unit is (`canada/statcan.py`, shared with every province). The
directory on saskatchewan.ca has no export, so it is a manual file (`DIRECTORY.instructions`):
a CSV derived by hand from the 761 municipality pages, one row per municipality with its name,
kind, website and the page it was read from. The rules:

- A city, town, village, resort village, rural municipality, northern town, northern village
  or northern hamlet is matched to the directory's row by name and kind. The directory writes a
  rural municipality in its list form ("Aberdeen, Rural Municipality No. 373"); the place is
  named as the census names it ("Aberdeen No. 373") and the government "Rural Municipality of
  Aberdeen No. 373". Every other government is composed from the directory's kind: "City of
  Regina", "Resort Village of Aquadeo", "Northern Village of Air Ronge", "Northern Hamlet of
  Black Point". The directory's name wins where the two differ in more than case and accents
  (the District of Katepwa, the District of Lakeland No. 521), with the census's as an alias;
  the census's spelling stays where the directory only drops an accent (Roche Percée) or
  capitalizes otherwise.
- A census municipality the directory no longer lists has restructured since the census
  (relinquished its village status to become a hamlet or special service area of its rural
  municipality); `OVERRIDES` names each, and an unexplained one is an error.
- Lloydminster and Flin Flon are one city each in two provinces; the census counts each
  province's part. Lloydminster is loaded under Alberta (`canada/alberta/places`) and Flin Flon
  under Manitoba (`canada/manitoba/places`), each with the Saskatchewan part's population added,
  so this list leaves their Saskatchewan parts out.
- A municipality incorporated since the census is loaded from the interim list when that gives
  its code (the Resort Village of Pasqua Lake, 2024-01-01), with the directory's row and no
  census figure; one the interim list does not yet code (Elk Ridge, Turtle View) waits for the
  code and is counted.
- The Northern Saskatchewan Administration District is the province's administration of the
  unincorporated north, not a municipality. Indian reserves, Indian settlements, unorganized
  areas and the Crown colony are not governments and are left out.
- The website is the directory's link.
"""

import logging
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from public_atlas.modules.graph.models import IdentifierScheme
from public_atlas.modules.graph.service import normalize_url
from public_atlas.modules.imports.entries import Code, Fact, PlaceEntry
from public_atlas.modules.imports.files import Format, ListFile, ListFileError, OpenedFile
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.statcan import (
    ATTRIBUTES,
    INTERIM_CHANGES,
    MUNICIPALITY,
    POPULATION,
    PROVINCE_LEVEL,
    Change,
    Citation,
    Counted,
    Draft,
    census_name,
    read_changes,
)
from public_atlas.modules.imports.models import Retrieval

if TYPE_CHECKING:
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = statcan.COUNTRY
PROVINCE = "Saskatchewan"
PROVINCE_CODE = "47"
SASKATCHEWAN = statcan.Province(PROVINCE_CODE)

DIRECTORY = ListFile(
    name="saskatchewan_municipal_directory_2026_10_09",
    title=(
        "Government of Saskatchewan, Municipal Directory, the 761 municipality pages as read on "
        "2026-10-09"
    ),
    url="https://www.saskatchewan.ca/government/municipal-administration/municipal-directory",
    format=Format.CSV,
    retrieval=Retrieval.MANUAL,
    instructions=(
        "The directory is a Sitecore search application with no export. Open it, follow each "
        "of the nine category links (City, Town, Village, Resort Village, Rural Municipality, "
        "Northern Town, Northern Village, Northern Hamlet, Northern Saskatchewan "
        "Administration District), collect every municipality link (municipal-directory?s={id}) "
        "and save each page's HTML; then write one CSV row per municipality from the saved "
        "pages, with the columns id, name, municipality_type (the category the link was under), "
        "telephone, fax, website (the href of the URL row), email, the addresses, rm_number, "
        "office hours, council meeting time, the contacts, last_updated_on_page, source_url, "
        "fetched_at_utc, page_sha256 and raw_html_file. Save it as "
        "saskatchewan_municipal_directory_2026_10_09.csv; the saved pages and the per-value "
        "evidence log stay beside it outside the repository. Expect 761 rows: 16 cities, 147 "
        "towns, 234 villages, 43 resort villages, 296 rural municipalities, 2 northern towns, "
        "11 northern villages, 11 northern hamlets and the administration district."
    ),
    min_rows=750,
    filename_override="saskatchewan_municipal_directory_2026_10_09.csv",
    # The contacts, addresses and hours stay out of the stored text.
    columns=(
        "id",
        "name",
        "municipality_type",
        "website",
        "rm_number",
        "source_url",
        "page_sha256",
    ),
)
SOURCES = (POPULATION, ATTRIBUTES, INTERIM_CHANGES, DIRECTORY)

MUNICIPAL_TYPES = SASKATCHEWAN.municipal_types
DROPPED_TYPES = SASKATCHEWAN.dropped_types
# The directory's kinds, each with the census type it answers to. A northern town is a town to
# the census.
KINDS: dict[str, str] = {
    "City": "CY",
    "Town": "T",
    "Village": "VL",
    "Resort Village": "RV",
    "Rural Municipality": "RM",
    "Northern Town": "T",
    "Northern Village": "NV",
    "Northern Hamlet": "NH",
}
ADMINISTRATION_DISTRICT = "Northern Saskatchewan Administration District"
RURAL_MUNICIPALITY = re.compile(r"^(?P<name>.+), Rural Municipality No\. (?P<number>\d+)$")
# The census codes of the two cities shared with another province, which load it.
SHARED_CITIES: dict[str, str] = {"4717029": "Alberta", "4718052": "Manitoba"}
INCORPORATION = "Incorporation from part"

# Hand corrections keyed by census code, each with its reason: `dissolved`, for a census
# village the directory no longer lists, with the rural municipality it became part of;
# `directory`, the directory's name for a municipality the census names otherwise, with `name`
# for the place and `government` where the legal name is not composed from the kind.
OVERRIDES: dict[str, dict[str, str]] = {
    "4706050": {
        "directory": "District of Katepwa",
        "name": "District of Katepwa",
        "government": "Resort Village of the District of Katepwa",
        "reason": "the resort village is the District of Katepwa; the census writes Katepwa",
    },
    "4715075": {
        "directory": "District of Lakeland, Rural Municipality No. 521",
        "name": "District of Lakeland No. 521",
        "government": "District of Lakeland No. 521",
        "reason": "the rural municipality is the District of Lakeland No. 521; the census "
        "writes Lakeland No. 521",
    },
    **{
        code: {
            "dissolved": into,
            "reason": f"the village {when}, becoming part of the {into}; the directory no "
            "longer lists it",
        }
        for code, into, when in (
            ("4708036", "RM of Riverside No. 168", "relinquished its status on 2022-07-15"),
            ("4708049", "RM of Miry Creek No. 229", "relinquished its status on 2022-08-01"),
            ("4708039", "RM of Saskatchewan Landing No. 167", "dissolved on 2023-07-01"),
            ("4708057", "RM of Happyland No. 231", "relinquished its status on 2024-07-01"),
            (
                "4713053",
                "RM of Eye Hill No. 382",
                "relinquished its status on 2015-12-31 (the census still carried it)",
            ),
            ("4701012", "RM of Enniskillen No. 3", "restructured since the census"),
            ("4702008", "RM of Souris Valley No. 7", "restructured since the census"),
            ("4703051", "RM of Pinto Creek No. 75", "restructured since the census"),
            ("4705068", "RM of Stanley No. 215", "restructured since the census"),
            ("4705049", "RM of Langenburg No. 181", "restructured since the census"),
            ("4706062", "RM of Dufferin No. 190", "restructured since the census"),
            ("4708054", "RM of Clinworth No. 230", "restructured since the census"),
            ("4709076", "RM of Livingston No. 331", "restructured since the census"),
            ("4710072", "RM of Sasman No. 336", "restructured since the census"),
            ("4710028", "RM of Mount Hope No. 279", "restructured since the census"),
            ("4711094", "RM of Viscount No. 341", "restructured since the census"),
            ("4716002", "RM of Mayfield No. 406", "restructured since the census"),
        )
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

    @property
    def place_name(self) -> str:
        """The name as the census writes it: "Aberdeen No. 373" for the directory's "Aberdeen,
        Rural Municipality No. 373"."""
        match = RURAL_MUNICIPALITY.match(self.name)
        if match is None:
            return self.name
        return f"{match.group('name')} No. {match.group('number')}"

    @property
    def government(self) -> str:
        return f"{self.kind} of {self.place_name}"


def read_rows(opened: OpenedFile) -> list[Row]:
    rows = []
    for row in opened.rows:
        site = row["website"].strip()
        rows.append(
            Row(
                name=" ".join(row["name"].split()),
                kind=row["municipality_type"],
                homepage=normalize_url(site) if site else None,
                line=row.line,
            )
        )
    return rows


def key(name: str) -> str:
    """A name as the census and the directory are compared: lower case, accents folded (the
    directory writes Roche Percee), punctuation out."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", folded.lower()).split())


@dataclass
class Notes:
    dropped: Counter[str] = field(default_factory=Counter)
    restructured: list[str] = field(default_factory=list)
    renamed: list[str] = field(default_factory=list)
    shared: list[str] = field(default_factory=list)
    # Municipalities the directory has and the census has not: loaded from the interim list
    # when that codes them, else waiting.
    created: list[str] = field(default_factory=list)
    uncoded: list[str] = field(default_factory=list)
    directory_dropped: list[str] = field(default_factory=list)

    def log(self) -> None:
        for type_, count in sorted(self.dropped.items()):
            logger.info(
                "left out %d %s subdivisions (%s)", count, DROPPED_TYPES.get(type_, type_), type_
            )
        for line in self.restructured:
            logger.info("override: %s", line)
        for line in self.renamed:
            logger.info("the directory names otherwise than the census: %s", line)
        for line in self.shared:
            logger.info("a city shared with another province, loaded there: %s", line)
        for line in self.created:
            logger.info("incorporated since the census, coded by the interim list: %s", line)
        for line in self.uncoded:
            logger.warning("incorporated since the census and not coded yet, not loaded: %s", line)
        for line in self.directory_dropped:
            logger.info("directory row that is no municipality: %s", line)


class Builder:
    def __init__(self, files: Mapping[str, OpenedFile]) -> None:
        self.census = SASKATCHEWAN.read(files)
        self.rows = read_rows(files[DIRECTORY.name])
        self.changes = read_changes(files[INTERIM_CHANGES.name], SASKATCHEWAN)
        self.notes = Notes()
        self.by_key: dict[tuple[str, str], Row] = {}
        for row in self.rows:
            type_ = row.census_type
            if type_ is None:
                self.notes.directory_dropped.append(f"{row.name} ({row.kind})")
                continue
            self.by_key[(key(row.place_name), type_)] = row

    def _row_for(self, unit: Counted, fields: Mapping[str, str]) -> Row | None:
        name = fields.get("directory", census_name(unit))
        row = self.by_key.get((key(name), unit.type_))
        if row is None and "directory" in fields:
            row = next((row for row in self.rows if row.name == name), None)
        return row

    def municipalities(self) -> list[PlaceEntry]:
        found = []
        taken: set[int] = set()
        for unit in self.census.subdivisions:
            if unit.type_ not in MUNICIPAL_TYPES:
                self.notes.dropped[unit.type_] += 1
                continue
            if unit.code in SHARED_CITIES:
                self.notes.shared.append(
                    f"{unit.code} {unit.names[0]}: under {SHARED_CITIES[unit.code]}"
                )
                continue
            fields = OVERRIDES.get(unit.code, {})
            if "dissolved" in fields:
                self.notes.restructured.append(f"{unit.code} {unit.names[0]}: {fields['reason']}")
                continue
            row = self._row_for(unit, fields)
            if row is None:
                raise ListFileError(
                    f"{DIRECTORY.name}: no row for census municipality {unit.code} "
                    f"{unit.names[0]} ({unit.type_}) and no override says what became of it"
                )
            taken.add(row.line)
            found.append(self._entry(unit, row, fields))
        found.extend(self._created(taken))
        return sorted(found, key=lambda entry: entry.name)

    def _entry(self, unit: Counted, row: Row, fields: Mapping[str, str]) -> PlaceEntry:
        # The directory's name wins where it differs in more than case and accents (the
        # directory writes "Roche Percee" and "Lake Of The Rivers").
        name = fields.get("name", row.place_name)
        if key(name) == key(census_name(unit)):
            name = census_name(unit)
        draft = Draft(unit=unit, name=name, parent=PROVINCE)
        if name != census_name(unit):
            self.notes.renamed.append(f"{unit.code} {census_name(unit)} -> {name}")
            draft.alias(census_name(unit))
        citation = Citation(source=DIRECTORY.name, line=row.line)
        draft.government = fields.get("government", f"{row.kind} of {name}")
        draft.government_citation = citation
        draft.homepage = row.homepage
        draft.homepage_citation = citation
        return draft.entry()

    def _created(self, taken: set[int]) -> list[PlaceEntry]:
        """The directory's municipalities the census has no row for, from the interim list."""
        found = []
        incorporated = {
            (key(change.name), change.type_): change
            for change in self.changes
            if change.change == INCORPORATION
        }
        for row in self.rows:
            type_ = row.census_type
            if row.line in taken or type_ is None:
                continue
            change = incorporated.get((key(row.place_name), type_))
            if change is None:
                self.notes.uncoded.append(f"{row.name} ({row.kind})")
                continue
            self.notes.created.append(f"{change.code} {row.name} ({row.kind}), {change.effective}")
            found.append(self._incorporated(row, change))
        return found

    def _incorporated(self, row: Row, change: Change) -> PlaceEntry:
        interim = Citation(source=INTERIM_CHANGES.name, line=change.line)
        directory = Citation(source=DIRECTORY.name, line=row.line)
        citations: dict[Fact, Citation] = {"place": interim, "government": directory}
        if row.homepage is not None:
            citations["homepage"] = directory
        return PlaceEntry(
            name=row.place_name,
            level=MUNICIPALITY,
            parent=PROVINCE,
            parent_level=PROVINCE_LEVEL,
            government=row.government,
            code=Code(scheme=IdentifierScheme.STATCAN_SGC, value=change.code),
            homepage=row.homepage,
            citations=citations,
        )


def build(files: Mapping[str, OpenedFile]) -> tuple[list[PlaceEntry], Notes]:
    builder = Builder(files)
    return builder.municipalities(), builder.notes


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[PlaceEntry]:
    """Saskatchewan's municipalities, under the province."""
    del rules
    found, notes = build(files)
    notes.log()
    return found
