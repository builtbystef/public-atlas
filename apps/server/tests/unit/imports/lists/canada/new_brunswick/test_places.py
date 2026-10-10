"""The New Brunswick places list: `entries()` on the cached files keeps every rule, the counts
are pinned, and a few places show the rules a count cannot. The contacts list is a PDF: the
first run parses it with Docling and keeps the pages beside the cache."""

from collections import Counter

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import IdentifierScheme
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.new_brunswick import places as new_brunswick

LOCAL_GOVERNMENTS = 77
TYPED = {"C": 8, "TV": 30, "VL": 21, "RCR": 17, "MRM": 1}
RURAL_DISTRICTS = 12
HOMEPAGES = 68
DROPPED = {"IRI": 20}


@pytest.fixture(scope="module")
def opened(sources_of) -> dict[str, files.OpenedFile]:
    return sources_of(new_brunswick)


@pytest.fixture(scope="module")
def built(opened) -> tuple[list[PlaceEntry], new_brunswick.Notes]:
    return new_brunswick.build(opened)


@pytest.fixture(scope="module")
def entries(built) -> list[PlaceEntry]:
    return built[0]


@pytest.fixture(scope="module")
def by_code(entries) -> dict[str, PlaceEntry]:
    return {entry.code.value: entry for entry in entries}


def test_the_counts(entries, built, opened, rules):
    notes = built[1]
    assert len(new_brunswick.entries(opened, rules)) == len(entries)
    assert len(entries) == LOCAL_GOVERNMENTS
    changes = statcan.read_changes(
        opened[statcan.INTERIM_CHANGES.name], new_brunswick.NEW_BRUNSWICK
    )
    governments = new_brunswick.local_governments(changes, new_brunswick.Notes())
    assert Counter(change.type_ for change in governments) == TYPED
    assert len(new_brunswick.read_rows(opened[new_brunswick.CONTACTS.name])) == LOCAL_GOVERNMENTS
    assert sum(1 for entry in entries if entry.homepage) == HOMEPAGES
    assert len(notes.rural_districts) == RURAL_DISTRICTS
    assert dict(notes.dropped) == DROPPED
    assert len(notes.without_website) == LOCAL_GOVERNMENTS - HOMEPAGES
    assert notes.untaken == []
    codes = [entry.code.value for entry in entries]
    assert len(set(codes)) == len(codes)


def test_every_local_government_has_a_post_reform_code_and_no_population(
    entries, opened, rules: countries.CountryRules
):
    naming = rules.naming
    interim = opened[statcan.INTERIM_CHANGES.name]
    contacts = opened[new_brunswick.CONTACTS.name]
    for entry in entries:
        assert (entry.level, entry.parent) == ("municipality", new_brunswick.PROVINCE)
        assert entry.code.scheme is IdentifierScheme.STATCAN_SGC
        assert new_brunswick.REFORMED.match(entry.code.value)
        assert entry.figures == ()
        line = interim.line(entry.citations["place"].line)
        assert entry.code.value in line
        assert entry.government is not None
        core = naming.core(entry.government)
        # "Town of X" governs "X"; the layer may drop a period the census writes (Fort St James).
        assert core in (naming.core(entry.name), naming.key(entry.name)) or core in naming.forms(
            entry.name
        ), entry.name
        row = contacts.line(entry.citations["government"].line)
        assert entry.name in row or new_brunswick.PDF_NAMES.get(entry.name, "") in row
        if entry.homepage is not None:
            host = entry.homepage.removeprefix("http://").removeprefix("https://").rstrip("/")
            assert host.lower() in row.lower(), entry.name


def test_the_places_that_show_the_rules(by_code):
    assert by_code["1323012"].government == "City of Bathurst"
    assert by_code["1323012"].homepage == "http://bathurst.ca/"
    assert by_code["1325020"].government == "Rural Community of Alnwick"
    assert by_code["1324018"].government == "Regional Municipality of Tracadie"
    grand_sault = by_code["1321004"]
    assert (grand_sault.name, grand_sault.government) == ("Grand-Sault", "Town of Grand-Sault")
    assert [(alias.text, alias.language) for alias in grand_sault.aliases] == [
        ("Grand Falls", "en")
    ]
    # A page title in the website cell is no address.
    assert grand_sault.homepage is None
    heron_bay = by_code["1322009"]
    assert [(alias.text, alias.language) for alias in heron_bay.aliases] == [
        ("Baie-des-Hérons", "fr")
    ]
    assert by_code["1324013"].name == "Rivière-du-Nord"
    # The interim list's rural districts are not loaded.
    assert "1331111" not in by_code
