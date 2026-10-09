"""Canada: its settings and naming rules, its administrative levels with the types expected at
each, the types it uses, its platforms, and its anchor. The pilot works Ontario alone; to widen
it, add Quebec, or Canada itself (`canada.ca`, `gc.ca`) for the federal government."""

from typing import Any

from public_atlas.modules.countries.seeds.shared import uses

SETTINGS: dict[str, Any] = {
    "country_code": "CA",
    "name": "Canada",
    # How public bodies write their names, in English and French. A government's name is a
    # place name with a designator around it: "Township of Elmwood", "Elmwood Township",
    # "Elmwood, Township of" in a list. Designators of different kinds are two bodies ("Township
    # of Elmwood", "Elmwood, City of"), so the duplicate check never offers one for the other;
    # and a site that writes the place name with another designator ("Elmwood Township" for
    # "Township of Elmwood") may still name the body when its domain is verified.
    "naming_rules": {
        # One group per kind of body; "Ville" is a city or a town.
        "designators": [
            ["City", "Ville", "Cité"],
            ["Town", "Ville", "Separated Town"],
            ["Township", "Canton"],
            ["United Townships", "Cantons unis"],
            ["Village"],
            ["Municipality", "Municipalité"],
            ["Regional Municipality", "Municipalité régionale"],
            ["District Municipality", "Municipalité de district"],
            ["County", "Comté"],
            ["United Counties", "Comtés unis"],
            ["Region", "Région"],
            ["District"],
        ],
        # What joins a designator to the place name: "Township of Elmwood", "Canton de Elmwood".
        "connectors": ["of the", "of", "de la", "de l'", "du", "des", "de", "d'"],
        # Words before a body's name that are not part of it.
        "leading": ["The Corporation of the", "Corporation of the", "The"],
        # What "&" stands for.
        "and_words": ["and", "et"],
    },
}

# The hierarchy, top-down. The expected types are the checklist for `find_institutions` at a
# place of the level: a floor, not a ceiling. A known type found at another level is saved and
# sent to review.
ADMINISTRATIVE_LEVELS: list[dict[str, Any]] = [
    {
        "name": "country",
        "rank": 1,
        "government_institution_type": "federal_government",
        "expected_institution_types": ["department", "agency", "crown_corporation"],
    },
    {
        "name": "province_territory",
        "rank": 2,
        "government_institution_type": "provincial_government",
        "expected_institution_types": [
            "ministry",
            "agency",
            "crown_corporation",
            "health_authority",
            "hospital",
            "university",
            "college",
            "school_board",
        ],
    },
    {
        "name": "region",
        "rank": 3,
        "government_institution_type": "regional_government",
        "expected_institution_types": [
            "transit_agency",
            "police_service",
            "public_utility",
            "conservation_authority",
            "public_health_unit",
            "municipal_corporation",
        ],
    },
    # A municipality sits under a region or directly under the province.
    {
        "name": "municipality",
        "rank": 4,
        "government_institution_type": "municipal_government",
        "expected_institution_types": [
            "transit_agency",
            "police_service",
            "fire_service",
            "public_utility",
            "library",
            "conservation_authority",
            "public_health_unit",
            "municipal_corporation",
        ],
    },
]

# The types Canada uses, with the default sources unless changed here. A name pattern catches a
# directory's short label ("Transportation") saved as a ministry's name without refusing a real
# one the pattern misses ("Cabinet Office"): the name is saved and goes to review.
INSTITUTION_TYPES: list[dict[str, Any]] = [
    uses("federal_government"),
    uses("provincial_government"),
    uses("regional_government"),
    uses("municipal_government"),
    uses("department"),
    uses("ministry", name_pattern=r"^(Ministry of |Ministère d)"),
    uses("agency"),
    uses("crown_corporation"),
    uses("health_authority"),
    uses("hospital"),
    uses("university"),
    uses("college"),
    uses("school_board"),
    uses("transit_agency"),
    uses("police_service"),
    uses("fire_service"),
    uses("public_utility"),
    uses("library"),
    uses("conservation_authority"),
    uses("public_health_unit"),
    uses("municipal_corporation"),
    uses("other"),
]

# Domains the agent may fetch (subdomains included) but never trusts: a page on one becomes a
# source only when a trusted page links to it. Extended by hand when a reviewer spots a new one.
PLATFORMS: list[str] = [
    "bidsandtenders.ca",
    "escribemeetings.com",
    "merx.com",
    "biddingo.com",
    "jaggaer.com",
    "civicweb.net",
    "bonfirehub.ca",
    "ariba.com",
    "questica.com",
    "catalisgov.ca",
    "allnetmeetings.com",
    # Meeting video: where councils keep their recordings.
    "youtube.com",
    "rogerstv.com",
]

# The country as a place, and the anchor: a place whose government and domains were verified by
# hand. Every host under gov.on.ca is the Government of Ontario, and the allowlist takes
# subdomains, so the one entry covers the Public Appointments Secretariat (pas.gov.on.ca, the
# list of every provincial agency by ministry, where ontario.ca's "Agencies, boards and
# commissions" page sends readers), INFO-GO (www.infogo.gov.on.ca) and the ministries' legacy
# sites such as www.mto.gov.on.ca. Agency domains such as supplyontario.ca stay out:
# find_homepage verifies them like any other candidate.
PLACES: list[dict[str, Any]] = [
    {"name": "Canada", "level": "country"},
    {
        "name": "Ontario",
        "level": "province_territory",
        "parent": "Canada",
        "government": "Government of Ontario",
        "domains": ["ontario.ca", "gov.on.ca"],
    },
]

SEED: dict[str, Any] = {
    "settings": SETTINGS,
    "administrative_levels": ADMINISTRATIVE_LEVELS,
    "institution_types": INSTITUTION_TYPES,
    "platforms": PLATFORMS,
    "places": PLACES,
}
