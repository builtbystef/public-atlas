"""The United States: its settings and naming rules, its four administrative levels with the
types expected at each, the types it uses, its platforms, and its anchors: the federal
government and the government of each state, the District of Columbia and Puerto Rico.

The levels follow the Census Bureau's units (lists-research section 1.1): a state is a
`provincial_government`, a county equivalent (county, parish, borough) a `regional_government`,
and a municipality (an incorporated place, or a town or township in the twenty states where
those are governments) a `municipal_government`. School and special districts are bodies under
a county or a municipality, not places. Each anchor's domains were checked on 2026-10-09 against
the "State or territory" rows of the .gov registry (`current-full.csv`): every one is
registered to that state's government or its technology office.
"""

from typing import Any

from public_atlas.modules.countries.seeds.shared import uses

SETTINGS: dict[str, Any] = {
    "country_code": "US",
    "name": "United States",
    # How public bodies write their names. The legal form puts the designator first ("City of
    # Springfield", "Charter Township of Canton"); the census puts a lowercase kind after the
    # name ("Springfield city", "Canton charter township"), and a site may write either. The
    # groups tell a town from the village of the same name inside it, which both govern.
    "naming_rules": {
        "designators": [
            ["City"],
            ["Town"],
            ["Township", "Charter Township", "Civil Township", "Metro Township"],
            ["Village"],
            ["Borough"],
            ["County"],
            ["Parish"],
            ["Plantation"],
            ["Municipality", "Municipio"],
            # Both spellings: the rules read "and" as "&" in a name's key, and a designator must
            # be found in both the key ("city & county of denver") and the plain text.
            ["City and County", "City & County", "City and Borough", "City & Borough"],
            [
                "Consolidated Government",
                "Unified Government",
                "Metropolitan Government",
                "Metro Government",
                "Urban County Government",
                "City-Parish",
            ],
            ["State", "Commonwealth"],
            ["Territory"],
        ],
        # What joins a designator to the place name: "City of Springfield", "Government of the
        # District of Columbia".
        "connectors": ["of the", "of"],
        # Words before a body's name that are not part of it.
        "leading": ["The"],
        # What "&" stands for.
        "and_words": ["and"],
    },
}

# The bodies a county or a municipality has of its own: school and special districts, which
# the Census of Governments lists, and the corporations a government owns.
LOCAL_TYPES = [
    "school_board",
    "education_service_agency",
    "fire_service",
    "public_utility",
    "transit_agency",
    "library",
    "hospital",
    "park_district",
    "conservation_authority",
    "airport_authority",
    "port_authority",
    "housing_authority",
    "municipal_corporation",
]

# The hierarchy, top-down. The expected types are the checklist for `find_institutions` at a
# place of the level: a floor, not a ceiling.
ADMINISTRATIVE_LEVELS: list[dict[str, Any]] = [
    {
        "name": "country",
        "rank": 1,
        "government_institution_type": "federal_government",
        "expected_institution_types": ["department", "agency", "crown_corporation"],
    },
    {
        "name": "state",
        "rank": 2,
        "government_institution_type": "provincial_government",
        "expected_institution_types": [
            "department",
            "agency",
            "crown_corporation",
            "public_authority",
            "university",
            "college",
            "hospital",
            "transit_agency",
        ],
    },
    # A county, parish, borough or other county equivalent.
    {
        "name": "county",
        "rank": 3,
        "government_institution_type": "regional_government",
        "expected_institution_types": LOCAL_TYPES,
    },
    # A municipality sits under its county, or directly under the state where it is independent
    # of any county or its county is no government.
    {
        "name": "municipality",
        "rank": 4,
        "government_institution_type": "municipal_government",
        "expected_institution_types": LOCAL_TYPES,
    },
]

# The types the United States uses, with the default sources unless changed here. A state's
# bodies are departments and agencies, as the federal government's are; there is no ministry.
INSTITUTION_TYPES: list[dict[str, Any]] = [
    uses("federal_government"),
    uses("provincial_government"),
    uses("regional_government"),
    uses("municipal_government"),
    uses("department"),
    uses("agency"),
    uses("crown_corporation"),
    uses("public_authority"),
    uses("hospital"),
    uses("university"),
    uses("college"),
    uses("school_board"),
    uses("education_service_agency"),
    uses("transit_agency"),
    uses("police_service"),
    uses("fire_service"),
    uses("public_utility"),
    uses("library"),
    uses("park_district"),
    uses("conservation_authority"),
    uses("airport_authority"),
    uses("port_authority"),
    uses("housing_authority"),
    uses("municipal_corporation"),
    uses("other"),
]

# Domains the agent may fetch (subdomains included) but never trusts: a page on one becomes a
# source only when a trusted page links to it (lists-research section 1.7).
PLATFORMS: list[str] = [
    # Procurement portals.
    "bidnetdirect.com",
    "bonfirehub.com",
    "gobonfire.com",
    "demandstar.com",
    "planetbids.com",
    "bidsync.com",
    "periscopeholdings.com",
    "procurement.opengov.com",
    "ionwave.net",
    "publicpurchase.com",
    "sam.gov",
    "bidexpress.com",
    "vendorregistry.com",
    "jaggaer.com",
    "ariba.com",
    "eunasolutions.com",
    # Agendas and minutes.
    "legistar.com",
    "legistar1.com",
    "granicus.com",
    "iqm2.com",
    "civicplus.com",
    "civicclerk.com",
    "civicweb.net",
    "municode.com",
    "boarddocs.com",
    "diligent.com",
    "novusagenda.com",
    "primegov.com",
    "onbaseonline.com",
    "destinyhosting.com",
    "escribemeetings.com",
    # Meeting video.
    "swagit.com",
    "boxcast.com",
    "boxcast.tv",
    "youtube.com",
    "vimeo.com",
    "facebook.com",
]

# Each state with its government's name and main domains. The names are the census's, so the
# places list finds its state; the government is "State of X" except for the four
# commonwealths, the District and Puerto Rico (lists-research section 1.1).
STATES: list[tuple[str, str, list[str]]] = [
    ("Alabama", "State of Alabama", ["alabama.gov", "al.gov"]),
    ("Alaska", "State of Alaska", ["alaska.gov", "ak.gov"]),
    ("Arizona", "State of Arizona", ["az.gov", "arizona.gov"]),
    ("Arkansas", "State of Arkansas", ["arkansas.gov", "ar.gov"]),
    ("California", "State of California", ["ca.gov"]),
    ("Colorado", "State of Colorado", ["colorado.gov", "co.gov"]),
    ("Connecticut", "State of Connecticut", ["ct.gov"]),
    ("Delaware", "State of Delaware", ["delaware.gov", "de.gov"]),
    (
        "District of Columbia",
        "Government of the District of Columbia",
        ["dc.gov"],
    ),
    ("Florida", "State of Florida", ["fl.gov", "myflorida.gov"]),
    ("Georgia", "State of Georgia", ["georgia.gov", "ga.gov"]),
    ("Hawaii", "State of Hawaii", ["hawaii.gov", "hi.gov", "ehawaii.gov"]),
    ("Idaho", "State of Idaho", ["idaho.gov", "id.gov"]),
    ("Illinois", "State of Illinois", ["illinois.gov", "il.gov"]),
    ("Indiana", "State of Indiana", ["in.gov", "indiana.gov"]),
    ("Iowa", "State of Iowa", ["iowa.gov", "ia.gov"]),
    ("Kansas", "State of Kansas", ["kansas.gov", "ks.gov"]),
    ("Kentucky", "Commonwealth of Kentucky", ["ky.gov", "kentucky.gov"]),
    ("Louisiana", "State of Louisiana", ["louisiana.gov", "la.gov"]),
    ("Maine", "State of Maine", ["maine.gov", "me.gov"]),
    ("Maryland", "State of Maryland", ["maryland.gov", "md.gov"]),
    ("Massachusetts", "Commonwealth of Massachusetts", ["mass.gov", "ma.gov"]),
    ("Michigan", "State of Michigan", ["michigan.gov", "mi.gov"]),
    ("Minnesota", "State of Minnesota", ["mn.gov", "minnesota.gov"]),
    ("Mississippi", "State of Mississippi", ["ms.gov", "mississippi.gov"]),
    ("Missouri", "State of Missouri", ["mo.gov", "missouri.gov"]),
    ("Montana", "State of Montana", ["mt.gov", "montana.gov"]),
    ("Nebraska", "State of Nebraska", ["nebraska.gov", "ne.gov"]),
    ("Nevada", "State of Nevada", ["nv.gov", "nevada.gov"]),
    ("New Hampshire", "State of New Hampshire", ["nh.gov"]),
    ("New Jersey", "State of New Jersey", ["nj.gov", "newjersey.gov"]),
    ("New Mexico", "State of New Mexico", ["nm.gov", "newmexico.gov"]),
    ("New York", "State of New York", ["ny.gov"]),
    ("North Carolina", "State of North Carolina", ["nc.gov"]),
    ("North Dakota", "State of North Dakota", ["nd.gov"]),
    ("Ohio", "State of Ohio", ["ohio.gov", "oh.gov"]),
    ("Oklahoma", "State of Oklahoma", ["oklahoma.gov", "ok.gov"]),
    ("Oregon", "State of Oregon", ["oregon.gov", "or.gov"]),
    ("Pennsylvania", "Commonwealth of Pennsylvania", ["pa.gov"]),
    ("Puerto Rico", "Commonwealth of Puerto Rico", ["pr.gov"]),
    ("Rhode Island", "State of Rhode Island", ["ri.gov"]),
    ("South Carolina", "State of South Carolina", ["sc.gov"]),
    ("South Dakota", "State of South Dakota", ["sd.gov"]),
    ("Tennessee", "State of Tennessee", ["tn.gov"]),
    ("Texas", "State of Texas", ["texas.gov", "tx.gov"]),
    ("Utah", "State of Utah", ["utah.gov", "ut.gov"]),
    ("Vermont", "State of Vermont", ["vermont.gov", "vt.gov"]),
    ("Virginia", "Commonwealth of Virginia", ["virginia.gov"]),
    ("Washington", "State of Washington", ["wa.gov"]),
    ("West Virginia", "State of West Virginia", ["wv.gov"]),
    ("Wisconsin", "State of Wisconsin", ["wisconsin.gov", "wi.gov"]),
    ("Wyoming", "State of Wyoming", ["wyo.gov", "wyoming.gov", "wy.gov"]),
]

# The anchors: places whose government and domains were verified by hand. usa.gov is the
# federal government's portal; the federal departments and agencies come with their own domains
# from the Federal Register list (lists-todo session 6).
PLACES: list[dict[str, Any]] = [
    {
        "name": "United States",
        "level": "country",
        "government": "Government of the United States",
        "domains": ["usa.gov"],
    },
    *(
        {
            "name": name,
            "level": "state",
            "parent": "United States",
            "government": government,
            "domains": domains,
        }
        for name, government, domains in STATES
    ),
]

SEED: dict[str, Any] = {
    "settings": SETTINGS,
    "administrative_levels": ADMINISTRATIVE_LEVELS,
    "institution_types": INSTITUTION_TYPES,
    "platforms": PLATFORMS,
    "places": PLACES,
}
