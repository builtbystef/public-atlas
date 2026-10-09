"""Where a body is when a list gives its city as the post office writes it: a hospital in
"Almonte" is in Mississippi Mills, a school board in "Nepean" is in Ottawa, a college in
"Sudbury" is in Greater Sudbury, and "Thunder Bay" means the city, not the district. A shared
reader for the Ontario lists that attach bodies by city (`fippa_bodies`, `school_boards`,
`libraries`, `health_units`, `conservation_authorities`); it defines no `entries` and so is no
list. The names are those of the places `canada/ontario/places` loads; a city that is a
municipality and shares its name with nothing needs no row.

Moose Factory is on an island that is a reserve and unorganized land, so its bodies belong to
the territorial district of Cochrane, the region of that name with no government."""

from dataclasses import dataclass

from public_atlas.shared.text import name_key

MUNICIPALITY = "municipality"
REGION = "region"
PROVINCE = "Ontario"


@dataclass(frozen=True, slots=True)
class Location:
    """A place as an `InstitutionEntry` names it: the name, the level, and the parent that
    tells it from a namesake."""

    place: str
    level: str = MUNICIPALITY
    parent: str | None = None


COMMUNITIES: dict[str, str] = {
    # The cities' former municipalities and neighbourhoods.
    "Scarborough": "Toronto",
    "North York": "Toronto",
    "Etobicoke": "Toronto",
    "East York": "Toronto",
    "Nepean": "Ottawa",
    "Kanata": "Ottawa",
    "Gloucester": "Ottawa",
    "Orleans": "Ottawa",
    "Orléans": "Ottawa",
    "Vanier": "Ottawa",
    "Stoney Creek": "Hamilton",
    "Ancaster": "Hamilton",
    "Dundas": "Hamilton",
    "Flamborough": "Hamilton",
    "Sudbury": "Greater Sudbury",
    "Chatham": "Chatham-Kent",
    "Wallaceburg": "Chatham-Kent",
    "Lindsay": "Kawartha Lakes",
    "Simcoe": "Norfolk County",
    "Dunnville": "Haldimand County",
    "Hagersville": "Haldimand County",
    "Caledonia": "Haldimand County",
    # Towns and villages inside an amalgamated municipality.
    "Almonte": "Mississippi Mills",
    "Alexandria": "North Glengarry",
    "Alliston": "New Tecumseth",
    "Barry's Bay": "Madawaska Valley",
    "Campbellford": "Trent Hills",
    "Chesley": "Arran-Elderslie",
    "Clinton": "Central Huron",
    "Dublin": "West Perth",
    "Exeter": "South Huron",
    "Fergus": "Centre Wellington",
    "Geraldton": "Greenstone",
    "Haliburton": "Dysart et al",
    "Kemptville": "North Grenville",
    "L'Orignal": "Champlain",
    "Listowel": "North Perth",
    "Little Current": "Northeastern Manitoulin and the Islands",
    "Matheson": "Black River-Matheson",
    "Midhurst": "Springwater",
    "Mount Forest": "Wellington North",
    "Napanee": "Greater Napanee",
    "New Liskeard": "Temiskaming Shores",
    "Seaforth": "Huron East",
    "Strathroy": "Strathroy-Caradoc",
    "Sturgeon Falls": "West Nipissing",
    "Walkerton": "Brockton",
    "Winchester": "North Dundas",
    "Wingham": "North Huron",
    "Downsview": "Toronto",
    "Manotick": "Ottawa",
    "Glenburnie": "Kingston",
    "Utopia": "Essa",
    "Finch": "North Stormont",
    "Wroxeter": "Howick",
    "Lanark": "Lanark Highlands",
    "Trenton": "Quinte West",
    "Marmora": "Marmora and Lake",
}

# Communities on unorganized land: the territorial district they are in.
UNORGANIZED: dict[str, str] = {
    "Moose Factory": "Cochrane",
}

# Municipalities that share their name with another place: the parent that tells the one the
# lists mean. The City of Hamilton is a single tier under the province; the township of that
# name is in Northumberland.
NAMESAKES: dict[str, str] = {
    "Hamilton": PROVINCE,
}

_BY_KEY = {name_key(community): municipality for community, municipality in COMMUNITIES.items()}
_UNORGANIZED_BY_KEY = {name_key(community): district for community, district in UNORGANIZED.items()}
_NAMESAKES_BY_KEY = {name_key(municipality): parent for municipality, parent in NAMESAKES.items()}


def location_of(city: str) -> Location:
    """Where a body whose city is `city` is: the municipality it is in, or the district when
    it is on unorganized land. Case, punctuation and a trailing comma ("Hamilton,") do not
    matter."""
    city = " ".join(city.replace(",", " ").split())
    key = name_key(city)
    if key in _UNORGANIZED_BY_KEY:
        return Location(_UNORGANIZED_BY_KEY[key], REGION, PROVINCE)
    municipality = _BY_KEY.get(key, city)
    return Location(municipality, MUNICIPALITY, _NAMESAKES_BY_KEY.get(name_key(municipality)))
