"""Quebec's places from Statistics Canada's 2021 Census and the Ministère des Affaires
municipales et de l'Habitation's *Répertoire des municipalités*: 81 regions (the municipalités
régionales de comté the census counts as divisions) and about 1,120 municipalities, each with
its code, its 2021 population, the population the 2026 décret de population gives it, its
government's legal name and, where the directory links one, the government's homepage as a
candidate; and, as `regional_government` institutions under Quebec with the places they serve,
the two communautés métropolitaines, the Administration régionale Kativik and the six MRCs the
census carries no division for.

The census population table gives every unit's code, names and population; the census
geographic attribute file says what each unit is; the two census files and their readers are
shared with every province (`canada/statcan.py`). The directory is two files: `MUN.csv`, one
row per municipality, reserve and unorganized territory with its five-digit code (`mcode`, the
last five digits of the census code, so the join is exact), its name, designation, MRC,
website and décret population; and `MRC_CM_Arg.csv`, one row per MRC, communauté
métropolitaine and the Kativik administration, with its three-digit code, website and
population. The rules:

- A municipalité régionale de comté is a region with a government, and a municipality's parent
  is the MRC the directory's `mrc` column names, never its census division: twelve `TÉ`
  divisions are cities with no MRC above them (Québec, Montréal, Laval, Longueuil, Gatineau and
  the rest), and five `CDR` divisions are census units holding the municipalities of MRCs the
  census does not count as divisions (Francheville holds Trois-Rivières and the MRC Des
  Chenaux; Nord-du-Québec the north). A municipality with no MRC sits under Quebec.
- An MRC's code is its census division's: the directory's three-digit code is the division's
  last two digits and a trailing digit (`460` is division 2446). The six MRCs whose code is no
  division (Des Chenaux, Le Fjord-du-Saguenay, Sept-Rivières, Caniapiscau, Minganie, Le
  Golfe-du-Saint-Laurent) have no code in any scheme the graph has, and a place needs one; they
  are loaded as `regional_government` institutions under Quebec with their municipalities as
  served places, as the communautés métropolitaines are, and their municipalities sit under
  Quebec. A `mamh` identifier scheme would make them regions.
- The municipal subdivision types are municipalities, the Eeyou Istchee Baie-James regional
  government among them (a subdivision with a code of its own). Indian reserves, Cree, Inuit
  and Naskapi lands, Indian settlements and unorganized territories are not governments and are
  left out.
- A municipality is named as the directory names it, with the census's name as an alias where
  the two differ (a rename since the census: Mont-Blanc for Saint-Faustin--Lac-Carré). Its
  government's name is composed from the directory's designation (`mdes`: Ville, Municipalité,
  Paroisse, Canton, Cantons unis, Village, Village nordique, Village cri, Village naskapi,
  Gouvernement régional) and the name with the French connector: "de" ("Ville de Québec"),
  elided before a vowel ("Municipalité d'Adstock") and before the French-origin names in H the
  hand table lists ("Municipalité d'Hébertville", but "Ville de Hampstead"), contracted with
  an article ("Municipalité des Îles-de-la-Madeleine" for Les Îles-de-la-Madeleine, "du" for
  Le, "des" for Des) and kept before "La", "L'" and "D'" ("Ville de La Tuque", "Ville de
  L'Épiphanie", "MRC de D'Autray"). An MRC's is "Municipalité régionale de comté de ..." the
  same way, with "MRC de ..." as an alias.
- A census municipality the directory no longer lists has merged or been recoded since the
  census; `OVERRIDES` names what it became, and an unexplained one is an error. A directory
  municipality the census has no row for was created since the census (a merger's new
  municipality, the Cree village of Oujé-Bougoumou) and is loaded from the directory alone,
  with the décret population and no census figure.
- The communautés métropolitaines serve the municipalities whose `mcm` column names them, the
  Kativik administration the northern villages whose `admregionale` names it. Each is an
  institution at Quebec with the directory's website.
- The décret population is the figure the Décret de population pour 2026 gives (decree
  1499-2025, published 2025-12-24, resting on the Institut de la statistique du Québec's
  estimate at 2025-07-01), stored for the year 2026 beside the census's 2021 count.

The directory updates daily, so its two files' hashes break every day: the operator re-pins
the hashes at load time (download the two files, record their sha256 here with the date, read
the diff). The census files are the 2021 release and hold still.
"""

import logging
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from public_atlas.modules.graph.models import IdentifierScheme, MetricName
from public_atlas.modules.graph.service import normalize_url
from public_atlas.modules.imports.entries import (
    AliasEntry,
    Citation,
    Code,
    Fact,
    Figure,
    InstitutionEntry,
    PlaceEntry,
    ServedPlace,
)
from public_atlas.modules.imports.files import Format, ListFile, ListFileError, OpenedFile
from public_atlas.modules.imports.lists.canada import statcan
from public_atlas.modules.imports.lists.canada.statcan import (
    ATTRIBUTES,
    CENSUS_YEAR,
    POPULATION,
    Counted,
)

if TYPE_CHECKING:
    from public_atlas.modules.countries.service import CountryRules

logger = logging.getLogger(__name__)

COUNTRY = "CA"
PROVINCE = "Quebec"
PROVINCE_LEVEL = "province_territory"
PROVINCE_CODE = "24"
QUEBEC = statcan.Province(PROVINCE_CODE)
REGION = "region"
MUNICIPALITY = "municipality"
REGIONAL_GOVERNMENT = "regional_government"
# The year of the décret de population the directory's figures are from.
DECREE_YEAR = 2026

MUNICIPALITIES = ListFile(
    name="mamh_municipalities",
    title=(
        "Ministère des Affaires municipales et de l'Habitation, Répertoire des municipalités: "
        "the municipalities (MUN.csv), as fetched on 2026-10-09"
    ),
    url="https://donneesouvertes.affmunqc.net/repertoire/MUN.csv",
    sha256="10887c38c40e062dd918570a5e651252a2b44e0ed660bfc35c8a301c54ff5e83",
    format=Format.CSV,
    # The addresses, the elected officials and the staff stay out of the stored text.
    columns=("mcode", "munnom", "mdes", "mrc", "admregionale", "mcm", "mweb", "mpopul", "mdatcons"),
)
MRCS = ListFile(
    name="mamh_mrcs",
    title=(
        "Ministère des Affaires municipales et de l'Habitation, Répertoire des municipalités: "
        "the MRCs, communautés métropolitaines and the Administration régionale Kativik "
        "(MRC_CM_Arg.csv), as fetched on 2026-10-09"
    ),
    url="https://donneesouvertes.affmunqc.net/repertoire/MRC_CM_Arg.csv",
    sha256="b9605a38441453607c93548a51d09fe41ba0ee74df24b4b9aee1e362b7b8e945",
    format=Format.CSV,
    columns=("mrccod", "mrcnom", "mrcdescdesi", "mrcweb", "mrcpopul"),
)
SOURCES = (POPULATION, ATTRIBUTES, MUNICIPALITIES, MRCS)

# What Quebec's census unit types are (SGC 2021, `statcan.py`).
UPPER_TIER_TYPES = QUEBEC.upper_tier_types
CENSUS_ONLY_TYPES = QUEBEC.census_only_types
MUNICIPAL_TYPES = QUEBEC.municipal_types
DROPPED_TYPES = QUEBEC.dropped_types
MRC_TYPE = "MRC"

# The designator a government's name takes, by the directory's designation; a designation
# not here is no municipality (a reserve, a territoire non organisé, Cree or Inuit land).
DESIGNATORS: dict[str, str] = {
    "Ville": "Ville",
    "Municipalité": "Municipalité",
    "Paroisse": "Paroisse",
    "Canton": "Canton",
    "Cantons unis": "Cantons unis",
    "Village": "Village",
    "Village nordique": "Village nordique",
    "Village cri (Terre de la catégorie": "Village cri",
    "Village naskapi (Terre de la catégo": "Village naskapi",
    "Gouvernement régional": "Gouvernement régional",
}
MRC_DESIGNATOR = "Municipalité régionale de comté"
MRC_SHORT = "MRC"
MRC_DESIGNATION = "Municipalité régionale de comté"
# The bodies the MRC file lists that are no MRC, by their code, with their names (the file
# abbreviates one) and the aliases they go by.
SPANNING_BODIES: dict[str, tuple[str, tuple[AliasEntry, ...]]] = {
    "CM663": (
        "Communauté métropolitaine de Montréal",
        (AliasEntry(text="CMM", language="fr", is_acronym=True),),
    ),
    "CM235": (
        "Communauté métropolitaine de Québec",
        (AliasEntry(text="CMQ", language="fr", is_acronym=True),),
    ),
    "AR992": (
        "Administration régionale Kativik",
        (
            AliasEntry(text="Kativik Regional Government", language="en"),
            AliasEntry(text="KRG", language="en", is_acronym=True),
        ),
    ),
}
# Names in H the connector elides before: the French-origin ones. The English-origin names
# (Hampstead, Hudson's neighbour Huntingdon, Hemmingford) keep "de".
ELIDED_H = frozenset(
    {"Hébertville", "Hérouxville", "Henryville", "Honfleur", "Huberdeau", "Hudson"}
)
_VOWEL = re.compile(r"^[AEIOUYÀÂÄÉÈÊËÎÏÔÖÙÛÜ]", re.IGNORECASE)
# The code in parentheses that ends an MRC, administration or communauté cell.
_CODED = re.compile(r"^(?P<name>.*?)\s*\((?P<code>\d+)\)$")

# Hand corrections keyed by census code, each with its reason: `merged_from`, the census codes
# of the municipalities that have merged into, or been recoded as, the one the key names since
# the census, so a census municipality the directory no longer lists is accounted for.
OVERRIDES: dict[str, dict[str, str | tuple[str, ...]]] = {
    "2488057": {
        "merged_from": ("2488055", "2488060"),
        "reason": "Amos merged with Saint-Félix-de-Dalquier in 2025",
    },
    "2488012": {
        "merged_from": ("2488015", "2488010"),
        "reason": "La Morandière and Rochebaucourt merged in 2023",
    },
    "2429027": {
        "merged_from": ("2430090", "2429025"),
        "reason": "Courcelles and Saint-Évariste-de-Forsyth merged in 2024",
    },
    "2414082": {
        "merged_from": ("2414085", "2414080", "2414090"),
        "reason": (
            "La Pocatière merged with Saint-Onésime-d'Ixworth and Sainte-Anne-de-la-Pocatière "
            "in 2025"
        ),
    },
    "2432043": {
        "merged_from": ("2432040", "2432045"),
        "reason": "the ville and the paroisse of Plessisville merged in 2024",
    },
    "2493022": {
        "merged_from": ("2493020", "2493025", "2493030"),
        "reason": "Hébertville merged with Hébertville-Station and Saint-Bruno in 2026",
    },
    "2413062": {
        "merged_from": ("2413060", "2411020"),
        "reason": "Lac-des-Aigles merged with Saint-Guy into a ville in 2024",
    },
    "2480087": {
        "merged_from": ("2482010",),
        "reason": (
            "Notre-Dame-de-la-Salette moved from Les Collines-de-l'Outaouais to Papineau in 2022 "
            "and was recoded"
        ),
    },
}
# The new census code of each municipality merged or recoded since the census.
MERGED_INTO: dict[str, str] = {
    old: new for new, fields in OVERRIDES.items() for old in fields["merged_from"]
}


# --- The files ---


@dataclass(frozen=True)
class MunicipalityRow:
    code: str
    name: str
    designation: str
    # The MRC's three-digit code, or None.
    mrc: str | None
    # The Kativik administration's code, or None.
    administration: str | None
    # The communauté métropolitaine's code, or None.
    community: str | None
    homepage: str | None
    population: int | None
    line: int

    @property
    def is_municipality(self) -> bool:
        return self.designation in DESIGNATORS


@dataclass(frozen=True)
class MrcRow:
    # "AR460", "CM663".
    code: str
    name: str
    designation: str
    homepage: str | None
    population: int | None
    line: int

    @property
    def is_mrc(self) -> bool:
        return self.designation == MRC_DESIGNATION

    @property
    def short_code(self) -> str:
        """The three digits the municipalities' `mrc` column names."""
        return self.code[2:]

    @property
    def division_code(self) -> str:
        """The census division of that code, if the census has one."""
        return f"{PROVINCE_CODE}{self.short_code[:2]}"


def _coded(cell: str) -> str | None:
    match = _CODED.match(cell)
    return match.group("code") if match else None


def _homepage(cell: str) -> str | None:
    cell = cell.strip()
    return normalize_url(cell) if cell else None


def _population(cell: str) -> int | None:
    return int(cell) if cell.isdigit() else None


def read_municipalities(opened: OpenedFile) -> list[MunicipalityRow]:
    return [
        MunicipalityRow(
            code=row["mcode"],
            name=" ".join(row["munnom"].split()),
            designation=row["mdes"],
            mrc=_coded(row["mrc"]),
            administration=_coded(row["admregionale"]),
            community=_coded(row["mcm"]),
            homepage=_homepage(row["mweb"]),
            population=_population(row["mpopul"]),
            line=row.line,
        )
        for row in opened.rows
    ]


def read_mrcs(opened: OpenedFile) -> list[MrcRow]:
    return [
        MrcRow(
            code=row["mrccod"],
            name=" ".join(row["mrcnom"].split()),
            designation=row["mrcdescdesi"],
            homepage=_homepage(row["mrcweb"]),
            population=_population(row["mrcpopul"]),
            line=row.line,
        )
        for row in opened.rows
    ]


# --- Names ---


def with_connector(designator: str, name: str) -> str:
    """The designator joined to the name in French: "Ville de Québec", "Municipalité
    d'Adstock", "Ville de L'Épiphanie", "Municipalité des Îles-de-la-Madeleine", "MRC du
    Granit", "MRC des Chenaux" (Des Chenaux), "MRC de D'Autray"."""
    if name.startswith("Le "):
        return f"{designator} du {name.removeprefix('Le ')}"
    if name.startswith("Les "):
        return f"{designator} des {name.removeprefix('Les ')}"
    if name.startswith("Des "):
        return f"{designator} des {name.removeprefix('Des ')}"
    if _VOWEL.match(name) or name in ELIDED_H:
        return f"{designator} d'{name}"
    return f"{designator} de {name}"


def government_name(designation: str, name: str) -> str:
    return with_connector(DESIGNATORS[designation], name)


# --- Building ---


@dataclass
class Notes:
    """What the build dropped, renamed, created and corrected, logged for the operator and
    pinned by the rule test."""

    dropped: Counter[str] = field(default_factory=Counter)
    # Municipalities the directory names otherwise than the census, as "census -> directory".
    renamed: list[str] = field(default_factory=list)
    # Municipalities the directory has and the census has not, by name.
    created: list[str] = field(default_factory=list)
    # Census municipalities merged or recoded since, by name, with what they became.
    merged: list[str] = field(default_factory=list)
    # MRCs the census has no division for, loaded as institutions.
    mrcs_without_division: list[str] = field(default_factory=list)
    # Directory rows that are no municipality, by designation.
    directory_dropped: Counter[str] = field(default_factory=Counter)

    def log(self) -> None:
        for type_, count in sorted(self.dropped.items()):
            logger.info(
                "left out %d %s subdivisions (%s)", count, DROPPED_TYPES.get(type_, type_), type_
            )
        for line in self.renamed:
            logger.info("renamed since the census: %s", line)
        for line in self.created:
            logger.info("created since the census, loaded from the directory: %s", line)
        for line in self.merged:
            logger.info("override: %s", line)
        for line in self.mrcs_without_division:
            logger.info("no census division for MRC %s: loaded as an institution", line)
        for designation, count in sorted(self.directory_dropped.items()):
            logger.info("left out %d directory rows designated %r", count, designation)


@dataclass
class Builder:
    counted: dict[str, Counted]
    municipalities: list[MunicipalityRow]
    mrcs: list[MrcRow]
    notes: Notes = field(default_factory=Notes)

    def __post_init__(self) -> None:
        self.divisions = {
            code: unit
            for code, unit in self.counted.items()
            if unit.division is None and code != PROVINCE_CODE
        }
        self.subdivisions = sorted(
            (unit for unit in self.counted.values() if unit.division is not None),
            key=lambda unit: unit.code,
        )
        self.rows_by_code = {row.code: row for row in self.municipalities}
        # The MRCs that are regions, by their three-digit code, with the region's name.
        self.region_names: dict[str, str] = {}
        for row in self.mrcs:
            if row.is_mrc and self._division_of(row) is not None:
                self.region_names[row.short_code] = row.name

    def _division_of(self, row: MrcRow) -> Counted | None:
        """The MRC's census division: the one of its code, when it is an MRC division."""
        if not row.short_code.endswith("0"):
            return None
        division = self.divisions.get(row.division_code)
        return division if division is not None and division.type_ == MRC_TYPE else None

    def parent_of(self, row: MunicipalityRow) -> str:
        """The MRC the directory names, when it is a region; else the province."""
        return self.region_names.get(row.mrc or "", PROVINCE)

    def regions(self) -> list[PlaceEntry]:
        found = []
        for row in self.mrcs:
            if not row.is_mrc:
                continue
            division = self._division_of(row)
            if division is None:
                self.notes.mrcs_without_division.append(f"{row.short_code} {row.name}")
                continue
            place = Citation(source=POPULATION.name, line=division.line)
            directory = Citation(source=MRCS.name, line=row.line)
            aliases = [AliasEntry(text=with_connector(MRC_SHORT, row.name), language="fr")]
            if division.names[0] != row.name:
                self.notes.renamed.append(f"{division.code} {division.names[0]} -> {row.name}")
                aliases.append(AliasEntry(text=division.names[0], language="fr"))
            figures: list[Figure] = []
            if division.population is not None:
                figures.append(
                    Figure(
                        name=MetricName.POPULATION,
                        year=CENSUS_YEAR,
                        value=Decimal(division.population),
                        citation=place,
                    )
                )
            if row.population is not None:
                figures.append(
                    Figure(
                        name=MetricName.POPULATION,
                        year=DECREE_YEAR,
                        value=Decimal(row.population),
                        citation=directory,
                    )
                )
            citations: dict[Fact, Citation] = {"place": place, "government": directory}
            if row.homepage is not None:
                citations["homepage"] = directory
            found.append(
                PlaceEntry(
                    name=row.name,
                    aliases=tuple(aliases),
                    language="fr",
                    level=REGION,
                    parent=PROVINCE,
                    parent_level=PROVINCE_LEVEL,
                    government=with_connector(MRC_DESIGNATOR, row.name),
                    code=Code(scheme=IdentifierScheme.STATCAN_SGC, value=division.code),
                    figures=tuple(figures),
                    homepage=row.homepage,
                    citations=citations,
                )
            )
        return sorted(found, key=lambda entry: entry.name)

    def municipality_entries(self) -> list[PlaceEntry]:
        """The census municipalities the directory lists, then the directory's municipalities
        the census has no row for."""
        found = []
        taken: set[str] = set()
        for unit in self.subdivisions:
            if unit.type_ not in MUNICIPAL_TYPES:
                self.notes.dropped[unit.type_] += 1
                continue
            row = self.rows_by_code.get(unit.code[len(PROVINCE_CODE) :])
            if row is None:
                self._merged(unit)
                continue
            if not row.is_municipality:
                raise ListFileError(
                    f"{MUNICIPALITIES.name}: {row.code} {row.name} is a {row.designation!r}, "
                    f"which the census counts as a municipality ({unit.type_})"
                )
            taken.add(row.code)
            found.append(self._municipality(row, unit))
        for row in self.municipalities:
            if not row.is_municipality:
                self.notes.directory_dropped[row.designation] += 1
            elif row.code not in taken:
                self.notes.created.append(f"{row.code} {row.name} ({row.designation})")
                found.append(self._municipality(row, None))
        return sorted(found, key=lambda entry: entry.name)

    def _merged(self, unit: Counted) -> None:
        new = MERGED_INTO.get(unit.code)
        if new is None:
            raise ListFileError(
                f"{MUNICIPALITIES.name}: no row for census municipality {unit.code} "
                f"{unit.names[0]} ({unit.type_}) and no override says what it became"
            )
        into = self.rows_by_code.get(new[len(PROVINCE_CODE) :])
        if into is None or not into.is_municipality:
            raise ListFileError(
                f"{MUNICIPALITIES.name}: override {new} names no municipality in the directory"
            )
        self.notes.merged.append(
            f"{unit.code} {unit.names[0]} -> {new} {into.name}: {OVERRIDES[new]['reason']}"
        )

    def _municipality(self, row: MunicipalityRow, unit: Counted | None) -> PlaceEntry:
        directory = Citation(source=MUNICIPALITIES.name, line=row.line)
        aliases: list[AliasEntry] = []
        figures: list[Figure] = []
        if unit is not None:
            place = Citation(source=POPULATION.name, line=unit.line)
            if unit.names[0] != row.name:
                self.notes.renamed.append(f"{unit.code} {unit.names[0]} -> {row.name}")
                aliases.append(AliasEntry(text=unit.names[0], language="fr"))
            if unit.population is not None:
                figures.append(
                    Figure(
                        name=MetricName.POPULATION,
                        year=CENSUS_YEAR,
                        value=Decimal(unit.population),
                        citation=place,
                    )
                )
        else:
            place = directory
        if row.population is not None:
            figures.append(
                Figure(
                    name=MetricName.POPULATION,
                    year=DECREE_YEAR,
                    value=Decimal(row.population),
                    citation=directory,
                )
            )
        citations: dict[Fact, Citation] = {"place": place, "government": directory}
        if row.homepage is not None:
            citations["homepage"] = directory
        parent = self.parent_of(row)
        return PlaceEntry(
            name=row.name,
            aliases=tuple(aliases),
            language="fr",
            level=MUNICIPALITY,
            parent=parent,
            parent_level=REGION if parent != PROVINCE else PROVINCE_LEVEL,
            parent_parent=PROVINCE if parent != PROVINCE else None,
            government=government_name(row.designation, row.name),
            code=Code(scheme=IdentifierScheme.STATCAN_SGC, value=f"{PROVINCE_CODE}{row.code}"),
            figures=tuple(figures),
            homepage=row.homepage,
            citations=citations,
        )

    def served(self, row: MunicipalityRow) -> ServedPlace:
        parent = self.parent_of(row)
        return ServedPlace(name=row.name, level=MUNICIPALITY, parent=parent)

    def institutions(self) -> list[InstitutionEntry]:
        """The communautés métropolitaines, the Kativik administration and the MRCs with no
        census division, each with the municipalities it serves."""
        found = []
        for row in self.mrcs:
            if row.is_mrc:
                if self._division_of(row) is not None:
                    continue
                name = with_connector(MRC_DESIGNATOR, row.name)
                aliases: tuple[AliasEntry, ...] = (
                    AliasEntry(text=with_connector(MRC_SHORT, row.name), language="fr"),
                )
                members = [
                    m for m in self.municipalities if m.is_municipality and m.mrc == row.short_code
                ]
            elif row.code in SPANNING_BODIES:
                name, aliases = SPANNING_BODIES[row.code]
                if row.code.startswith("CM"):
                    members = [
                        m
                        for m in self.municipalities
                        if m.is_municipality and m.community == row.short_code
                    ]
                else:
                    members = [
                        m
                        for m in self.municipalities
                        if m.is_municipality and m.administration == row.short_code
                    ]
            else:
                raise ListFileError(
                    f"{MRCS.name}: {row.code} {row.name} is a {row.designation!r}, which the "
                    "module does not know"
                )
            if not members:
                raise ListFileError(f"{MRCS.name}: no municipality names {row.code} {row.name}")
            citation = Citation(source=MRCS.name, line=row.line)
            citations: dict[Fact, Citation] = {"institution": citation}
            if row.homepage is not None:
                citations["homepage"] = citation
            found.append(
                InstitutionEntry(
                    name=name,
                    aliases=aliases,
                    language="fr",
                    institution_type=REGIONAL_GOVERNMENT,
                    place=PROVINCE,
                    place_level=PROVINCE_LEVEL,
                    served_places=tuple(
                        self.served(member) for member in sorted(members, key=lambda m: m.name)
                    ),
                    homepage=row.homepage,
                    citations=citations,
                )
            )
        return sorted(found, key=lambda entry: entry.name)


def build(files: Mapping[str, OpenedFile]) -> tuple[list[PlaceEntry | InstitutionEntry], Notes]:
    """The regions, the municipalities and the spanning bodies, with the notes of the build."""
    counted = QUEBEC.read_population(files[POPULATION.name])
    QUEBEC.read_types(counted, files[ATTRIBUTES.name])
    builder = Builder(
        counted=counted,
        municipalities=read_municipalities(files[MUNICIPALITIES.name]),
        mrcs=read_mrcs(files[MRCS.name]),
    )
    regions = builder.regions()
    municipalities = builder.municipality_entries()
    institutions = builder.institutions()
    return [*regions, *municipalities, *institutions], builder.notes


def entries(
    files: Mapping[str, OpenedFile], rules: CountryRules
) -> list[PlaceEntry | InstitutionEntry]:
    """Quebec's regions, then its municipalities, then the bodies that span them."""
    del rules
    found, notes = build(files)
    notes.log()
    return found
