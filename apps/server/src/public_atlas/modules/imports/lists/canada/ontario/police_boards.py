"""Ontario's municipal police service boards from the Public Appointments Secretariat (PAS):
the 43 boards under the Community Safety and Policing Act, 2019, each a `police_service`
institution at the municipality or region whose police service it governs, with the places it
polices as `served_places`. The boards are the buyers: a board employs the service's members
and contracts for its vehicles, equipment and systems, on its own account or through its
municipality's purchasing department.

PAS lists every provincial agency and board with an appointment; its agency pages are stable
(one fetch hashes like the next) and are fetched sources. A board's page carries the board's
name as PAS writes it ("Police Service Board - Barrie (City of)"), the ministry, an address,
and the Act, section and duties the board is constituted under, and no website: the agent
finds the homepage. The rules:

- A board is one of the "Police Service Board - ..." links of the agencies list. The hand table
  below names each (the legal form, "Barrie Police Service Board"; the regional boards keep
  "Regional" where the board itself does, and Peel's does not), places it and names the
  places it serves. The page's Background must cite the Community Safety and Policing Act,
  2019: a page still citing the Police Services Act, 1990 is a legacy entry.
- Two of PAS's 45 links are legacy entries and are left out: Blandford-Blenheim's, whose
  township is policed by the OPP under the Oxford O.P.P. Detachment Board 2, and North
  Huron's, whose council disbanded the board at the end of 2022 (Wingham moved to the OPP in
  2019). Neither buys anything. The 88 "O.P.P. Detachment Board" links are not boards of a
  police service: a detachment board sets local priorities and takes part in choosing the
  detachment commander, employs no officers and owns no equipment, and its own spending is
  member pay levied on the member municipalities. The Ontario Provincial Police is the buyer,
  and belongs in the provincial agencies list.
- The board sits at the municipality it is named for, at the region for a regional police
  service, and for South Simcoe (two towns, one service) at Innisfil, where its office is,
  serving both towns. Every place is given with its parent, since other provinces' lists load
  a Cornwall, a Kingston, a Windsor, a Stratford, a Hanover and a Woodstock too. The board's
  parent is the place's government (the loader's default).
- A list page with other "Police Service Board" links than the table knows is an error: a new
  board, or one gone, is a change to review by hand.
"""

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from public_atlas.modules.imports.entries import Citation, InstitutionEntry, ServedPlace
from public_atlas.modules.imports.files import Format, ListFile, ListFileError, OpenedFile
from public_atlas.modules.imports.lists.canada.ontario.communities import (
    PROVINCE,
    REGION,
    Location,
    location_of,
)

if TYPE_CHECKING:
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = "CA"
POLICE_SERVICE = "police_service"
PAS = "https://www.pas.gov.on.ca"
ACT = "Community Safety and Policing Act, 2019"

LIST = ListFile(
    name="pas_agencies_list",
    title="Public Appointments Secretariat, Agencies and current appointees",
    url=f"{PAS}/Home/Agencies-list",
    format=Format.HTML,
    sha256="9e55b3d961557c491331410be493eba46d19ed2ddb15f89863ca333283f55051",
)
# The list's links to the police service boards: PAS's agency number and its name for the board.
_LINK = re.compile(r'href="/Home/Agency/(?P<id>\d+)"[^>]*>(?P<title>Police Service Board - [^<]*)<')
PREFIX = "Police Service Board - "


def region(place: str) -> Location:
    return Location(place, REGION, PROVINCE)


def municipality(place: str, parent: str) -> Location:
    """A municipality with its parent as `canada/ontario/places` names it (the province for a
    single-tier one): another province's Cornwall, Kingston, Windsor, Stratford, Hanover or
    Woodstock goes by the same name, and the parent tells the loader which."""
    where = location_of(place)
    return Location(where.place, where.level, parent)


@dataclass(frozen=True)
class Board:
    """A board the table knows: PAS's agency number, its page's hash, the board's name, where
    it sits and, when more than its own place, the places it polices."""

    pas_id: str
    sha256: str
    name: str
    place: Location
    served: tuple[Location, ...] = ()

    @property
    def served_places(self) -> tuple[Location, ...]:
        return self.served or (self.place,)

    @property
    def page(self) -> ListFile:
        return ListFile(
            name=f"pas_agency_{self.pas_id}",
            title=f"Public Appointments Secretariat, agency page of the {self.name}",
            url=f"{PAS}/Home/Agency/{self.pas_id}",
            format=Format.HTML,
            sha256=self.sha256,
            filename_override=f"pas_agency_{self.pas_id}.html",
        )


BOARDS: tuple[Board, ...] = (
    Board(
        "45",
        "8a4d7fe70bf8b1d50e1be9b71cf8b27561fcc8fc27c7d92dfd30bba08634cfef",
        "Aylmer Police Service Board",
        municipality("Aylmer", "Elgin"),
    ),
    Board(
        "46",
        "ee3ea36f79d3fed2906652a656a9255e6ef1d339799ad99c6247ed5f0b366ca9",
        "Barrie Police Service Board",
        municipality("Barrie", "Ontario"),
    ),
    Board(
        "48",
        "d5cc38ebd2776c15e67e8564eebae4e6b260928a90b6a5b6ba724fbc1c1428a7",
        "Belleville Police Service Board",
        municipality("Belleville", "Ontario"),
    ),
    Board(
        "53",
        "71a93e96028f0ceb1997a35b1186bfe25f582c43714a7aa3b92f9ad18363f3b2",
        "South Simcoe Police Service Board",
        municipality("Innisfil", "Simcoe"),
        (municipality("Bradford West Gwillimbury", "Simcoe"), municipality("Innisfil", "Simcoe")),
    ),
    Board(
        "55",
        "0dccf36b8fbe48b74253ce484837f7af2597e609a89d7a8e64f6ecce5a1d0ff7",
        "Brantford Police Service Board",
        municipality("Brantford", "Ontario"),
    ),
    Board(
        "58",
        "867d22feaf72baa2223197c76a19cbba5e1876ead635172ee6a6a74e6ceaa343",
        "Brockville Police Service Board",
        municipality("Brockville", "Ontario"),
    ),
    Board(
        "62",
        "f47b0b7b65dd081ce8d52e8ceb7d286134cdc2847c551ab71941a7d99ff89d06",
        "Chatham-Kent Police Service Board",
        municipality("Chatham-Kent", "Ontario"),
    ),
    Board(
        "64",
        "146aa8ede858ca23d8800435d664b556e474d6fd45cc923fd781d15d2a33059a",
        "Cobourg Police Service Board",
        municipality("Cobourg", "Northumberland"),
    ),
    Board(
        "67",
        "deed61e1337080faa0183715959550853effa5036411627362379a0e7d3a9890",
        "Cornwall Police Service Board",
        municipality("Cornwall", "Ontario"),
    ),
    Board(
        "69",
        "d61b937f28f35423830b36c5b3895f60cda4c1989cc8fa27642a6fa8794342ff",
        "Deep River Police Service Board",
        municipality("Deep River", "Renfrew"),
    ),
    Board(
        "72",
        "6eb54be57dae6acf8ee01e46ab3d2b0af5c8ba9be754d60cbaefa6661f5de900",
        "Durham Regional Police Service Board",
        region("Durham"),
    ),
    Board(
        "80",
        "7bf696c1b29fccb1ebfb7c98e515e2fbf8f679987ac5c707fd0637adb537a2fb",
        "Gananoque Police Service Board",
        municipality("Gananoque", "Ontario"),
    ),
    Board(
        "85",
        "64c1ed7f854fc26281f277e293bf7e29da61e29c82cd8ac066c01bcbfb8b0906",
        "Greater Sudbury Police Service Board",
        municipality("Greater Sudbury", "Ontario"),
    ),
    Board(
        "87",
        "68d539309e25cb37b495e159dd0c811d88d0e8ac92bb44d80afb2e22f2869734",
        "Guelph Police Service Board",
        municipality("Guelph", "Ontario"),
    ),
    Board(
        "89",
        "f6fa7f741aee27e8ab414d06280912da3f7b0f64343f18435b57f9b3c2d745cc",
        "Halton Regional Police Service Board",
        region("Halton"),
    ),
    Board(
        "90",
        "198d8be35f7d20639de6705a1bdc4e8de37e1b6c54d50752d5e8ae56295783ff",
        "Hamilton Police Service Board",
        municipality("Hamilton", "Ontario"),
    ),
    Board(
        "92",
        "3823b19659888987641948b911bcdb9422bc89a959a6b828f51c9116a21a789c",
        "Hanover Police Service Board",
        municipality("Hanover", "Grey"),
    ),
    Board(
        "100",
        "3dd9b857a6026a250ffd69982a5402ee692a4665315acf5a1e1d1f764c306197",
        "Kawartha Lakes Police Service Board",
        municipality("Kawartha Lakes", "Ontario"),
    ),
    Board(
        "103",
        "ce58d62b04db7a1b12481923892dcc513eb643ae819c44913d4fa796c2bfe150",
        "Kingston Police Service Board",
        municipality("Kingston", "Ontario"),
    ),
    Board(
        "110",
        "fbf628f1f30852ffb0c31529b3a91cb9abaf45fcf68ce33141e29919ae94cc4b",
        "LaSalle Police Service Board",
        municipality("LaSalle", "Essex"),
    ),
    Board(
        "112",
        "2f02aebf733b9899084bd1bea5668c5c6f9f99137b6a3fb96abf6a6ec158f99d",
        "London Police Service Board",
        municipality("London", "Ontario"),
    ),
    Board(
        "123",
        "ab25112f4378c3e5a016fe2fd6b4c8bd7c2b61e651024636ab1a74100bd96edd",
        "Niagara Regional Police Service Board",
        region("Niagara"),
    ),
    Board(
        "125",
        "aeb168c3f893d68e2a776f900da297d17769a64b3540e6bd9b92bfff40635b94",
        "North Bay Police Service Board",
        municipality("North Bay", "Nipissing"),
    ),
    Board(
        "135",
        "0d46650c94d9e9da660d7347cc2ad1f496c7fc9877f0822b968464a6ec9316c7",
        "Ottawa Police Service Board",
        municipality("Ottawa", "Ontario"),
    ),
    Board(
        "136",
        "dec730697106ccf98a8ca93c1158ecd8211db7d44f26815b74f4e240f5fe9df2",
        "Owen Sound Police Service Board",
        municipality("Owen Sound", "Grey"),
    ),
    Board(
        "137",
        "c061b4efd9774c7ecb282953d3cd0d5f5bc4bfeb573a54cfe5a908898812e138",
        "Peel Police Service Board",
        region("Peel"),
    ),
    Board(
        "142",
        "4887fdd0790082461fbe07aee5c01ed9653bd3c3024759ec40c82b69d5fadb26",
        "Peterborough Police Service Board",
        municipality("Peterborough", "Ontario"),
    ),
    Board(
        "144",
        "d9dce4727da9928c098bb22c12aa06138f2c180e0174d9f044453e92163276a7",
        "Port Hope Police Service Board",
        municipality("Port Hope", "Northumberland"),
    ),
    Board(
        "151",
        "e366bad1dc25ca455f8feef454f0a7ad65042a0947ace9f118fcbdee262ef13c",
        "Sarnia Police Service Board",
        municipality("Sarnia", "Lambton"),
    ),
    Board(
        "152",
        "6977b0f0d361d886a793d9980d09e967bb2c8d7c125fd2c36d4d00efe1100f9f",
        "Saugeen Shores Police Service Board",
        municipality("Saugeen Shores", "Bruce"),
    ),
    Board(
        "153",
        "f0d0f01026be10f5f403dcb65e04d825207386882c00415971761713330db56d",
        "Sault Ste. Marie Police Service Board",
        municipality("Sault Ste. Marie", "Algoma"),
    ),
    Board(
        "159",
        "0d5d9526da2ed8c8896b2646cbbb251c242778ca0099ca7b50a2a6f4fa41e97d",
        "Smiths Falls Police Service Board",
        municipality("Smiths Falls", "Ontario"),
    ),
    Board(
        "167",
        "944d1cc7e4d4684585288b46c1f64832bebad967e8d1f71aada930b3093ab9b3",
        "St. Thomas Police Service Board",
        municipality("St. Thomas", "Ontario"),
    ),
    Board(
        "171",
        "06bacd7a97ec1f4cd743d596d0330cf978d94d0ce76930a446e35e1b5db85cd6",
        "Stratford Police Service Board",
        municipality("Stratford", "Ontario"),
    ),
    Board(
        "172",
        "dd042c6fb8f0117d938f8230d8b5b5da046fd85d975116bd0d9f5b8608cc67bd",
        "Strathroy-Caradoc Police Service Board",
        municipality("Strathroy-Caradoc", "Middlesex"),
    ),
    Board(
        "183",
        "60e887ab49f75a709abaf900f804b0ef89cbcacda27d5a7f6a7e9117028e0c01",
        "Thunder Bay Police Service Board",
        municipality("Thunder Bay", "Thunder Bay"),
    ),
    Board(
        "185",
        "ab7fbe5befa963da127f2386eca7c817c57d57978f523827b23016761ce499e4",
        "Timmins Police Service Board",
        municipality("Timmins", "Cochrane"),
    ),
    Board(
        "186",
        "76c1ec195175b829e90c042895c303fadac42dbcd5ebf1b70d7a1369bb03dfef",
        "Toronto Police Service Board",
        municipality("Toronto", "Ontario"),
    ),
    Board(
        "190",
        "55bda596d9ce8826451963d116582ba0d1078b9b85921d84d72585daa1768d79",
        "Waterloo Regional Police Service Board",
        region("Waterloo"),
    ),
    Board(
        "193",
        "cee9511c9409db5a2bbf6122d78c3d359fc4e3e15e682b9d3c0b18fe38a86dcb",
        "West Grey Police Service Board",
        municipality("West Grey", "Grey"),
    ),
    Board(
        "196",
        "61367373120117d64533856de40034b2ae2b4a8d219075072c4af310c62cdcf4",
        "Windsor Police Service Board",
        municipality("Windsor", "Ontario"),
    ),
    Board(
        "197",
        "11907e5f3a82a205f68b155c986e36e42505477a0d55d5eb3e84573bb9e9b45d",
        "Woodstock Police Service Board",
        municipality("Woodstock", "Oxford"),
    ),
    Board(
        "198",
        "b3c770f1645629d7ee1607842ae9b48487a74d6b6e85dbf42f5a0c5e7eb6e0fc",
        "York Regional Police Service Board",
        region("York"),
    ),
)
# PAS's "Police Service Board" links that are no board of a police service, by agency number,
# each with its reason.
LEGACY: dict[str, str] = {
    "49": "Blandford-Blenheim (Township of): policed by the OPP, under the Oxford O.P.P. "
    "Detachment Board 2; the page still cites the Police Services Act, 1990",
    "127": "North Huron (Township of): the board was disbanded on 2022-12-31, Wingham having "
    "moved to the OPP in 2019; the page still cites the Police Services Act, 1990",
}
BY_ID: dict[str, Board] = {board.pas_id: board for board in BOARDS}
SOURCES = (LIST, *(board.page for board in BOARDS))
# No hand corrections beyond the table: the table is the list.
OVERRIDES: dict[str, dict[str, str]] = {}


def board_links(opened: OpenedFile) -> dict[str, str]:
    """PAS's police service board links: the agency number and PAS's name for the board."""
    html = opened.data.decode("utf-8", errors="replace")
    return {match.group("id"): match.group("title").strip() for match in _LINK.finditer(html)}


@dataclass(frozen=True)
class Page:
    """What a board's page says: PAS's name for the board (its heading), the line it is on,
    and the Act the Background cites."""

    title: str
    line: int
    background: str


def read_page(opened: OpenedFile) -> Page:
    title = next(
        ((n, line) for n, line in enumerate(opened.lines, 1) if line.startswith(PREFIX)), None
    )
    if title is None:
        raise ListFileError(f"{opened.file.name}: no '{PREFIX}' heading")
    try:
        background = opened.lines[opened.lines.index("Background") + 1]
    except ValueError, IndexError:
        raise ListFileError(f"{opened.file.name}: no Background") from None
    return Page(title=title[1], line=title[0], background=background)


def build(files: Mapping[str, OpenedFile]) -> list[InstitutionEntry]:
    links = board_links(files[LIST.name])
    known = set(BY_ID) | set(LEGACY)
    if set(links) != known:
        raise ListFileError(
            f"{LIST.name}: the police service board links are not the table's: "
            f"new {sorted(set(links) - known)}, gone {sorted(known - set(links))}"
        )
    found = []
    for board in BOARDS:
        page = read_page(files[board.page.name])
        if page.title != links[board.pas_id]:
            raise ListFileError(
                f"{board.page.name}: the page is headed {page.title!r}, the list says "
                f"{links[board.pas_id]!r}"
            )
        if not page.background.startswith(ACT):
            raise ListFileError(
                f"{board.page.name}: the Background cites {page.background[:60]!r}, not the "
                f"{ACT}: a legacy entry"
            )
        found.append(
            InstitutionEntry(
                name=board.name,
                institution_type=POLICE_SERVICE,
                place=board.place.place,
                place_level=board.place.level,
                place_parent=board.place.parent,
                served_places=tuple(
                    ServedPlace(name=where.place, level=where.level, parent=where.parent)
                    for where in board.served_places
                ),
                citations={"institution": Citation(source=board.page.name, line=page.line)},
            )
        )
    for pas_id, reason in LEGACY.items():
        logger.info("left out: %s (%s): %s", links[pas_id], pas_id, reason)
    return found


def entries(files: Mapping[str, OpenedFile], rules: CountryRules) -> list[InstitutionEntry]:
    """Ontario's 43 municipal police service boards, at the places they police."""
    del rules
    return build(files)
