"""Ontario's public hospitals, colleges and universities from the province's Directory of
Institutions under the Freedom of Information and Protection of Privacy Act (FIPPA) and its
municipal counterpart (MFIPPA): 144 hospital corporations, 24 colleges and 21 universities,
each with its website as a candidate homepage, attached to the municipality of its address.

The directory is one CSV of every body under the two acts (1,497 rows); this module reads
the three types whose rows carry a website. Its rules:

- The name is the directory's, with the HTML its cells hold (`<abbr>` around "St.") read as
  text. A trailing parenthetical is a note, not part of the name: an acronym ("(STEGH)") and a
  former name ("(Formerly ...)") become aliases, a cross-reference ("(See ...)") or a place
  is dropped.
- The website is the link's origin (scheme and host), not the page it points at: the directory
  links each body's freedom-of-information page, and the homepage is the site's root. "not
  available" is no website.
- The place is the municipality the `City` column's community lies in, with its level and
  parent so a city named like its district or county is the city (`communities.py`).
- The ministry's own pages of public universities and colleges (ontario.ca, read 2026-10-09;
  `UNIVERSITIES_PAGE`, `COLLEGES_PAGE`) are the cross-check: each FIPPA college is on the
  colleges page under a long or short form of its name; each FIPPA university is on the
  universities page except Dominican University College, which the directory alone lists; and
  three universities the page lists are not in the directory (NOSM University, Université de
  Hearst, Université de l'Ontario français), so they are not loaded here: there is no line
  to cite. The pages are not sources: each fetch of an ontario.ca page carries a new
  bot-detection token, so no hash can be pinned. The current names the pages give to the
  bodies the directory names as they were (Ryerson University, University of Ontario
  Institute of Technology, Ontario College of Art & Design, University of Western Ontario,
  Seneca College) win, with the directory's name as an alias.
- Royal Military College is the Government of Canada's (National Defence), not a provincial
  body: left out for the federal list.
- The hospital rows are the corporations as the directory still lists them: a few are sites
  of a corporation listed beside them (the Huron Perth Healthcare Alliance's hospitals, the
  Chatham-Kent Health Alliance and its two founding hospitals), and some share a website for
  that reason. They are loaded as listed; the reviewer merges what the directory has not.

The CKAN resource is `c1164f6a-1677-4b21-9ff2-5e92163e9a99` on dataset
`ec9daf71-33de-469e-af32-05265673049b`; the file name carries the release month, so a new
release is one URL and hash swap.
"""

import html
import logging
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from public_atlas.modules.graph.service import normalize_url
from public_atlas.modules.imports.entries import AliasEntry, Citation, Fact, InstitutionEntry
from public_atlas.modules.imports.files import Format, ListFile, OpenedFile
from public_atlas.modules.imports.lists.canada.ontario.communities import location_of
from public_atlas.shared.text import name_key

if TYPE_CHECKING:
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = "CA"

DIRECTORY = ListFile(
    name="fippa_directory_2025_12",
    title=(
        "Ontario Ministry of Public and Business Service Delivery and Procurement, Directory of "
        "Institutions under FIPPA and MFIPPA, release of December 2025"
    ),
    url=(
        "https://data.ontario.ca/dataset/ec9daf71-33de-469e-af32-05265673049b/resource/"
        "c1164f6a-1677-4b21-9ff2-5e92163e9a99/download/doi_dec2025_en.csv"
    ),
    sha256="7bec41339eb20e36513b77c1a727a0866a424d62d44645b9dfa051646f4c275a",
    format=Format.CSV,
    # The contact columns name the bodies' freedom-of-information coordinators; they stay out
    # of the stored text.
    columns=("Name of institution", "Institution type", "Website", "City"),
)
SOURCES = (DIRECTORY,)

# The directory's type to the graph's.
TYPES = {"Hospital": "hospital", "College": "college", "University": "university"}
NOT_AVAILABLE = "not available"

# Rows left out, with the reason.
LEFT_OUT: dict[str, str] = {
    "Royal Military College": (
        "the Government of Canada's, under National Defence; a federal list's, not Ontario's"
    ),
}

# Hand corrections keyed by the directory's name (as text), each with its reason. Fields:
# `name` (the body's current name; the directory's becomes an alias), `place` (the city, when
# the City column is wrong or empty), `homepage` (None when the directory's link is not the
# body's own site), `language`.
OVERRIDES: dict[str, dict[str, str | None]] = {
    "Ryerson University": {
        "name": "Toronto Metropolitan University",
        "reason": "renamed in 2022; the ministry's universities page has the new name",
    },
    "University of Ontario Institute of Technology": {
        "name": "Ontario Tech University",
        "reason": "the name it has used since 2019 and the ministry's universities page gives",
    },
    "Ontario College of Art & Design": {
        "name": "OCAD University",
        "reason": "the name it has had since 2010 and the ministry's universities page gives",
    },
    "University of Western Ontario": {
        "name": "Western University",
        "reason": "the name it has used since 2012 and the ministry's universities page gives",
    },
    "Seneca College of Applied Arts and Technology": {
        "name": "Seneca Polytechnic",
        "reason": "the name it has used since 2023 and the ministry's colleges page gives",
    },
    "Collège Boréal": {"language": "fr", "reason": "a French-language college"},
    "La Cité Collégiale": {"language": "fr", "reason": "a French-language college"},
    "Wilfrid Laurier University": {
        "place": "Waterloo",
        "reason": "the directory has no city; the university is in Waterloo",
    },
    "York University": {
        "place": "Toronto",
        "reason": "the directory has no city; the university is in Toronto",
    },
    "George Brown College": {
        "place": "Toronto",
        "reason": "the directory says Thunder Bay; the college is in Toronto",
    },
    "Renfrew Victoria Hospital": {
        "place": "Renfrew",
        "reason": "the directory says 'North Renfrew'; the hospital is in the Town of Renfrew",
    },
    "Riverside Health Care Facilities Inc.": {
        "place": "Fort Frances",
        "reason": "the directory writes 'Fort France'",
    },
    "University of Toronto": {
        "homepage": None,
        "reason": "the directory links the freedom-of-information office's own subdomain",
    },
    "Lennox & Addington County General Hospital": {
        "homepage": None,
        "reason": "the directory links a page on the web agency's domain, not the hospital's",
    },
    "Atikokan General Hospital": {
        "homepage": None,
        "reason": "the directory repeats Arnprior's link on this row",
    },
}

# The ministry's page of public universities (https://www.ontario.ca/page/ontario-universities,
# updated 2026-06-04, read 2026-10-09), as it names them, Royal Military College included.
UNIVERSITIES_PAGE = (
    "Algoma University",
    "Brock University",
    "Carleton University",
    "Lakehead University",
    "Laurentian University",
    "McMaster University",
    "Nipissing University",
    "Northern Ontario School of Medicine (NOSM) University",
    "OCAD University",
    "Ontario Tech University",
    "Queen's University",
    "Royal Military College",
    "Toronto Metropolitan University",
    "Trent University",
    "University of Guelph",
    "Université de Hearst",
    "Université de l'Ontario français",
    "University of Ottawa",
    "University of Toronto",
    "University of Waterloo",
    "University of Windsor",
    "Western University",
    "Wilfrid Laurier University",
    "York University",
)
# The ministry's page of colleges (https://www.ontario.ca/page/ontario-colleges, updated
# 2026-07-13, read 2026-10-09). Kemptville College, Ridgetown College and the Michener
# Institute are named there as not colleges.
COLLEGES_PAGE = (
    "Algonquin College of Applied Arts and Technology",
    "Cambrian College of Applied Arts and Technology",
    "Canadore College of Applied Arts and Technology",
    "Centennial College of Applied Arts and Technology",
    "Collège Boréal",
    "Conestoga College Institute of Technology and Advanced Learning",
    "Confederation College of Applied Arts and Technology",
    "Durham College of Applied Arts and Technology",
    "Fanshawe College of Applied Arts and Technology",
    "Fleming College of Applied Arts and Technology",
    "George Brown College of Applied Arts and Technology",
    "Georgian College of Applied Arts and Technology",
    "Humber College Institute of Technology and Advanced Learning",
    "La Cité collégiale",
    "Lambton College of Applied Arts and Technology",
    "Loyalist College of Applied Arts and Technology",
    "Mohawk College of Applied Arts and Technology",
    "Niagara College of Applied Arts and Technology",
    "Northern College of Applied Arts and Technology",
    "St. Clair College of Applied Arts and Technology",
    "St. Lawrence College of Applied Arts and Technology",
    "Sault College of Applied Arts and Technology",
    "Seneca Polytechnic",
    "Sheridan College Institute of Technology and Advanced Learning",
)
# Universities the ministry's page lists and the directory does not.
UNIVERSITIES_NOT_IN_DIRECTORY = frozenset(
    {
        "Northern Ontario School of Medicine (NOSM) University",
        "Université de Hearst",
        "Université de l'Ontario français",
    }
)
# And the one the directory lists that the page does not.
UNIVERSITIES_ONLY_IN_DIRECTORY = frozenset({"Dominican University College"})

_TAG = re.compile(r"<[^>]+>")
_HREF = re.compile(r'href="([^"]*)"')
_TRAILING_NOTE = re.compile(r"^(?P<name>.+?)\s*\((?P<note>[^()]*)\)$")
_ACRONYM = re.compile(r"^[A-Z]{2,}$")


def as_text(cell: str) -> str:
    """A cell's text: its HTML read as text, entities decoded, whitespace collapsed."""
    return " ".join(html.unescape(_TAG.sub("", cell)).split())


def split_name(cell: str) -> tuple[str, list[AliasEntry]]:
    """The name without its trailing note, and the aliases the note gives."""
    text = as_text(cell)
    match = _TRAILING_NOTE.match(text)
    if match is None:
        return text, []
    name, note = match.group("name"), match.group("note").strip()
    if _ACRONYM.match(note):
        return name, [AliasEntry(text=note, is_acronym=True)]
    lowered = note.casefold()
    if lowered.startswith("formerly "):
        return name, [AliasEntry(text=note[len("formerly ") :].strip())]
    return name, []


def homepage_of(cell: str) -> str | None:
    """The origin of the site the cell links: the link's target, or the cell's text when it
    is a bare address. "not available" is no site."""
    match = _HREF.search(cell)
    url = match.group(1) if match else as_text(cell)
    if not url or url.casefold() == NOT_AVAILABLE:
        return None
    parts = urlsplit(normalize_url(url))
    return urlunsplit((parts.scheme, parts.netloc, "/", "", ""))


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[InstitutionEntry]:  # noqa: ARG001 - the loader's signature
    """The hospitals, colleges and universities, by type and then name."""
    opened = files[DIRECTORY.name]
    found: list[InstitutionEntry] = []
    applied: set[str] = set()
    for row in opened.rows:
        institution_type = TYPES.get(row["Institution type"])
        if institution_type is None:
            continue
        name, aliases = split_name(row["Name of institution"])
        if name in LEFT_OUT:
            logger.info("left out %s: %s", name, LEFT_OUT[name])
            continue
        fields = OVERRIDES.get(name, {})
        if fields:
            applied.add(name)
            logger.info("override: %s: %s", name, fields["reason"])
        city = as_text(row["City"])
        if city.casefold() == NOT_AVAILABLE and "place" not in fields:
            logger.warning("%s has no city in the directory", name)
        where = location_of(fields.get("place") or city)
        homepage = fields["homepage"] if "homepage" in fields else homepage_of(row["Website"])
        current = fields.get("name")
        if current:
            aliases.append(AliasEntry(text=name))
            name = current
        citation = Citation(source=DIRECTORY.name, line=row.line)
        citations: dict[Fact, Citation] = {"institution": citation}
        if homepage is not None:
            citations["homepage"] = citation
        found.append(
            InstitutionEntry(
                name=name,
                aliases=tuple(aliases),
                language=fields.get("language") or "en",
                institution_type=institution_type,
                place=where.place,
                place_level=where.level,
                place_parent=where.parent,
                homepage=homepage,
                citations=citations,
            )
        )
    for name, fields in OVERRIDES.items():
        if name not in applied:
            logger.warning("override changed nothing: %s: %s (no such row)", name, fields["reason"])
    order = {institution_type: index for index, institution_type in enumerate(TYPES.values())}
    return sorted(found, key=lambda entry: (order[entry.institution_type], name_key(entry.name)))
