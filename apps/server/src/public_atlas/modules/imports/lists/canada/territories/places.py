"""The three territories' places from Statistics Canada's 2021 Census and each territory's own
directory: Yukon's 8 municipalities, the Northwest Territories' 24 and Nunavut's 25, each with
its code, its 2021 population, its government's official name and, where the directory gives
one, its website as a candidate homepage. Every municipality sits under its territory; a
census region is only a census unit.

The census population table gives every unit's code, names and population and the geographic
attribute file says what each unit is (`canada/statcan.py`, shared with every province). The
three directories are manual files: yukon.ca and gov.nu.ca block scripts, and every page from
MACA (the Northwest Territories' Municipal and Community Affairs) carries a form token that
changes with each request, so no hash can be pinned and a person saves each (the files'
`instructions`). The rules:

- Yukon: the *Local Government Directory* PDF lists the eight municipalities with their
  websites. The parser renders its layout as one table cell per page (table structure is off,
  spec section 8.3), so a municipality's government and homepage cite the line that holds its
  page. The government's name is the directory's, less a leading "The" ("City of Dawson",
  "Village of Carmacks"). The hamlets and local advisory councils are advisory areas, not
  governments.
- Northwest Territories: MACA's community list is a page per community with its official
  name, status and website. The 24 communities the census types as a city, town, village,
  hamlet, community government or chartered community are municipalities, named as the
  census names them with the page's spelling as an alias where it differs (Behchoko, Deline,
  Gameti, Wekweeti, each with its own letters); the government's name is the page's official
  community name ("Community Government of Behchoko", "Charter Community of K'asho Got'ine",
  "Deline Got'ine Government"). The nine other communities are designated authorities, First
  Nations acting as the local authority of a settlement: their pages are read and counted, and
  the bodies wait for the First Nations list.
- Nunavut: the Government of Nunavut's community pages, one per municipality, with the
  hamlet's website where it has one. The government is the "Hamlet of X" or "Municipality of X"
  the page says, "City of Iqaluit" for the capital, and "Hamlet of X" where the page does not
  say. Three municipalities have renamed themselves since the census (Kinngait, Sanirajak,
  Resolute Bay): the page's name is the place's and the census's an alias. The website is the
  page's link.
- Settlements, self-government lands, unorganized areas, Indian reserves and settlements are
  not municipalities and are left out.
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
    Census,
    Citation,
    Counted,
    Draft,
    census_name,
    composed_government,
)
from public_atlas.modules.imports.models import Retrieval

if TYPE_CHECKING:
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = statcan.COUNTRY
YUKON = statcan.Province("60")
NORTHWEST_TERRITORIES = statcan.Province("61")
NUNAVUT = statcan.Province("62")
TERRITORIES = (YUKON, NORTHWEST_TERRITORIES, NUNAVUT)

# --- Yukon ---

YUKON_DIRECTORY = ListFile(
    name="yukon_local_government_directory_2026_06",
    title="Government of Yukon, Yukon local government directory, June 16, 2026",
    url="https://yukon.ca/sites/yukon.ca/files/cs/cs-local-government-directory-2026-06-16_.pdf",
    format=Format.PDF,
    retrieval=Retrieval.MANUAL,
    instructions=(
        "yukon.ca sits behind Cloudflare and refuses scripts. Open the directory's PDF in a "
        "browser (yukon.ca, Community Affairs, Local government directory) and save it as "
        "yukon_local_government_directory_2026_06.pdf. It is six pages: the Community Affairs "
        "Branch, the Association of Yukon Communities, the Yukon Municipal Board, the eight "
        "municipalities (Carmacks, Dawson City, Faro, Haines Junction, Mayo, Teslin, Watson "
        "Lake, Whitehorse) with their addresses, websites and councils, and the five local "
        "advisory areas."
    ),
    filename_override="yukon_local_government_directory_2026_06.pdf",
    tables=True,
)
# A municipality's row in the directory's table (the parser reconstructs it, `tables`): its
# first cell opens with the government's name and runs on into the address, and holds the
# website.
_YUKON_ROW = re.compile(
    r"^\|\s*(?:The )?(?P<government>(?:City|Town|Village) of (?P<name>[A-Z][\w' ]+?))\s+(?:Box |\d)"
)
_WEBSITE = re.compile(r"Website\s*:?\s*(?P<site>\S+)", re.IGNORECASE)

# --- Northwest Territories ---

_MACA = "https://www.maca.gov.nt.ca/en/content/"
# Every community MACA lists, by the slug of its page: the census name of the municipality it
# is, or None for a designated authority.
NWT_COMMUNITIES: tuple[tuple[str, str | None], ...] = (
    ("aklavik", "Aklavik"),
    ("behchoko", "Behchokò"),
    ("colville-lake", None),
    ("dettah", None),
    ("deline", "Déline"),
    ("enterprise", "Enterprise"),
    ("fort-good-hope", "Fort Good Hope"),
    ("fort-liard", "Fort Liard"),
    ("fort-mcpherson", "Fort McPherson"),
    ("fort-providence", "Fort Providence"),
    ("fort-resolution", "Fort Resolution"),
    ("fort-simpson", "Fort Simpson"),
    ("fort-smith", "Fort Smith"),
    ("gameti", "Gamètì"),
    ("hay-river", "Hay River"),
    ("inuvik", "Inuvik"),
    ("jean-marie-river", None),
    ("kakisa", None),
    ("katlodeeche", None),
    ("nahanni-butte", None),
    ("norman-wells", "Norman Wells"),
    ("paulatuk", "Paulatuk"),
    ("sachs-harbour", "Sachs Harbour"),
    ("sambaa-ke", None),
    ("tsiigehtchic", "Tsiigehtchic"),
    ("tuktoyaktuk", "Tuktoyaktuk"),
    ("tulita", "Tulita"),
    ("ulukhaktok", "Ulukhaktok"),
    ("wekweeti", "Wekweètì"),
    ("whati", "Whatì"),
    ("wrigley", None),
    ("yellowknife", "Yellowknife"),
    ("lutselke", None),
)
# The pages' paths, where the slug is not the path (the names with their own letters).
_MACA_PATHS: dict[str, str] = {
    "behchoko": "behchok%C7%AB%CC%80",
    "deline": "de%CC%81l%C4%B1%CC%A8ne%CC%A8",
    "gameti": "gam%C3%A8t%C3%AC",
    "katlodeeche": "k%C3%A1t%C5%82%E2%80%99odeeche",
    "sambaa-ke": "sambaa-k%E2%80%99e",
    "wekweeti": "wekwe%C3%A8t%C3%AC",
    "whati": "what%C3%AC",
    "lutselke": "%C5%82utselk%E2%80%99e",
}
_NWT_INSTRUCTIONS = (
    "Open the community's page under https://www.maca.gov.nt.ca/en/communitylist (33 "
    "communities over three pages) and save it as HTML, or fetch it once with curl and a "
    "browser user agent, as nwt_community_<slug>.html. Every response carries a new form "
    "token, so no hash is pinned. The page gives the official community name, the community "
    "status, the region, the leader, the senior administrative officer, the councillors, the "
    "address, the phone numbers and, for about half the communities, the website."
)


def _nwt_file(slug: str) -> ListFile:
    name = slug.replace("-", "_")
    return ListFile(
        name=f"nwt_community_{name}",
        title=f"Northwest Territories Municipal and Community Affairs, community page: {slug}",
        url=_MACA + _MACA_PATHS.get(slug, slug),
        format=Format.HTML,
        retrieval=Retrieval.MANUAL,
        instructions=_NWT_INSTRUCTIONS,
        filename_override=f"nwt_community_{name}.html",
    )


NWT_PAGES: dict[str, ListFile] = {slug: _nwt_file(slug) for slug, _ in NWT_COMMUNITIES}
OFFICIAL_NAME = "Official Community Name:"
STATUS = "Community Status:"

# --- Nunavut ---

# Every community the Government of Nunavut lists, by the slug of its page, with the census
# name of the municipality it is.
NUNAVUT_COMMUNITIES: tuple[tuple[str, str], ...] = (
    ("arctic-bay", "Arctic Bay"),
    ("arviat", "Arviat"),
    ("baker-lake", "Baker Lake"),
    ("cambridge-bay", "Cambridge Bay"),
    ("chesterfield-inlet", "Chesterfield Inlet"),
    ("clyde-river", "Clyde River"),
    ("coral-harbour", "Coral Harbour"),
    ("gjoa-haven", "Gjoa Haven"),
    ("grise-fiord", "Grise Fiord"),
    ("igloolik", "Igloolik"),
    ("iqaluit", "Iqaluit"),
    ("kimmirut", "Kimmirut"),
    ("kinngait", "Cape Dorset"),
    ("kugaaruk", "Kugaaruk"),
    ("kugluktuk", "Kugluktuk"),
    ("naujaat", "Naujaat"),
    ("pangnirtung", "Pangnirtung"),
    ("pond-inlet", "Pond Inlet"),
    ("qikiqtarjuaq", "Qikiqtarjuaq"),
    ("rankin-inlet", "Rankin Inlet"),
    ("resolute-bay", "Resolute"),
    ("sanikiluaq", "Sanikiluaq"),
    ("sanirajak", "Hall Beach"),
    ("taloyoak", "Taloyoak"),
    ("whale-cove", "Whale Cove"),
)
_NUNAVUT_INSTRUCTIONS = (
    "gov.nu.ca refuses scripts. Open the community's page under "
    "https://www.gov.nu.ca/en/communities (25 communities) in a browser and save the rendered "
    "page as HTML (the document's outerHTML) as nunavut_community_<slug>.html, recording the "
    "capture time and the file's sha256 in an evidence log kept outside the repository. The "
    "page gives the community's description, its hamlet council and administration, the "
    "contact details and, where the hamlet has one, its website."
)


def _nunavut_file(slug: str) -> ListFile:
    name = slug.replace("-", "_")
    return ListFile(
        name=f"nunavut_community_{name}",
        title=f"Government of Nunavut, community page: {slug}",
        url=f"https://www.gov.nu.ca/en/communities/{slug}",
        format=Format.HTML,
        retrieval=Retrieval.MANUAL,
        instructions=_NUNAVUT_INSTRUCTIONS,
        filename_override=f"nunavut_community_{name}.html",
    )


NUNAVUT_PAGES: dict[str, ListFile] = {slug: _nunavut_file(slug) for slug, _ in NUNAVUT_COMMUNITIES}
# "<Kind> of <the community's name>" as the page's prose or link gives it, and its website link
# in the HTML.
_NUNAVUT_KINDS = ("City", "Municipality", "Hamlet")


def _government_pattern(name: str) -> re.Pattern[str]:
    kinds = "|".join(_NUNAVUT_KINDS)
    return re.compile(rf"\b(?P<government>(?P<kind>{kinds}) of {re.escape(name)})\b")


# What the page calls the body, the most specific first: the hamlets that style themselves a
# municipality say both.
_KIND_ORDER = {"City": 0, "Municipality": 1, "Hamlet": 2}
_NUNAVUT_LINK = re.compile(
    r"Website:?(?:&nbsp;|\s)*<a[^>]*href=\"(?P<href>[^\"]+)\"", re.IGNORECASE
)

SOURCES = (
    POPULATION,
    ATTRIBUTES,
    YUKON_DIRECTORY,
    *NWT_PAGES.values(),
    *NUNAVUT_PAGES.values(),
)

# No hand corrections: the renames are read from the pages.
OVERRIDES: dict[str, dict[str, str]] = {}


def key(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", folded.lower()).split())


def _site(text: str) -> str | None:
    text = text.strip().rstrip(".,;)")
    if "." not in text or "@" in text or " " in text:
        return None
    text = re.sub(r"^(https?)//", r"\1://", text)
    return normalize_url(text)


@dataclass
class Notes:
    dropped: Counter[str] = field(default_factory=Counter)
    renamed: list[str] = field(default_factory=list)
    without_website: list[str] = field(default_factory=list)
    designated_authorities: list[str] = field(default_factory=list)

    def log(self) -> None:
        for type_, count in sorted(self.dropped.items()):
            logger.info("left out %d subdivisions typed %s", count, type_)
        for line in self.renamed:
            logger.info("the directory names otherwise than the census: %s", line)
        for line in self.without_website:
            logger.info("no website in the directory: %s", line)
        for line in self.designated_authorities:
            logger.info("designated authority, not a municipality: %s", line)


def _municipalities(census: Census, notes: Notes) -> list[Counted]:
    notes.dropped.update(census.dropped())
    return census.municipalities


# --- Yukon ---


def yukon_entries(files: Mapping[str, OpenedFile], notes: Notes) -> list[PlaceEntry]:
    census = YUKON.read(files)
    opened = files[YUKON_DIRECTORY.name]
    # Each municipality's row, with its line.
    segments: dict[str, tuple[str, int, str]] = {}
    for number, line in enumerate(opened.lines, 1):
        match = _YUKON_ROW.match(line)
        if match:
            segments[key(match.group("name"))] = (match.group("government"), number, line)
    found = []
    for unit in _municipalities(census, notes):
        segment = segments.get(key(census_name(unit)))
        if segment is None:
            raise ListFileError(f"{YUKON_DIRECTORY.name}: no entry for {unit.code} {unit.names[0]}")
        government, line, text = segment
        draft = Draft(unit=unit, name=census_name(unit), parent=YUKON.name)
        draft.government = government
        draft.government_citation = Citation(source=YUKON_DIRECTORY.name, line=line)
        site = _WEBSITE.search(text)
        draft.homepage = _site(site.group("site")) if site else None
        draft.homepage_citation = draft.government_citation
        if draft.homepage is None:
            notes.without_website.append(f"{unit.code} {census_name(unit)}")
        found.append(draft.entry())
    return found


# --- Northwest Territories ---


def _after(lines: list[str], label: str) -> str | None:
    """The line after the labelled one."""
    try:
        index = lines.index(label)
    except ValueError:
        return None
    return lines[index + 1] if index + 1 < len(lines) else None


def nwt_entries(files: Mapping[str, OpenedFile], notes: Notes) -> list[PlaceEntry]:
    census = NORTHWEST_TERRITORIES.read(files)
    by_name = {key(census_name(unit)): unit for unit in _municipalities(census, notes)}
    found = []
    taken: set[str] = set()
    for slug, census_name_ in NWT_COMMUNITIES:
        opened = files[NWT_PAGES[slug].name]
        official = _after(opened.lines, OFFICIAL_NAME)
        status = _after(opened.lines, STATUS)
        if official is None or status is None:
            raise ListFileError(f"{NWT_PAGES[slug].name}: no official community name on the page")
        if census_name_ is None:
            notes.designated_authorities.append(f"{slug}: {official} ({status})")
            continue
        unit = by_name.get(key(census_name_))
        if unit is None:
            raise ListFileError(
                f"{NWT_PAGES[slug].name}: {census_name_!r} is no census municipality"
            )
        taken.add(unit.code)
        draft = Draft(unit=unit, name=census_name(unit), parent=NORTHWEST_TERRITORIES.name)
        draft.government = " ".join(official.split())
        draft.government_citation = Citation(
            source=NWT_PAGES[slug].name, line=opened.lines.index(official) + 1
        )
        spelled = official.split(" of ", 1)[-1] if " of " in official else None
        if spelled is not None and spelled != census_name(unit):
            draft.alias(spelled)
            if key(spelled) != key(census_name(unit)):
                notes.renamed.append(f"{unit.code} {census_name(unit)} -> {spelled} (alias)")
        sites = [
            (number, line) for number, line in enumerate(opened.lines, 1) if line.startswith("http")
        ]
        if sites:
            number, line = sites[0]
            draft.homepage = normalize_url(line.strip())
            draft.homepage_citation = Citation(source=NWT_PAGES[slug].name, line=number)
        else:
            notes.without_website.append(f"{unit.code} {census_name(unit)}")
        found.append(draft.entry())
    missing = [unit for unit in by_name.values() if unit.code not in taken]
    if missing:
        raise ListFileError(f"no MACA page for {[unit.names[0] for unit in missing]}")
    return found


# --- Nunavut ---


def nunavut_entries(files: Mapping[str, OpenedFile], notes: Notes) -> list[PlaceEntry]:
    census = NUNAVUT.read(files)
    by_name = {key(census_name(unit)): unit for unit in _municipalities(census, notes)}
    found = []
    taken: set[str] = set()
    for slug, census_name_ in NUNAVUT_COMMUNITIES:
        opened = files[NUNAVUT_PAGES[slug].name]
        unit = by_name.get(key(census_name_))
        if unit is None:
            raise ListFileError(
                f"{NUNAVUT_PAGES[slug].name}: {census_name_!r} is no census municipality"
            )
        taken.add(unit.code)
        # The page's heading is the community's current name.
        name = " ".join(slug.replace("-", " ").title().split())
        heading = next((n for n, line in enumerate(opened.lines, 1) if line == name), None)
        if heading is None:
            raise ListFileError(f"{NUNAVUT_PAGES[slug].name}: the page has no heading {name!r}")
        draft = Draft(unit=unit, name=name, parent=NUNAVUT.name)
        if name != census_name(unit):
            notes.renamed.append(f"{unit.code} {census_name(unit)} -> {name}")
            draft.alias(census_name(unit))
        pattern = _government_pattern(name)
        governments = sorted(
            (_KIND_ORDER[match.group("kind")], n, match.group("government"))
            for n, line in enumerate(opened.lines, 1)
            for match in pattern.finditer(line)
        )
        if governments:
            _, number, government = governments[0]
            draft.government = government
            draft.government_citation = Citation(source=NUNAVUT_PAGES[slug].name, line=number)
        else:
            draft.government = composed_government(NUNAVUT, unit, name)
            draft.government_citation = Citation(source=NUNAVUT_PAGES[slug].name, line=heading)
        link = _NUNAVUT_LINK.search(opened.data.decode("utf-8", errors="replace"))
        site_line = next(
            (n for n, line in enumerate(opened.lines, 1) if line.lower().startswith("website")),
            None,
        )
        if link is not None and site_line is not None:
            draft.homepage = _site(link.group("href"))
            draft.homepage_citation = Citation(source=NUNAVUT_PAGES[slug].name, line=site_line)
        if draft.homepage is None:
            notes.without_website.append(f"{unit.code} {name}")
        found.append(draft.entry())
    missing = [unit for unit in by_name.values() if unit.code not in taken]
    if missing:
        raise ListFileError(f"no community page for {[unit.names[0] for unit in missing]}")
    return found


def build(files: Mapping[str, OpenedFile]) -> tuple[list[PlaceEntry], Notes]:
    notes = Notes()
    found = [
        *yukon_entries(files, notes),
        *nwt_entries(files, notes),
        *nunavut_entries(files, notes),
    ]
    return sorted(found, key=lambda entry: (entry.parent, entry.name)), notes


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[PlaceEntry]:
    """Yukon's, the Northwest Territories' and Nunavut's municipalities, each under its
    territory."""
    del rules
    found, notes = build(files)
    notes.log()
    return found
