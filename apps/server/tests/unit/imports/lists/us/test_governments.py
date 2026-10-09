"""The shared Census of Governments reader: names in capitals recased, web addresses cleaned,
legal names taken apart."""

from public_atlas.modules.imports.lists.us import governments


def test_a_name_in_capitals_is_recased_as_a_page_writes_it():
    assert governments.title_case("PRATTVILLE HOUSING AUTHORITY") == "Prattville Housing Authority"
    assert governments.title_case("HARRIS COUNTY MUD 400") == "Harris County MUD 400"
    assert (
        governments.title_case("MCHENRY TOWNSHIP FIRE PROTECTION DISTRICT")
        == "McHenry Township Fire Protection District"
    )
    assert governments.title_case("3RD STREET BRIDGE AUTHORITY") == "3rd Street Bridge Authority"
    assert governments.title_case("CITY OF ST. LOUIS") == "City of St. Louis"
    assert governments.title_case("O'FALLON FIRE DISTRICT") == "O'Fallon Fire District"
    assert governments.title_case("WOMEN'S HOSPITAL DISTRICT") == "Women's Hospital District"

    assert governments.title_case("DISTRICT NO. 1 OF THE TOWN") == "District No. 1 of the Town"
    assert governments.title_case("SOUTH SAN JOAQUIN FIRE AUTHORITY (SSJCFA)") == (
        "South San Joaquin Fire Authority (Ssjcfa)"
    )
    assert governments.title_case("LA JOLLA-DE ANZA WATER DISTRICT II") == (
        "La Jolla-de Anza Water District II"
    )
    assert governments.title_case("THE CITY") == "The City"


def test_a_web_address_is_cleaned_or_refused():
    assert governments.website("http://www.autaugaco.org") == "http://www.autaugaco.org/"
    assert governments.website("WWW.ROCHESTERLIBRARY.ORG") == "http://www.rochesterlibrary.org/"
    assert governments.website("http:www.galatiak12.org") == "http://www.galatiak12.org/"
    assert governments.website(" https://x.example/a ") == "https://x.example/a"
    assert governments.website(None) is None
    assert governments.website("") is None
    assert governments.website(" ") is None
    assert governments.website("new website not working yet") is None
    assert governments.website("mayor@example.gov") is None
    assert governments.website("N/A") is None
    assert governments.website("http://") is None


def test_a_legal_name_is_its_designator_and_the_name_after_of():
    assert governments.split_legal_name("CITY OF SPRINGFIELD") == ("City", "SPRINGFIELD")
    assert governments.split_legal_name("CHARTER TOWNSHIP OF CANTON") == (
        "Charter Township",
        "CANTON",
    )
    assert governments.split_legal_name("CITY AND COUNTY OF DENVER") == (
        "City and County",
        "DENVER",
    )
    assert governments.split_legal_name("UNIFIED GOVERNMENT OF ATHENS-CLARKE COUNTY") == (
        "Unified Government",
        "ATHENS-CLARKE COUNTY",
    )
    assert governments.split_legal_name("BUTTE-SILVER BOW") is None
    assert governments.split_legal_name("CITY OF") is None
    assert governments.same_letters("ST MARTIN", "St. Martin")
    assert governments.same_letters("SEWALLS POINT", "Sewall's Point")
    assert governments.same_letters("DE FOREST", "DeForest")
    assert not governments.same_letters("TEMPLE", "Temple City")


def test_the_workbook_file_renders_both_sheets_with_the_columns_each_has():
    assert governments.GOVT_UNITS.sheets == ("General Purpose", "Special District")
    columns = governments.GOVT_UNITS.columns
    assert columns is not None
    assert {"UNIT_TYPE", "FUNCTION_NAME"} <= set(columns)

    assert governments.GOVT_UNITS.member == "Govt_Units_2022_Final.xlsx"
