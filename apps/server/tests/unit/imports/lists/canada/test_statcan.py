"""The shared census tables: every province's classification covers exactly the types its
2021 files hold, and a province reads only its own rows."""

import pytest

from public_atlas.modules.evidence.service import content_hash
from public_atlas.modules.imports import files
from public_atlas.modules.imports.files import Format, ListFile
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.statcan import Province


def types_of(table: dict[str, statcan.UnitType], province: str) -> set[str]:
    return {code for code, unit in table.items() if province in unit.provinces}


@pytest.mark.parametrize("code", sorted(statcan.PROVINCES))
def test_every_division_type_of_a_province_is_an_upper_tier_a_district_or_census_only(code):
    province = Province(code)
    upper = set(province.upper_tier_types)
    district = set(province.district_types)
    census_only = set(province.census_only_types)
    assert not (upper & district), code
    assert not (upper & census_only), code
    assert not (district & census_only), code
    assert upper | district | census_only == types_of(statcan.CD_TYPES, code), code


@pytest.mark.parametrize("code", sorted(statcan.PROVINCES))
def test_every_subdivision_type_of_a_province_is_a_municipality_or_dropped(code):
    province = Province(code)
    municipal = set(province.municipal_types)
    dropped = set(province.dropped_types)
    assert not (municipal & dropped), code
    assert municipal | dropped == types_of(statcan.CSD_TYPES, code), code
    assert all(province.municipal_types.values()), code


def test_the_type_tables_name_every_code_and_province():
    for table in (statcan.CD_TYPES, statcan.CSD_TYPES):
        for code, unit in table.items():
            assert unit.code == code
            assert unit.name
            assert unit.provinces <= set(statcan.PROVINCES), code


def test_region_governments_exist_only_in_ontario_quebec_and_british_columbia():
    assert {code for code in statcan.PROVINCES if Province(code).upper_tier_types} == {
        "24",
        "35",
        "59",
    }
    assert Province("35").district_types == {"DIS"}
    assert Province("35").upper_tier_types["UC"] == "United Counties"
    assert Province("47").municipal_types["RM"] == "Rural Municipality"
    assert Province("12").municipal_types["RM"] == "Regional Municipality"
    with pytest.raises(ValueError, match="SGC code"):
        Province("99")


POPULATION_CSV = (
    'GEO,DGUID,"Population and dwelling counts (13): Population, 2021 [1]"\n'
    'Ontario,2021A000235,"14,223,942"\n'
    'Frontenac,2021A00033510,"150,475"\n'
    'Kingston,2021A00053510010,"132,485"\n'
    'Québec,2021A000224,"8,501,833"\n'
    "Not a unit,2021S05051234,12\n"
).encode()
ATTRIBUTES_CSV = (
    "PRUID_PRIDU,CDUID_DRIDU,CDNAME_DRNOM,CDTYPE_DRGENRE,CSDUID_SDRIDU,CSDNAME_SDRNOM,"
    "CSDTYPE_SDRGENRE\n"
    "35,3510,Frontenac,CTY,3510010,Kingston,CY\n"
    "24,2423,Québec,TÉ,2423027,Québec,V\n"
).encode()


def _opened(file: ListFile, data: bytes) -> files.OpenedFile:
    return files.render(
        ListFile(
            name=file.name,
            title=file.title,
            url="https://example.test/x.csv",
            sha256=content_hash(data),
            format=Format.CSV,
            columns=file.columns,
            distinct=file.distinct,
        ),
        data,
    )


def test_a_province_reads_its_own_rows_with_their_types_and_divisions():
    ontario = Province("35")
    counted = ontario.read_population(_opened(statcan.POPULATION, POPULATION_CSV))
    assert sorted(counted) == ["35", "3510", "3510010"]
    assert counted["3510010"].population == 132485
    assert counted["3510010"].names == ("Kingston",)
    assert counted["3510010"].line == 4
    ontario.read_types(counted, _opened(statcan.ATTRIBUTES, ATTRIBUTES_CSV))
    assert (counted["3510"].type_, counted["3510"].division) == ("CTY", None)
    assert (counted["3510010"].type_, counted["3510010"].division) == ("CY", "3510")
    assert counted["35"].type_ == ""

    quebec = Province("24")
    counted = quebec.read_population(_opened(statcan.POPULATION, POPULATION_CSV))
    assert sorted(counted) == ["24"]
    assert quebec.name == "Quebec"


def test_a_unit_the_attribute_file_lacks_is_an_error():
    ontario = Province("35")
    counted = ontario.read_population(_opened(statcan.POPULATION, POPULATION_CSV))
    empty = _opened(statcan.ATTRIBUTES, ATTRIBUTES_CSV.splitlines()[0] + b"\n")
    with pytest.raises(files.ListFileError, match="no type in the attribute file for 2"):
        ontario.read_types(counted, empty)
