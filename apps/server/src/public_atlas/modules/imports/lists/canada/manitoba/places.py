"""Manitoba's places from Statistics Canada's 2021 Census and the province's *Municipal
Officials Directory*: the 138 municipalities, each with its code, its 2021 population, its
government's name and, where the directory gives one, its website as a candidate homepage. The
province is single-tier: every municipality sits under Manitoba, and a census division is only
a census unit.

The census population table gives every unit's code, names and population and the geographic
attribute file says what each unit is (`canada/statcan.py`, shared with every province). The
directory is a PDF the loader parses with Docling: its "Manitoba Municipalities" section is one
entry per municipality, headed by the name and the kind in capitals ("ALEXANDER, RM", "ALTONA,
TOWN", "GILBERT PLAINS MUNICIPALITY", "PINAWA, L.G.D."), with the address, the contacts and a
"Website:" line below. The rules:

- A city, town, village, municipality, rural municipality or local government district is
  matched to the directory's entry by name, accents and case folded ("TACHĖ, RM" is Taché). The
  namesakes (the rural municipality and the town of Lac du Bonnet, Morris and Ste. Anne; the
  rural municipality and the city of Dauphin, Portage la Prairie and Thompson) are told apart
  by the kind. The place keeps the census's name; the government's name is composed from the
  directory's kind, which wins over the census type (the census types the Municipality of
  Killarney-Turtle Mountain as a rural municipality): "Rural Municipality of Alexander", "Town
  of Altona", "City of Brandon", "Village of Dunnottar", "Municipality of Gilbert Plains",
  "Local Government District of Pinawa".
- Where the directory and the census differ in more than spelling, `OVERRIDES` says why: the
  Municipality of Roblin, which the census still calls Hillsburg-Roblin-Shell River, takes the
  directory's name with the census's as an alias; the Rural Municipality of Mountain, which the
  census still counts as Mountain (North) and Mountain (South), is one place with the two
  parts' population.
- Flin Flon is one city in two provinces with its city hall in Manitoba: one place under
  Manitoba with the Manitoba part's code and the two parts' population summed; Saskatchewan's
  list leaves its part out.
- The website is the entry's "Website:" line, given a scheme; an entry without one has none.
- Indian reserves, Indian settlements and unorganized areas are not governments and are left
  out.

The directory is updated a few times a year at the same URL, so a new release means a new hash
recorded here and the diff reviewed.
"""

import logging
import re
import unicodedata
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
    Counted,
    Draft,
    census_name,
)

if TYPE_CHECKING:
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = statcan.COUNTRY
PROVINCE = "Manitoba"
PROVINCE_CODE = "46"
MANITOBA = statcan.Province(PROVINCE_CODE)
SASKATCHEWAN = statcan.Province("47")

DIRECTORY = ListFile(
    name="manitoba_municipal_officials_directory_2026_07",
    title="Manitoba Municipal Relations, Municipal Officials Directory, updated 2026-07-24",
    url="https://www.gov.mb.ca/mr/contactus/pubs/mod.pdf",
    sha256="72e36c5690e6afd7b2937fcb7f8e71299b1790c49db79b6f0664a56ec7f267dc",
    format=Format.PDF,
)
SOURCES = (POPULATION, ATTRIBUTES, DIRECTORY)

MUNICIPAL_TYPES = MANITOBA.municipal_types
DROPPED_TYPES = MANITOBA.dropped_types
# The directory's kinds, each with the census type it answers to.
KINDS: dict[str, str] = {
    "RM": "RM",
    "TOWN": "T",
    "CITY": "CY",
    "VILLAGE": "VL",
    "MUNICIPALITY": "MU",
    "L.G.D.": "LGD",
    "LGD": "LGD",
}
# The section of the directory the entries are in.
SECTION_START = "## MANITOBA MUNICIPALITIES"
SECTION_END = "## THE CITY OF WINNIPEG"
# An entry's heading: the name in capitals, a comma, the kind; or the name and MUNICIPALITY; or
# the name and a comma alone, the kind on the next heading.
_KINDS = r"RM|TOWN|CITY|VILLAGE|MUNICIPALITY|L\.G\.D\.|LGD"
_HEADING = re.compile(
    r"^(?:## )?(?P<name>[A-ZÀ-ÖØ-ÞĖ' .\-]+?)"
    rf"(?:,\s*(?P<kind>{_KINDS})(?:\s+\d.*)?|\s+(?P<kind2>MUNICIPALITY)|(?P<comma>,))\s*$"
)
_KIND_LINE = re.compile(r"^## (?P<kind>MUNICIPALITY|RM|TOWN|CITY|VILLAGE|L\.G\.D\.)\s*$")
# The website line, as a bare line or a markdown link whose text is the line.
_WEBSITE = re.compile(r"Website\s*:?\s*(?P<site>\S+)", re.IGNORECASE)
_LINK = re.compile(r"^\[(?P<text>[^\]]*)\]\((?P<url>[^)]*)\)")
# The city shared with Saskatchewan: the Manitoba part's census code and the Saskatchewan part's.
FLIN_FLON = "4621064"
FLIN_FLON_SASKATCHEWAN = "4718052"

# Hand corrections keyed by census code, each with its reason: `directory`, the heading's name
# where the census writes another; `merged_from`, the census code of a municipality that has
# merged into this one since the census and whose population is added.
OVERRIDES: dict[str, dict[str, str]] = {
    "4616048": {
        "directory": "ROBLIN",
        "name": "Roblin",
        "reason": "the Municipality of Roblin (Hillsburg, Roblin and Shell River, amalgamated "
        "2015) goes by Roblin; the census keeps the three names",
    },
    "4620055": {
        "directory": "MOUNTAIN",
        "name": "Mountain",
        "merged_from": "4620032",
        "reason": "the rural municipalities of Mountain (North) and Mountain (South) are one "
        "Rural Municipality of Mountain in the directory, with its office in Birch River; the "
        "census counts the two parts, summed here under the northern part's code",
    },
}


@dataclass(frozen=True)
class Entry:
    # As the heading writes it, in capitals.
    name: str
    kind: str
    homepage: str | None
    line: int
    homepage_line: int | None

    @property
    def census_type(self) -> str:
        return KINDS[self.kind]


def key(name: str) -> str:
    """A name as the census and the directory are compared: lower case, accents folded."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", folded.lower()).split())


def website(line: str) -> str | None:
    """The URL a "Website:" line gives: the link's target when the parser made one, else the
    first word after the label, given a scheme; None when the word is no address."""
    link = _LINK.match(line.strip())
    if link is not None:
        target = link.group("url").strip()
        text = link.group("text")
        if target and "safelinks" not in target and "mailto:" not in target:
            return normalize_url(target)
        line = text
    match = _WEBSITE.search(line)
    if match is None:
        return None
    site = match.group("site").strip("[]()").rstrip(".,;")
    if "." not in site or "@" in site:
        return None
    return normalize_url(site)


def _headings(lines: list[str], start: int, end: int) -> list[tuple[int, str, str]]:
    """Each entry's heading between `start` and `end`: its line (counted from 0), name and
    kind."""
    headings: list[tuple[int, str, str]] = []
    number = start + 1
    while number < end:
        match = _HEADING.match(lines[number])
        heading = number
        number += 1
        if match is None:
            continue
        kind = match.group("kind") or match.group("kind2")
        if kind is None and match.group("comma"):
            # The kind is on the next heading line.
            while number < end and not lines[number].strip():
                number += 1
            kind_match = _KIND_LINE.match(lines[number]) if number < end else None
            if kind_match is None:
                continue
            kind = kind_match.group("kind")
            number += 1
        if kind is None:
            continue
        headings.append((heading, match.group("name").strip(), kind))
    return headings


def read_entries(opened: OpenedFile) -> list[Entry]:
    """The municipalities' entries: each heading with the first website line before the next."""
    lines = opened.lines
    try:
        start = lines.index(SECTION_START)
        end = lines.index(SECTION_END)
    except ValueError as exc:
        raise ListFileError(f"{DIRECTORY.name}: the municipalities section is not found") from exc
    headings = _headings(lines, start, end)
    entries = []
    for index, (line, name, kind) in enumerate(headings):
        until = headings[index + 1][0] if index + 1 < len(headings) else end
        homepage, homepage_line = None, None
        for offset in range(line, until):
            if "ebsite" in lines[offset]:
                homepage = website(lines[offset])
                homepage_line = offset + 1 if homepage is not None else None
                break
        entries.append(
            Entry(
                name=name, kind=kind, homepage=homepage, line=line + 1, homepage_line=homepage_line
            )
        )
    return entries


@dataclass
class Notes:
    dropped: Counter[str] = field(default_factory=Counter)
    shared: list[str] = field(default_factory=list)
    renamed: list[str] = field(default_factory=list)
    merged: list[str] = field(default_factory=list)
    without_website: list[str] = field(default_factory=list)
    untaken: list[str] = field(default_factory=list)

    def log(self) -> None:
        for type_, count in sorted(self.dropped.items()):
            logger.info(
                "left out %d %s subdivisions (%s)", count, DROPPED_TYPES.get(type_, type_), type_
            )
        for line in self.shared:
            logger.info("a city shared with another province: %s", line)
        for line in self.renamed:
            logger.info("override: %s", line)
        for line in self.merged:
            logger.info("merged since the census into: %s", line)
        for line in self.without_website:
            logger.info("no website in the directory: %s", line)
        for line in self.untaken:
            logger.warning("directory entry no place took: %s", line)


def government_name(entry: Entry, name: str) -> str:
    designator = MUNICIPAL_TYPES[entry.census_type]
    return f"{designator} of {name}"


def _entry_for(unit: Counted, entries: list[Entry], namesakes: Counter[str]) -> Entry | None:
    """The directory's entry for a census municipality: by name, and by kind where two
    municipalities share a name. The directory's kind is otherwise taken over the census's (the
    census types the Municipality of Killarney-Turtle Mountain as a rural municipality)."""
    wanted = key(OVERRIDES.get(unit.code, {}).get("directory", census_name(unit)))
    found = [entry for entry in entries if key(entry.name) == wanted]
    if len(found) > 1 or namesakes[wanted] > 1:
        found = [entry for entry in found if entry.census_type == unit.type_]
    return found[0] if len(found) == 1 else None


def build(files: Mapping[str, OpenedFile]) -> tuple[list[PlaceEntry], Notes]:
    census = MANITOBA.read(files)
    saskatchewan = SASKATCHEWAN.read(files)
    directory = read_entries(files[DIRECTORY.name])
    merged = {
        fields["merged_from"]: code for code, fields in OVERRIDES.items() if "merged_from" in fields
    }
    namesakes = Counter(key(census_name(unit)) for unit in census.municipalities)
    notes = Notes()
    found = []
    taken: set[int] = set()
    for unit in census.subdivisions:
        if unit.type_ not in MUNICIPAL_TYPES:
            notes.dropped[unit.type_] += 1
            continue
        if unit.code in merged:
            notes.merged.append(f"{unit.code} {unit.names[0]} -> {merged[unit.code]}")
            continue
        entry = _entry_for(unit, directory, namesakes)
        if entry is None:
            raise ListFileError(
                f"{DIRECTORY.name}: no entry for census municipality {unit.code} {unit.names[0]} "
                f"({unit.type_})"
            )
        taken.add(entry.line)
        found.append(_place(unit, entry, census, saskatchewan, notes))
    for entry in directory:
        if entry.line not in taken:
            notes.untaken.append(f"{entry.name}, {entry.kind}")
    return sorted(found, key=lambda e: e.name), notes


def _place(
    unit: Counted, entry: Entry, census: statcan.Census, saskatchewan: statcan.Census, notes: Notes
) -> PlaceEntry:
    fields = OVERRIDES.get(unit.code, {})
    name = fields.get("name", census_name(unit))
    draft = Draft(unit=unit, name=name, parent=PROVINCE)
    if name != census_name(unit):
        notes.renamed.append(f"{unit.code} {census_name(unit)} -> {name}: {fields['reason']}")
        draft.alias(census_name(unit))
    if "merged_from" in fields:
        part = census.unit(fields["merged_from"])
        if unit.population is None or part.population is None:
            raise ListFileError(f"{name}: a part has no population")
        draft.population = unit.population + part.population
        draft.alias(census_name(part))
    draft.government = government_name(entry, name)
    draft.government_citation = Citation(source=DIRECTORY.name, line=entry.line)
    if entry.homepage is not None and entry.homepage_line is not None:
        draft.homepage = entry.homepage
        draft.homepage_citation = Citation(source=DIRECTORY.name, line=entry.homepage_line)
    else:
        notes.without_website.append(f"{unit.code} {name}")
    if unit.code == FLIN_FLON:
        part = saskatchewan.unit(FLIN_FLON_SASKATCHEWAN)
        if unit.population is None or part.population is None:
            raise ListFileError("Flin Flon: a part has no population")
        draft.population = unit.population + part.population
        notes.shared.append(f"{unit.code} {name}: with Saskatchewan's {part.code}")
    return draft.entry()


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[PlaceEntry]:
    """Manitoba's 138 municipalities, under the province."""
    del rules
    found, notes = build(files)
    notes.log()
    return found
