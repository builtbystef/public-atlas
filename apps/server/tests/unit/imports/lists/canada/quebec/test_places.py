"""The Quebec places list: `entries()` on the cached files keeps every rule, the counts are
pinned, and a few places show the rules a count cannot. The files are fetched into the lists
cache when they are not there; without the network the module's tests are skipped."""

from collections import Counter
from collections.abc import Callable

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import Code, InstitutionEntry, PlaceEntry
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.quebec import places as quebec_places

from .conftest import open_sources

# Every MRC: the 81 the census counts as divisions and the six loaded from the directory alone.
REGIONS = 87
MRCS_WITHOUT_DIVISION = 6
# The census's 1,131 municipalities less the 17 merged or recoded since, plus the 9 the
# directory has since created.
CENSUS_MUNICIPALITIES = 1131
MERGED = 17
CREATED = 9
MUNICIPALITIES = CENSUS_MUNICIPALITIES - MERGED + CREATED
# The two communautés métropolitaines and the Kativik administration.
INSTITUTIONS = 3
# The cities of the TÉ divisions and the municipalities of Nord-du-Québec and of the Kativik
# administration, which have no MRC.
UNDER_THE_PROVINCE = 68
HOMEPAGES = 1189
# Places the directory names otherwise than the census (an MRC and six municipalities).
RENAMED = 7
DROPPED_SUBDIVISIONS = {"IRI": 27, "NO": 96, "S-É": 5, "TC": 9, "TI": 13, "TK": 1}
DROPPED_DIRECTORY_ROWS = 158
SERVED_PLACES = {
    "Communauté métropolitaine de Montréal": 82,
    "Communauté métropolitaine de Québec": 28,
    "Administration régionale Kativik": 15,
}
# Municipal names two places go by, each told apart by its code: the research's 32, less the
# two Plessisvilles that merged and the Sainte-Jeanne-d'Arc the directory has renamed.
NAMESAKES = 30
# Of them, the pairs under one MRC: a ville and a paroisse, a canton and a village, which the
# loader tells apart by their designators.
SIBLING_NAMESAKES = 9


@pytest.fixture(scope="module")
def opened() -> dict[str, files.OpenedFile]:
    return open_sources(quebec_places)


@pytest.fixture(scope="module")
def built(
    opened: dict[str, files.OpenedFile],
) -> tuple[list[PlaceEntry | InstitutionEntry], quebec_places.Notes]:
    return quebec_places.build(opened)


@pytest.fixture(scope="module")
def entries(
    built: tuple[list[PlaceEntry | InstitutionEntry], quebec_places.Notes],
) -> list[PlaceEntry | InstitutionEntry]:
    return built[0]


@pytest.fixture(scope="module")
def notes(
    built: tuple[list[PlaceEntry | InstitutionEntry], quebec_places.Notes],
) -> quebec_places.Notes:
    return built[1]


@pytest.fixture(scope="module")
def regions(entries: list[PlaceEntry | InstitutionEntry]) -> list[PlaceEntry]:
    return [e for e in entries if isinstance(e, PlaceEntry) and e.level == quebec_places.REGION]


@pytest.fixture(scope="module")
def municipalities(entries: list[PlaceEntry | InstitutionEntry]) -> list[PlaceEntry]:
    return [
        e for e in entries if isinstance(e, PlaceEntry) and e.level == quebec_places.MUNICIPALITY
    ]


@pytest.fixture(scope="module")
def institutions(entries: list[PlaceEntry | InstitutionEntry]) -> list[InstitutionEntry]:
    return [e for e in entries if isinstance(e, InstitutionEntry)]


@pytest.fixture(scope="module")
def by_code(entries: list[PlaceEntry | InstitutionEntry]) -> dict[str, PlaceEntry]:
    return {e.code.value: e for e in entries if isinstance(e, PlaceEntry)}


@pytest.fixture(scope="module")
def by_name(institutions: list[InstitutionEntry]) -> dict[str, InstitutionEntry]:
    return {entry.name: entry for entry in institutions}


def test_the_counts(
    entries: list[PlaceEntry | InstitutionEntry],
    regions: list[PlaceEntry],
    municipalities: list[PlaceEntry],
    institutions: list[InstitutionEntry],
    notes: quebec_places.Notes,
    opened: dict[str, files.OpenedFile],
    rules: countries.CountryRules,
):
    assert len(quebec_places.entries(opened, rules)) == len(entries)
    assert len(regions) == REGIONS
    assert len(municipalities) == MUNICIPALITIES
    assert len(institutions) == INSTITUTIONS
    assert len(entries) == REGIONS + MUNICIPALITIES + INSTITUTIONS
    assert all(entry.government for entry in regions + municipalities)
    assert sum(1 for entry in entries if entry.homepage) == HOMEPAGES
    assert sum(1 for entry in municipalities if entry.parent == quebec_places.PROVINCE) == (
        UNDER_THE_PROVINCE
    )
    codes = [entry.code.value for entry in regions + municipalities]
    assert len(set(codes)) == len(codes)
    assert sum(1 for entry in regions if entry.code.scheme is IdentifierScheme.MAMH) == (
        MRCS_WITHOUT_DIVISION
    )
    assert sum(1 for entry in regions if entry.codes) == REGIONS - MRCS_WITHOUT_DIVISION
    assert dict(notes.dropped) == DROPPED_SUBDIVISIONS
    assert sum(notes.directory_dropped.values()) == DROPPED_DIRECTORY_ROWS
    assert len(notes.merged) == MERGED
    assert len(notes.created) == CREATED
    assert len(notes.renamed) == RENAMED
    assert len(notes.mrcs_without_division) == MRCS_WITHOUT_DIVISION
    assert {entry.name: len(entry.served_places) for entry in institutions} == SERVED_PLACES
    names = Counter(entry.name for entry in municipalities)
    assert sum(1 for count in names.values() if count > 1) == NAMESAKES


def test_every_place_has_its_code_populations_and_a_government_named_after_it(
    regions: list[PlaceEntry],
    municipalities: list[PlaceEntry],
    rules: countries.CountryRules,
    opened: dict[str, files.OpenedFile],
    notes: quebec_places.Notes,
):
    naming = rules.naming
    census = opened[statcan.POPULATION.name]
    created = {line.split(" ", 1)[0] for line in notes.created}
    without_division = {line.split(" ", 1)[0] for line in notes.mrcs_without_division}
    for entry in regions + municipalities:
        assert entry.code.value.isdigit()
        assert entry.language == "fr"
        years = {(figure.name, figure.year) for figure in entry.figures}
        assert (MetricName.POPULATION, quebec_places.DECREE_YEAR) in years
        assert all(figure.value >= 0 for figure in entry.figures)
        line = opened[entry.citations["place"].source].line(entry.citations["place"].line)
        if entry.code.scheme is IdentifierScheme.MAMH:
            # An MRC the census has no division for, loaded from the directory alone: its
            # directory code is its code, the directory's line is cited, no census figure.
            assert entry.code.value in without_division
            assert entry.codes == ()
            assert entry.citations["place"].source == quebec_places.MRCS.name
            assert (MetricName.POPULATION, statcan.CENSUS_YEAR) not in years
            assert f"AR{entry.code.value}" in line
        elif entry.code.value[2:] in created:
            # Loaded from the directory alone: no census figure, the directory's line cited.
            assert entry.code.scheme is IdentifierScheme.STATCAN_SGC
            assert entry.code.value.startswith(quebec_places.PROVINCE_CODE)
            assert entry.citations["place"].source == quebec_places.MUNICIPALITIES.name
            assert (MetricName.POPULATION, statcan.CENSUS_YEAR) not in years
            assert entry.code.value[2:] in line
        else:
            assert entry.code.scheme is IdentifierScheme.STATCAN_SGC
            assert entry.code.value.startswith(quebec_places.PROVINCE_CODE)
            assert entry.citations["place"].source == statcan.POPULATION.name
            assert (MetricName.POPULATION, statcan.CENSUS_YEAR) in years
            assert entry.code.value in line
            assert line is census.line(entry.citations["place"].line)
        assert any(name in line for name in (entry.name, *(a.text for a in entry.aliases)))
        # "Ville de Québec" governs "Québec": the place's name sits whole in its government's,
        # less an article the connector contracts ("MRC du Domaine-du-Roy").
        assert entry.government is not None
        stem = naming.key(entry.name)
        for article in ("le ", "les ", "des "):
            stem = stem.removeprefix(article)
        assert stem in naming.key(entry.government), entry.name
        assert entry.citations["government"].source in (
            quebec_places.MUNICIPALITIES.name,
            quebec_places.MRCS.name,
        )


def test_every_homepage_is_the_directorys_link(
    entries: list[PlaceEntry | InstitutionEntry], opened: dict[str, files.OpenedFile]
):
    for entry in entries:
        if entry.homepage is None:
            continue
        assert entry.homepage.startswith(("http://", "https://"))
        citation = entry.citations["homepage"]
        assert citation.source in (quebec_places.MUNICIPALITIES.name, quebec_places.MRCS.name)
        line = opened[citation.source].line(citation.line)
        host = entry.homepage.removeprefix("http://").removeprefix("https://").rstrip("/")
        assert host.lower() in line.lower(), entry.name


def test_regions_sit_under_quebec_and_municipalities_under_the_mrc_the_directory_names(
    regions: list[PlaceEntry], municipalities: list[PlaceEntry], by_code: dict[str, PlaceEntry]
):
    region_names = {entry.name for entry in regions}
    assert all(entry.parent == quebec_places.PROVINCE for entry in regions)
    assert all(entry.parent_level == quebec_places.PROVINCE_LEVEL for entry in regions)
    for entry in municipalities:
        if entry.parent == quebec_places.PROVINCE:
            assert (entry.parent_level, entry.parent_parent) == (
                quebec_places.PROVINCE_LEVEL,
                None,
            )
        else:
            assert entry.parent in region_names, entry.name
            assert (entry.parent_level, entry.parent_parent) == (
                quebec_places.REGION,
                quebec_places.PROVINCE,
            )
    # The directory's MRC, not the census division: Trois-Rivières is counted in Francheville
    # with the municipalities of Des Chenaux, and Québec's division is a TÉ.
    assert by_code["2437067"].name == "Trois-Rivières"
    assert by_code["2437067"].parent == quebec_places.PROVINCE
    assert by_code["2437210"].name == "Batiscan"
    assert by_code["2437210"].parent == "Des Chenaux"
    assert by_code["2423027"].parent == quebec_places.PROVINCE
    assert by_code["2446050"].parent == "Brome-Missisquoi"
    # An MRC's code is its division's, with the directory's beside it.
    assert by_code["2446"].name == "Brome-Missisquoi"
    assert by_code["2446"].government == "Municipalité régionale de comté de Brome-Missisquoi"
    assert by_code["2446"].codes == (Code(scheme=IdentifierScheme.MAMH, value="460"),)
    # An MRC the census has no division for is a region by the directory's code alone.
    chenaux = by_code["372"]
    assert (chenaux.name, chenaux.government) == (
        "Des Chenaux",
        "Municipalité régionale de comté des Chenaux",
    )
    assert chenaux.aliases[0].text == "MRC des Chenaux"
    assert chenaux.homepage == "http://www.mrcdeschenaux.ca/"
    assert chenaux.citations["place"] == chenaux.citations["government"]
    assert {entry.name for entry in regions if entry.code.scheme is IdentifierScheme.MAMH} == {
        "Des Chenaux",
        "Le Fjord-du-Saguenay",
        "Sept-Rivières",
        "Caniapiscau",
        "Minganie",
        "Le Golfe-du-Saint-Laurent",
    }


def test_the_places_that_show_the_rules(by_code: dict[str, PlaceEntry]):
    quebec = by_code["2423027"]
    assert (quebec.name, quebec.government) == ("Québec", "Ville de Québec")
    assert quebec.homepage == "http://www.ville.quebec.qc.ca/"
    assert by_code["2431056"].government == "Municipalité d'Adstock"
    assert by_code["2466062"].government == "Ville de Hampstead"
    assert by_code["2490012"].government == "Ville de La Tuque"
    assert by_code["2401023"].government == "Municipalité des Îles-de-la-Madeleine"
    assert by_code["2460037"].government == "Ville de L'Épiphanie"
    assert by_code["2451020"].government == "Municipalité d'Yamachiche"
    assert by_code["2499060"].government == "Gouvernement régional d'Eeyou Istchee Baie-James"
    assert by_code["2499125"].government == "Village nordique d'Akulivik"
    assert by_code["2452"].government == "Municipalité régionale de comté de D'Autray"
    assert by_code["2402"].government == "Municipalité régionale de comté du Rocher-Percé"
    assert by_code["2431"].government == "Municipalité régionale de comté des Appalaches"
    assert by_code["2431"].aliases[0].text == "MRC des Appalaches"
    assert by_code["2417"].government == "Municipalité régionale de comté de L'Islet"
    assert by_code["2403"].government == "Municipalité régionale de comté de La Côte-de-Gaspé"
    # The directory's name wins; the census's is an alias.
    mont_blanc = by_code["2478047"]
    assert (mont_blanc.name, mont_blanc.government) == ("Mont-Blanc", "Municipalité de Mont-Blanc")
    assert [alias.text for alias in mont_blanc.aliases] == ["Saint-Faustin--Lac-Carré"]
    beauce_centre = by_code["2427"]
    assert beauce_centre.name == "Beauce-Centre"
    assert [alias.text for alias in beauce_centre.aliases] == [
        "MRC de Beauce-Centre",
        "Robert-Cliche",
    ]
    # The directory's designation wins over the census's type.
    assert by_code["2461013"].government == "Ville de Crabtree"
    # Two places of one name, told apart by code.
    assert by_code["2426022"].parent == "La Nouvelle-Beauce"
    assert by_code["2405050"].parent == "Bonaventure"
    assert by_code["2426022"].name == by_code["2405050"].name == "Saint-Elzéar"
    assert quebec_places.with_connector("Ville", "Hudson") == "Ville d'Hudson"
    assert quebec_places.with_connector("Canton", "Hemmingford") == "Canton de Hemmingford"
    assert quebec_places.with_connector("MRC", "Des Chenaux") == "MRC des Chenaux"


def test_the_overrides_apply_to_merged_and_recoded_municipalities(
    by_code: dict[str, PlaceEntry], notes: quebec_places.Notes
):
    created = {f"{quebec_places.PROVINCE_CODE}{line.split(' ', 1)[0]}" for line in notes.created}
    assert set(quebec_places.OVERRIDES) <= created
    assert set(quebec_places.MERGED_INTO) == {line.split(" ", 1)[0] for line in notes.merged}
    assert not set(quebec_places.MERGED_INTO) & set(by_code)
    amos = by_code["2488057"]
    assert (amos.name, amos.government, amos.parent) == ("Amos", "Ville d'Amos", "Abitibi")
    assert [(figure.year, figure.citation.source) for figure in amos.figures] == [
        (quebec_places.DECREE_YEAR, quebec_places.MUNICIPALITIES.name)
    ]
    assert by_code["2499820"].government == "Village cri d'Oujé-Bougoumou"
    # Two places of one name under one MRC, a ville and a paroisse, stay two places: the
    # loader tells them apart by their designators, so "Paroisse" is one of the country's.
    assert by_code["2431015"].government == "Ville de Disraeli"
    assert by_code["2431020"].government == "Paroisse de Disraeli"


def test_no_two_places_of_one_name_and_kind_sit_under_one_parent(
    regions: list[PlaceEntry], municipalities: list[PlaceEntry], rules: countries.CountryRules
):
    """What the loader tells apart: two places under one parent whose plain name is a form of
    the other's are bodies of different kinds by the designators around their names ("Ville de
    Disraeli" and "Paroisse de Disraeli"); any other pair would be merged into one place."""
    naming = rules.naming

    def kind(entry: PlaceEntry) -> set[int]:
        assert entry.government is not None
        return naming.designators_in(
            naming.key(entry.government).replace(naming.key(entry.name), " ")
        )

    by_parent: dict[tuple[str, str | None, str | None], list[PlaceEntry]] = {}
    for entry in regions + municipalities:
        by_parent.setdefault((entry.level, entry.parent, entry.parent_parent), []).append(entry)
    pairs = 0
    for siblings in by_parent.values():
        loaded: dict[str, list[PlaceEntry]] = {}
        for entry in sorted(siblings, key=lambda entry: entry.name):
            for form in naming.plain_forms(entry.name):
                for earlier in loaded.get(form, []):
                    pair = (earlier.name, earlier.government, entry.name, entry.government)
                    assert kind(earlier), pair
                    assert kind(entry), pair
                    assert not kind(earlier) & kind(entry), pair
                    pairs += 1
            for form in naming.forms(entry.name):
                loaded.setdefault(form, []).append(entry)
    assert pairs == SIBLING_NAMESAKES


def test_the_spanning_bodies_serve_loaded_municipalities(
    institutions: list[InstitutionEntry],
    by_name: dict[str, InstitutionEntry],
    find_places: Callable[[str, str | None, str | None], list[PlaceEntry]],
):
    for entry in institutions:
        assert entry.institution_type == quebec_places.REGIONAL_GOVERNMENT
        assert (entry.place, entry.place_level) == (
            quebec_places.PROVINCE,
            quebec_places.PROVINCE_LEVEL,
        )
        assert entry.citations["institution"].source == quebec_places.MRCS.name
        for served in entry.served_places:
            found = find_places(served.name, served.level, served.parent)
            assert len(found) == 1, (entry.name, served)
    montreal = by_name["Communauté métropolitaine de Montréal"]
    assert montreal.homepage == "http://www.cmm.qc.ca/"
    assert [alias.text for alias in montreal.aliases] == ["CMM"]
    assert {served.name for served in montreal.served_places} >= {"Montréal", "Laval", "Longueuil"}
    # Saint-Lambert is also a paroisse in Abitibi-Ouest: the served place names its parent.
    assert any(
        served
        == quebec_places.ServedPlace(name="Saint-Lambert", level="municipality", parent="Quebec")
        for served in montreal.served_places
    )
    kativik = by_name["Administration régionale Kativik"]
    assert {alias.text for alias in kativik.aliases} == {"Kativik Regional Government", "KRG"}
    assert all(served.parent == quebec_places.PROVINCE for served in kativik.served_places)
