"""The Quebec places list: the counts are pinned, a place is coded and cited by the census or
by the directory alone, each government is named from its place, municipalities sit under the
MRC the directory names, and a few places show the rules a count cannot. What every list's
entries must satisfy is checked by the contract test beside the lists."""

from collections import Counter
from typing import Any

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import Code, InstitutionEntry, PlaceEntry
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.quebec import places as quebec_places

pytestmark = pytest.mark.lists

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


@pytest.fixture(scope="module")
def opened(sources_of) -> dict[str, files.OpenedFile]:
    return sources_of(quebec_places)


@pytest.fixture(scope="module")
def built(
    opened: dict[str, files.OpenedFile],
) -> tuple[list[PlaceEntry | InstitutionEntry], quebec_places.Notes]:
    return quebec_places.build(opened)


@pytest.fixture(scope="module")
def entries(
    quebec_entries: list[PlaceEntry | InstitutionEntry],
) -> list[PlaceEntry | InstitutionEntry]:
    return quebec_entries


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
):
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


def test_a_place_is_coded_and_cited_by_the_census_or_by_the_directory_alone(
    regions: list[PlaceEntry],
    municipalities: list[PlaceEntry],
    opened: dict[str, files.OpenedFile],
    notes: quebec_places.Notes,
):
    """An MRC the census has no division for, and a municipality the directory has since
    created, are cited at the directory's line with no census figure; every other place at
    the census's, with the decree's figure beside the census's."""
    created = {line.split(" ", 1)[0] for line in notes.created}
    without_division = {line.split(" ", 1)[0] for line in notes.mrcs_without_division}
    for entry in regions + municipalities:
        assert entry.language == "fr"
        years = {(figure.name, figure.year) for figure in entry.figures}
        assert (MetricName.POPULATION, quebec_places.DECREE_YEAR) in years
        line = opened[entry.citations["place"].source].line(entry.citations["place"].line)
        if entry.code.scheme is IdentifierScheme.MAMH:
            assert entry.code.value in without_division
            assert entry.codes == ()
            assert entry.citations["place"].source == quebec_places.MRCS.name
            assert (MetricName.POPULATION, statcan.CENSUS_YEAR) not in years
            assert f"AR{entry.code.value}" in line
        elif entry.code.value[2:] in created:
            assert entry.citations["place"].source == quebec_places.MUNICIPALITIES.name
            assert (MetricName.POPULATION, statcan.CENSUS_YEAR) not in years
            assert entry.code.value[2:] in line
        else:
            assert entry.citations["place"].source == statcan.POPULATION.name
            assert (MetricName.POPULATION, statcan.CENSUS_YEAR) in years
        assert entry.citations["government"].source in (
            quebec_places.MUNICIPALITIES.name,
            quebec_places.MRCS.name,
        )


def test_every_government_is_named_from_its_place(
    regions: list[PlaceEntry], municipalities: list[PlaceEntry], rules: countries.CountryRules
):
    """ "Ville de Québec" governs "Québec": the place's name sits whole in its government's,
    less an article the connector contracts ("MRC du Domaine-du-Roy")."""
    naming = rules.naming
    for entry in regions + municipalities:
        assert entry.government is not None, entry.name
        stem = naming.key(entry.name)
        for article in ("le ", "les ", "des "):
            stem = stem.removeprefix(article)
        assert stem in naming.key(entry.government), entry.name


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


def test_a_ville_and_the_paroisse_or_canton_of_its_name_are_two_places(loaded: Any) -> None:
    """The pairs under one MRC the loader tells apart by their designators: "Paroisse" and
    "Canton" are kinds of the country's own."""
    assert [(pair.name, pair.government, pair.other_government) for pair in loaded.told_apart] == [
        ("Bedford", "Ville de Bedford", "Canton de Bedford"),
        ("Disraeli", "Ville de Disraeli", "Paroisse de Disraeli"),
        ("Hatley", "Municipalité de Hatley", "Canton de Hatley"),
        ("Hemmingford", "Village de Hemmingford", "Canton de Hemmingford"),
        (
            "Notre-Dame-du-Bon-Conseil",
            "Village de Notre-Dame-du-Bon-Conseil",
            "Paroisse de Notre-Dame-du-Bon-Conseil",
        ),
        ("Saint-Célestin", "Village de Saint-Célestin", "Municipalité de Saint-Célestin"),
        ("Senneterre", "Ville de Senneterre", "Paroisse de Senneterre"),
        ("Stanstead", "Ville de Stanstead", "Canton de Stanstead"),
        ("Valcourt", "Ville de Valcourt", "Canton de Valcourt"),
    ]


def test_the_spanning_bodies_sit_at_the_province_and_serve_the_directorys_municipalities(
    institutions: list[InstitutionEntry], by_name: dict[str, InstitutionEntry]
):
    for entry in institutions:
        assert entry.institution_type == quebec_places.REGIONAL_GOVERNMENT
        assert (entry.place, entry.place_level) == (
            quebec_places.PROVINCE,
            quebec_places.PROVINCE_LEVEL,
        )
        assert entry.citations["institution"].source == quebec_places.MRCS.name
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
