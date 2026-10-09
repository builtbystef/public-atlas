"""The global institution types and source types, and the sources a country expects per type
unless it says otherwise. A country uses a type by listing it in its own seed; a type no country
lists is not used.

The description is what the agent is told the type means, so it must tell two types apart. A
source is a page that carries buying signals: what a body plans to spend on, what it is buying
now, what it bought, and what its council or board debates and announces. How to register as a
supplier is not one; it is one search away.
"""

from typing import Any

SOURCE_TYPES: list[dict[str, Any]] = [
    {
        "name": "procurement",
        "description": "The main purchasing page, with how the institution buys and who to contact",
    },
    {"name": "tender", "description": "Open calls for bids (RFPs, RFQs, tenders), not past awards"},
    {"name": "contract_award", "description": "Contracts already awarded, with supplier and value"},
    {"name": "budget", "description": "Operating budget or estimates for the current or next year"},
    {
        "name": "capital_plan",
        "description": (
            "Multi-year plan or budget for buildings, roads, fleet, IT and other capital projects"
        ),
    },
    {"name": "council_meeting", "description": "Agendas and minutes of the elected council"},
    {
        "name": "board_meeting",
        "description": "Agendas and minutes of the board of directors or trustees",
    },
    {
        "name": "strategic_plan",
        "description": "The current strategic, business or master plan, with stated priorities",
    },
    {"name": "annual_report", "description": "Yearly report on activities, spending and results"},
    {"name": "leadership", "description": "Names and roles of the executives or board members"},
    {
        "name": "meeting_video",
        "description": (
            "Recordings of past council or board meetings: the page that lists them (a YouTube "
            "channel or playlist, the meetings portal that keeps each meeting's video), not a "
            "live-stream player, not a page that only links to the recordings, and not one "
            "recording"
        ),
    },
    {
        "name": "news",
        "description": (
            "The list of news releases and public notices the institution publishes (projects, "
            "funding, appointments), not one release"
        ),
    },
]

# The sources of a government that buys centrally and publishes its own awards.
GOVERNMENT_SOURCES = [
    "procurement",
    "tender",
    "contract_award",
    "budget",
    "strategic_plan",
    "leadership",
    "news",
]
# The sources of a council-led government that plans capital works and records its meetings.
COUNCIL_SOURCES = [
    "procurement",
    "tender",
    "budget",
    "capital_plan",
    "council_meeting",
    "strategic_plan",
    "meeting_video",
    "news",
]
BOARD_SOURCES = ["procurement", "tender", "annual_report", "board_meeting", "leadership"]
CAMPUS_SOURCES = [
    "procurement",
    "tender",
    "capital_plan",
    "board_meeting",
    "strategic_plan",
    "news",
]

INSTITUTION_TYPES: list[dict[str, Any]] = [
    # Governments of each level.
    {"name": "federal_government", "description": "The national government"},
    {
        "name": "provincial_government",
        "description": "The government of a province, territory or state",
    },
    {
        "name": "regional_government",
        "description": "The government of a region, county or district that groups municipalities",
    },
    {
        "name": "municipal_government",
        "description": ("The government of a city, town, township, village or other municipality"),
    },
    # National and provincial bodies.
    {"name": "department", "description": "A department of the national government"},
    {"name": "ministry", "description": "A ministry of a provincial or territorial government"},
    {
        "name": "agency",
        "description": (
            "An agency, board or commission of the national or provincial government; never a "
            "body of a municipality or region"
        ),
    },
    {
        "name": "crown_corporation",
        "description": "A corporation the national or provincial government owns",
    },
    {
        "name": "health_authority",
        "description": "A body that plans or funds health services for a province or an area of it",
    },
    {"name": "hospital", "description": "A public hospital or hospital network"},
    {"name": "university", "description": "A public university"},
    {"name": "college", "description": "A public college"},
    {"name": "school_board", "description": "A public school board or school district"},
    # Bodies of a municipality or region that buy on their own account: their own procurement
    # page, their own budget, or their own board that approves spending. Business improvement
    # areas, council committees and tribunals are not institutions: they spend little and buy
    # through the municipality. A paramedic service has no type either: it is a department of its
    # municipality or region, which buys and budgets for it. Nor is a board of management for
    # one facility, a non-profit the municipality only funds, a holding company above a utility,
    # a subsidiary that buys through its parent, or a board that invests or grants the
    # municipality's money (eval dataset README, "Scope").
    {
        "name": "transit_agency",
        "description": (
            "A public transit operator the municipality or region runs or owns, with the board "
            "that governs it; not a provincial or contracted operator serving the place"
        ),
    },
    {
        "name": "police_service",
        "description": (
            "A municipal or regional police service, with the board that governs it; not a "
            "provincial force policing the place under contract"
        ),
    },
    {"name": "fire_service", "description": "A fire department or fire and rescue service"},
    {
        "name": "public_utility",
        "description": (
            "A publicly owned utility (electricity, water, gas, telecommunications, waste) that "
            "presents under its own name: the operating utility the public deals with, not the "
            "holding company above it, and not a provincial utility that serves the place"
        ),
    },
    {"name": "library", "description": "A public library, with the board that governs it"},
    {
        "name": "conservation_authority",
        "description": (
            "A watershed or conservation authority, usually shared by several municipalities"
        ),
    },
    {
        "name": "public_health_unit",
        "description": "The current public health unit or board of health; not a former one",
    },
    {
        "name": "municipal_corporation",
        "description": (
            "A corporation, authority or board a municipality or region owns or controls that "
            "runs a business of its own and buys on its own account: community housing, real "
            "estate, parking, an airport, a venue, a zoo, economic development. Not a board of "
            "management for one arena, community centre, theatre or street, a non-profit the "
            "municipality only funds, a holding company above a utility, a subsidiary that buys "
            "through its parent, or a board that invests or grants the municipality's money"
        ),
    },
    # A public body with buying power of its own that fits no type is saved as `other`, with the
    # type the agent would have given it in `suggested_type`, and sent to review.
    {
        "name": "other",
        "description": (
            "A public body that buys on its own account and fits no other type; say what it is "
            "in the suggested type"
        ),
    },
]

DEFAULT_EXPECTED_SOURCE_TYPES: dict[str, list[str]] = {
    "federal_government": GOVERNMENT_SOURCES,
    "provincial_government": GOVERNMENT_SOURCES,
    "regional_government": COUNCIL_SOURCES,
    "municipal_government": COUNCIL_SOURCES,
    "department": GOVERNMENT_SOURCES,
    "ministry": GOVERNMENT_SOURCES,
    "agency": BOARD_SOURCES,
    "crown_corporation": BOARD_SOURCES,
    "health_authority": [
        "procurement",
        "tender",
        "budget",
        "board_meeting",
        "strategic_plan",
        "news",
    ],
    "hospital": CAMPUS_SOURCES,
    "university": CAMPUS_SOURCES,
    "college": CAMPUS_SOURCES,
    "school_board": [
        "procurement",
        "tender",
        "budget",
        "capital_plan",
        "board_meeting",
        "meeting_video",
        "news",
    ],
    "transit_agency": [
        "procurement",
        "tender",
        "budget",
        "capital_plan",
        "board_meeting",
        "strategic_plan",
    ],
    "police_service": ["procurement", "tender", "budget", "board_meeting"],
    "fire_service": ["procurement", "budget"],
    "public_utility": ["procurement", "tender", "capital_plan", "board_meeting"],
    "library": ["procurement", "tender", "budget", "board_meeting"],
    "conservation_authority": ["procurement", "tender", "budget", "board_meeting"],
    "public_health_unit": ["procurement", "budget", "board_meeting"],
    "municipal_corporation": ["procurement", "tender", "annual_report", "board_meeting"],
    "other": ["procurement", "tender"],
}

SEED: dict[str, Any] = {
    "institution_types": INSTITUTION_TYPES,
    "source_types": SOURCE_TYPES,
    "default_expected_source_types": DEFAULT_EXPECTED_SOURCE_TYPES,
}


def uses(
    institution_type: str,
    *,
    expected_source_types: list[str] | None = None,
    name_pattern: str | None = None,
) -> dict[str, Any]:
    """A country's row for a type: the default sources unless the country changes them."""
    sources = DEFAULT_EXPECTED_SOURCE_TYPES[institution_type]
    return {
        "institution_type": institution_type,
        "expected_source_types": list(
            sources if expected_source_types is None else expected_source_types
        ),
        "name_pattern": name_pattern,
    }
