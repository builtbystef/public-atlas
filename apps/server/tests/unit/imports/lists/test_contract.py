"""What the loader needs of every list's entries, checked on every list: each citation points
at a line of a listed source and that line names the entry; a homepage is a URL cited on a
line that carries its host; a place sits at one of the country's levels with the codes and the
figure its list pins; every place is loaded under its parent and apart from its namesakes; and
every institution sits at one loaded place, serves loaded places and names a parent loaded
before it. The lists that differ in a detail say so in the tables below; a list's own tests
keep the rules only it has."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import Citation, Entry, InstitutionEntry, PlaceEntry
from public_atlas.modules.imports.lists import LISTS
from public_atlas.modules.imports.lists.canada.ontario import fippa_bodies
from public_atlas.shared.text import name_key

pytestmark = pytest.mark.lists


@dataclass(frozen=True)
class Places:
    """What a places list's codes and figures are: the schemes its codes come in, each with
    the prefix every value starts with, the years its population figures may carry, and the
    lists loaded before it whose places its parents are (the seed's anchors always are)."""

    schemes: dict[IdentifierScheme, str]
    years: frozenset[int]
    after: tuple[str, ...] = ()


SGC = IdentifierScheme.STATCAN_SGC
CENSUS = frozenset({2021})
PLACES = {
    "canada/alberta/places": Places({SGC: "48"}, CENSUS),
    "canada/british_columbia/places": Places({SGC: "59"}, CENSUS),
    "canada/manitoba/places": Places({SGC: "46"}, CENSUS),
    # New Brunswick's local governments are post-census: coded, with no figure yet.
    "canada/new_brunswick/places": Places({SGC: "13"}, frozenset()),
    "canada/newfoundland/places": Places({SGC: "10"}, CENSUS),
    "canada/nova_scotia/places": Places({SGC: "12"}, CENSUS),
    "canada/ontario/places": Places({SGC: "35"}, CENSUS),
    "canada/pei/places": Places({SGC: "11"}, CENSUS),
    # An MRC the census has no division for goes by its directory code; the decree's figures
    # sit beside the census's.
    "canada/quebec/places": Places({SGC: "24", IdentifierScheme.MAMH: ""}, frozenset({2021, 2026})),
    "canada/saskatchewan/places": Places({SGC: "47"}, CENSUS),
    "canada/territories/places": Places({SGC: "6"}, CENSUS),
    "us/states_counties": Places({IdentifierScheme.FIPS: ""}, frozenset({2025})),
    "us/municipalities": Places(
        {IdentifierScheme.FIPS: ""}, frozenset({2025}), after=("us/states_counties",)
    ),
    # The sheet adds to places the two lists above load: no figure of its own.
    "us/government_units": Places(
        {IdentifierScheme.FIPS: ""}, frozenset(), after=("us/states_counties", "us/municipalities")
    ),
}
# The lists that load institutions, with the places lists each attaches its bodies to: the
# seed's anchors alone for a federal list, a list's own places for one that loads both.
ONTARIO = ("canada/ontario/places",)
US = ("us/states_counties", "us/municipalities")
ATTACHED_TO = {
    "canada/federal": (),
    "canada/alberta/places": ("canada/alberta/places",),
    "canada/quebec/places": ("canada/quebec/places",),
    "canada/ontario/agencies": ONTARIO,
    "canada/ontario/conservation_authorities": ONTARIO,
    "canada/ontario/fippa_bodies": ONTARIO,
    "canada/ontario/health_units": ONTARIO,
    "canada/ontario/libraries": ONTARIO,
    "canada/ontario/police_boards": ONTARIO,
    "canada/ontario/school_boards": ONTARIO,
    "canada/ontario/service_managers": ONTARIO,
    "us/federal": (),
    "us/transit": US,
    "us/special_districts": US,
    "us/school_districts": US,
    "us/universities": US,
}

# How a list's file writes an entry where the line does not carry the name as the entry has
# it: the loader quotes the line and a person checks it against the name.
WRITTEN_AS: dict[str, Callable[[Entry, str], bool]] = {
    # The directory's HTML is cited; the names are read from its text.
    "canada/ontario/fippa_bodies": lambda entry, line: _names_in(entry, fippa_bodies.as_text(line)),
    # The page's heading is "Police Service Board - Aylmer (Town of)".
    "canada/ontario/police_boards": lambda entry, line: (
        _normal(entry.name.removesuffix(" Police Service Board").removesuffix(" Regional"))
        in _normal(line)
    ),
    # A service's name is composed from the row's agency, trade name and division cells.
    "us/transit": lambda entry, line: all(
        word in _normal(line) for word in _normal(entry.name).split()
    ),
}
# How a list's file gives a website where the cited line does not carry the host: the
# territories' community pages link the site from a "Website" line.
SITE_LINE_SAYS: dict[str, str] = {"canada/territories/places": "website"}


def _normal(text: str) -> str:
    return " ".join(text.split()).casefold()


def _names_in(entry: Entry, line: str) -> bool:
    """Whether the line carries the entry's name or one of its aliases, read loosely: case and
    runs of whitespace aside, and the and-words and punctuation evened out failing that. A
    place's line may carry its code instead: a list that misspells a name still codes it."""
    names = [entry.name, *(alias.text for alias in entry.aliases)]
    text = _normal(line)
    if any(_normal(name) in text for name in names):
        return True
    if isinstance(entry, PlaceEntry) and entry.code.value in line:
        return True
    key = name_key(line)
    return any(name_key(name) in key for name in names)


def _own(entry: Entry) -> Citation:
    return entry.citations["place" if isinstance(entry, PlaceEntry) else "institution"]


def _citations(entry: Entry) -> list[Citation]:
    found = list(entry.citations.values())
    if isinstance(entry, PlaceEntry):
        found.extend(figure.citation for figure in entry.figures)
    return found


def _host(url: str) -> str:
    host = url.split("://", 1)[1].split("/", 1)[0].casefold()
    return host.removeprefix("www.")


def _parse_marked(name: str) -> Any:
    """Lists read from a PDF run with the `parse` tests."""
    marks = (
        [pytest.mark.parse]
        if any(source.format is files.Format.PDF for source in LISTS[name].SOURCES)
        else []
    )
    return pytest.param(name, marks=marks, id=name)


every_list = pytest.mark.parametrize("name", [_parse_marked(name) for name in LISTS])
places_lists = pytest.mark.parametrize("name", [_parse_marked(name) for name in PLACES])
institution_lists = pytest.mark.parametrize("name", [_parse_marked(name) for name in ATTACHED_TO])


@every_list
def test_every_citation_points_at_a_line_of_a_listed_source_that_names_the_entry(
    name: str,
    entries_of: Callable[[str], list[Entry]],
    sources_of: Any,
):
    opened = sources_of(LISTS[name])
    written_as = WRITTEN_AS.get(name, _names_in)
    for entry in entries_of(name):
        for citation in _citations(entry):
            assert citation.source in opened, (entry.name, citation)
            assert 1 <= citation.line <= len(opened[citation.source].lines), (entry.name, citation)
        own = _own(entry)
        assert written_as(entry, opened[own.source].line(own.line)), (entry.name, own)


@every_list
def test_a_homepage_is_a_url_cited_on_a_line_that_carries_its_host(
    name: str,
    entries_of: Callable[[str], list[Entry]],
    sources_of: Any,
):
    opened = sources_of(LISTS[name])
    for entry in entries_of(name):
        if entry.homepage is None:
            assert "homepage" not in entry.citations, entry.name
            continue
        assert entry.homepage.startswith(("http://", "https://")), entry.name
        citation = entry.citations["homepage"]
        line = _normal(opened[citation.source].line(citation.line)).replace("https//", "https://")
        assert _host(entry.homepage) in line or SITE_LINE_SAYS.get(name, "\0") in line, (
            entry.name,
            entry.homepage,
            line,
        )


@places_lists
def test_places_sit_at_the_countrys_levels_with_their_codes_and_figures(
    name: str,
    entries_of: Callable[[str], list[Entry]],
    rules_for: Any,
):
    rules = rules_for(LISTS[name].COUNTRY)
    top = rules.levels_by_rank[0].name
    spec = PLACES[name]
    codes: list[tuple[IdentifierScheme, str]] = []
    for entry in entries_of(name):
        if not isinstance(entry, PlaceEntry):
            continue
        assert entry.level in rules.levels, (entry.name, entry.level)
        assert (entry.parent is None) == (entry.level == top), entry.name
        if entry.parent_level is not None:
            assert entry.parent_level in rules.levels_above(entry.level), entry.name
        codes.extend((code.scheme, code.value) for code in (entry.code, *entry.codes))
        assert entry.code.scheme in spec.schemes, (entry.name, entry.code)
        assert entry.code.value.startswith(spec.schemes[entry.code.scheme]), entry.code
        for figure in entry.figures:
            assert figure.name is MetricName.POPULATION, entry.name
            assert figure.year in spec.years, (entry.name, figure.year)
            assert figure.value >= 0, entry.name
    assert len(set(codes)) == len(codes)


@places_lists
def test_every_place_is_loaded_under_its_parent_and_apart_from_its_namesakes(
    name: str,
    loaded_places_of: Any,
):
    loaded = loaded_places_of(LISTS[name].COUNTRY, (*PLACES[name].after, name))
    assert loaded.skipped == []
    assert loaded.merged == []


@institution_lists
def test_every_institution_sits_at_one_loaded_place_and_names_a_parent_before_it(
    name: str,
    entries_of: Callable[[str], list[Entry]],
    rules_for: Any,
    loaded_places_of: Any,
):
    rules: countries.CountryRules = rules_for(LISTS[name].COUNTRY)
    loaded = loaded_places_of(LISTS[name].COUNTRY, ATTACHED_TO[name])
    entries = entries_of(name)
    before: dict[tuple[str, str | None, str | None], set[str]] = {}
    codes: list[tuple[IdentifierScheme, str]] = []
    for entry in entries:
        if not isinstance(entry, InstitutionEntry):
            continue
        assert entry.institution_type in rules.institution_types, (
            entry.name,
            entry.institution_type,
        )
        where = (entry.place, entry.place_level, entry.place_parent)
        found = loaded.find(*where)
        assert len(found) == 1, (entry.name, where, [place.parent for place in found])
        for served in entry.served_places:
            at = loaded.find(served.name, served.level, served.parent)
            assert len(at) == 1, (entry.name, served, [place.parent for place in at])
        if entry.parent_institution is not None:
            assert name_key(entry.parent_institution) in before.get(where, set()), (
                entry.name,
                entry.parent_institution,
            )
        names = before.setdefault(where, set())
        names.update(name_key(text) for text in (entry.name, *(a.text for a in entry.aliases)))
        codes.extend((code.scheme, code.value) for code in entry.codes)
    assert len(set(codes)) == len(codes)
