"""The shared Census Bureau readers: a census name comes apart into its place name and kind,
the legal name is composed from the kind, a state's government is named by its form, and the
estimates file is read into units with their FIPS codes and the county holding most of a
place."""

import pytest

from public_atlas.modules.evidence.service import content_hash
from public_atlas.modules.imports.entries import Citation
from public_atlas.modules.imports.files import Format, ListFile, render
from public_atlas.modules.imports.lists.us import census


@pytest.mark.parametrize(
    ("name", "base", "kind", "legal"),
    [
        ("Springfield city", "Springfield", "city", "City of Springfield"),
        ("Canton charter township", "Canton", "charter township", "Charter Township of Canton"),
        ("Cyr plantation", "Cyr", "plantation", "Cyr Plantation"),
        ("Anchorage municipality", "Anchorage", "municipality", "Municipality of Anchorage"),
        ("Juneau city and borough", "Juneau", "city and borough", "City and Borough of Juneau"),
        (
            "Lexington-Fayette urban county",
            "Lexington-Fayette",
            "urban county",
            "Lexington-Fayette Urban County Government",
        ),
        (
            "Athens-Clarke County unified government",
            "Athens-Clarke County",
            "unified government",
            "Athens-Clarke County Unified Government",
        ),
        ("Carson City", "Carson City", None, "Carson City"),
        ("Carson City city", "Carson City", "city", "City of Carson City"),
        ("Township 1", "Township 1", None, "Township 1"),
        ("Cook County", "Cook County", None, "Cook County"),
    ],
)
def test_a_census_name_comes_apart_and_the_legal_name_is_composed(name, base, kind, legal):
    assert census.split_name(name) == (base, kind)
    assert census.legal_name(base, kind) == legal


def test_a_county_part_and_a_balance_are_parts():
    assert census.is_part("New York city (pt.)")
    assert census.is_part("Indianapolis city (balance)")
    assert not census.is_part("Indianapolis city")


def test_a_states_government_is_named_by_its_form():
    assert census.state_government("Ohio") == "State of Ohio"
    assert census.state_government("Kentucky") == "Commonwealth of Kentucky"
    assert census.state_government("Puerto Rico") == "Commonwealth of Puerto Rico"
    assert census.state_government("District of Columbia") == (
        "Government of the District of Columbia"
    )


def test_the_functional_status_rule():
    assert {"A", "B", "C"} == census.ACTIVE
    assert set(census.FUNCTIONAL_STATUS) > census.ACTIVE


ROWS = [
    "SUMLEV,STATE,COUNTY,PLACE,COUSUB,CONCIT,PRIMGEO_FLAG,FUNCSTAT,NAME,STNAME,POPESTIMATE2025",
    "040,36,000,00000,00000,00000,0,A,New York,New York,19800000",
    "050,36,029,00000,00000,00000,0,A,Erie County,New York,950000",
    "050,36,047,00000,00000,00000,0,C,Kings County,New York,2650000",
    "061,36,029,00000,32402,00000,1,A,Hamburg town,New York,59000",
    "071,36,029,32396,32402,00000,0,A,Hamburg village,New York,9000",
    "157,36,047,51000,00000,00000,1,A,New York city (pt.),New York,2650000",
    "157,36,061,51000,00000,00000,1,A,New York city (pt.),New York,1660000",
    "162,36,000,32396,00000,00000,0,A,Hamburg village,New York,9000",
    "162,36,000,51000,00000,00000,0,A,New York city,New York,8400000",
    "170,18,000,00000,00000,36000,0,A,Indianapolis city,Indiana,910000",
    "172,18,000,36003,00000,36000,0,F,Indianapolis city (balance),Indiana,880000",
]


def estimates() -> census.Estimates:
    data = "\n".join(ROWS).encode("cp1252")
    file = ListFile(
        name="tiny_estimates",
        title="A tiny SUB-EST2025",
        url="https://census.example/sub-est2025.csv",
        sha256=content_hash(data),
        format=Format.CSV,
        encoding="cp1252",
        columns=census.SUB_EST.columns,
    )
    return census.Estimates(render(file, data))


def test_units_carry_their_fips_code_status_population_and_line():
    found = estimates()
    (state,) = found.units(census.SUMLEV_STATE)
    assert (state.fips, state.name, state.population, state.line) == (
        "36",
        "New York",
        19800000,
        2,
    )
    assert state.citation == Citation(source=census.SUB_EST.name, line=2)
    assert (state.figure.year, state.figure.value) == (2025, 19800000)
    erie, kings = found.units(census.SUMLEV_COUNTY)
    assert (erie.fips, erie.active) == ("36029", True)
    assert (kings.fips, kings.funcstat, kings.active) == ("36047", "C", True)
    assert found.active_counties().keys() == {"36029", "36047"}
    (hamburg,) = found.units(census.SUMLEV_SUBDIVISION)
    assert hamburg.fips == "3602932402"
    village, new_york = found.units(census.SUMLEV_PLACE)
    assert (village.fips, new_york.fips) == ("3632396", "3651000")
    (indianapolis,) = found.units(census.SUMLEV_CONSOLIDATED_CITY)
    assert indianapolis.fips == "1836000"
    assert found.state_names == {"36": "New York"}


def test_a_places_main_county_holds_most_of_its_population():
    found = estimates()
    village, new_york = found.units(census.SUMLEV_PLACE)
    assert found.main_county(new_york) == "047"
    # No county part in this file.
    assert found.main_county(village) is None
    assert [part.name for part in found.places_within["36", "029", "32402"]] == ["Hamburg village"]
    (balance,) = found.consolidated_parts["18", "36000"]
    assert balance.name == "Indianapolis city (balance)"
