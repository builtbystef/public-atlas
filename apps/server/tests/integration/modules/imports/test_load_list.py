"""The shared loader on a tiny list module: a dry run writes nothing, an apply writes the places
with their governments, codes, figures, candidate homepages and evidence quoting the list's own
line, a rerun changes nothing, and a new release changes only what moved. Then the real Ontario
list, when its files are cached."""

import csv
import io
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import ColumnElement, func, select

from public_atlas.config import Settings
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import canada, united_states
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.evidence.models import Evidence, EvidenceKind, Snapshot
from public_atlas.modules.graph.models import (
    Alias,
    Domain,
    DomainKind,
    EnteredBy,
    EntityStatus,
    Homepage,
    Identifier,
    IdentifierScheme,
    Institution,
    InstitutionServedPlace,
    Metric,
    MetricName,
    Place,
    Webpage,
)
from public_atlas.modules.imports import service
from public_atlas.modules.imports.entries import (
    AliasEntry,
    Citation,
    Code,
    Figure,
    InstitutionEntry,
    PlaceEntry,
    ServedPlace,
)
from public_atlas.modules.imports.files import Format, ListFile, OpenedFile, Retrieval
from public_atlas.modules.imports.lists.canada.ontario import places as ontario_places
from public_atlas.modules.imports.models import OfficialList

if TYPE_CHECKING:
    from tests.integration.conftest import Database

    from public_atlas.integrations.storage.memory import MemoryObjectStore

COLUMNS = ["name", "level", "parent", "government", "code", "population", "homepage", "alias_fr"]
ROWS_V1 = [
    ["Elm", "region", "Ontario", "County of Elm", "3598", "5000", "http://www.elmcounty.ca/", ""],
    ["Nowhere", "region", "Ontario", "", "3597", "300", "", ""],
    [
        "Oakville",
        "municipality",
        "Elm",
        "Town of Oakville",
        "3598001",
        "1200",
        "https://oakville.example/en/",
        "Oakville-les-Chênes",
    ],
    ["Pine", "municipality", "Ontario", "Township of Pine", "3598002", "800", "", ""],
]
# A new release: Oakville grew, Pine left the list, and a village arrived.
ROWS_V2 = [
    ROWS_V1[0],
    ROWS_V1[1],
    [*ROWS_V1[2][:5], "1300", *ROWS_V1[2][6:]],
    [
        "Birch",
        "municipality",
        "Elm",
        "Village of Birch",
        "3598003",
        "150",
        "http://www.elmcounty.ca/birch",
        "",
    ],
]


def csv_bytes(rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    return buffer.getvalue().encode()


def list_module(name: str, source: ListFile, entries: Callable[..., object]) -> ModuleType:
    """A list module as the loader reads one: the four names it looks for."""
    module = ModuleType(f"public_atlas.modules.imports.lists.{name}")
    module.__dict__.update(COUNTRY="CA", SOURCES=(source,), OVERRIDES={}, entries=entries)
    return module


def tiny_places(
    rows: list[list[str]],
    cache_dir: Path,
    name: str = "tiny_places",
    *,
    manual: bool = False,
    overrides: dict[str, dict[str, str]] | None = None,
) -> ModuleType:
    """A list module written for the test, its one file placed in the cache: fetched with its
    hash pinned, or obtained by hand."""
    data = csv_bytes(rows)
    if manual:
        source = ListFile(
            name="tiny_export",
            title="The tiny directory's export",
            url="https://register.example/directory",
            format=Format.CSV,
            retrieval=Retrieval.MANUAL,
            instructions="Open the directory and export every row as CSV.",
            filename_override="places.csv",
            min_rows=len(rows),
        )
    else:
        source = ListFile(
            name="tiny_register",
            title="The tiny register",
            url="https://register.example/places.csv",
            sha256=evidence.content_hash(data),
            format=Format.CSV,
        )
    source.cache_path(cache_dir).parent.mkdir(parents=True, exist_ok=True)
    source.cache_path(cache_dir).write_bytes(data)

    def entries(files: Mapping[str, OpenedFile], rules: countries.CountryRules) -> list[PlaceEntry]:
        found = []
        for row in files[source.name].rows:
            cite = Citation(source=source.name, line=row.line)
            citations: dict = {"place": cite}
            if row["homepage"]:
                citations["homepage"] = cite
            found.append(
                PlaceEntry(
                    name=row["name"],
                    aliases=(AliasEntry(text=row["alias_fr"], language="fr"),)
                    if row["alias_fr"]
                    else (),
                    level=row["level"],
                    parent=row["parent"],
                    government=row["government"] or None,
                    code=Code(scheme=IdentifierScheme.STATCAN_SGC, value=row["code"]),
                    figures=(
                        Figure(
                            name=MetricName.POPULATION,
                            year=2021,
                            value=Decimal(row["population"]),
                            citation=cite,
                        ),
                    ),
                    homepage=row["homepage"] or None,
                    citations=citations,
                )
            )
        assert rules.country_code == "CA"
        return found

    module = list_module(name, source, entries)
    module.__dict__["OVERRIDES"] = overrides or {}
    return module


def tiny_libraries(cache_dir: Path) -> ModuleType:
    data = b"name,place,served\nOakville Public Library,Oakville,Pine\n"
    source = ListFile(
        name="tiny_libraries",
        title="The tiny library list",
        url="https://libraries.example/list.csv",
        sha256=evidence.content_hash(data),
        format=Format.CSV,
    )
    source.cache_path(cache_dir).write_bytes(data)

    def entries(
        files: Mapping[str, OpenedFile], rules: countries.CountryRules
    ) -> list[InstitutionEntry]:
        return [
            InstitutionEntry(
                name=row["name"],
                institution_type="library",
                place=row["place"],
                served_places=(ServedPlace(name=row["served"]),),
                homepage="https://oakville.example/library",
                citations={
                    "institution": Citation(source=source.name, line=row.line),
                    "homepage": Citation(source=source.name, line=row.line),
                },
            )
            for row in files[source.name].rows
        ]

    return list_module("tiny_libraries", source, entries)


def tiny_colleges(cache_dir: Path, rows: list[list[str]]) -> ModuleType:
    """Institutions placed by name, level and parent: columns name, alias, place, level,
    parent."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["name", "alias", "place", "level", "parent"])
    writer.writerows(rows)
    data = buffer.getvalue().encode()
    source = ListFile(
        name="tiny_colleges",
        title="The tiny college list",
        url="https://colleges.example/list.csv",
        sha256=evidence.content_hash(data),
        format=Format.CSV,
    )
    source.cache_path(cache_dir).write_bytes(data)

    def entries(
        files: Mapping[str, OpenedFile], rules: countries.CountryRules
    ) -> list[InstitutionEntry]:
        return [
            InstitutionEntry(
                name=row["name"],
                aliases=(AliasEntry(text=row["alias"]),) if row["alias"] else (),
                institution_type="college",
                place=row["place"],
                place_level=row["level"] or None,
                place_parent=row["parent"] or None,
                citations={"institution": Citation(source=source.name, line=row.line)},
            )
            for row in files[source.name].rows
        ]

    return list_module("tiny_colleges", source, entries)


async def seed(db: Database) -> None:
    async with db.session() as session:
        await countries.seed(session, canada.SEED)
        await session.commit()


async def seed_united_states(db: Database) -> None:
    async with db.session() as session:
        await countries.seed(session, united_states.SEED)
        await session.commit()


US_COLUMNS = ["name", "level", "parent", "parent_level", "parent_parent", "government", "code"]
# Two counties of one name, a town and the village inside it, and a city under its state.
US_ROWS = [
    ["Erie County", "county", "New York", "state", "", "Erie County", "36029"],
    ["Erie County", "county", "Pennsylvania", "state", "", "Erie County", "42049"],
    [
        "Hamburg",
        "municipality",
        "Erie County",
        "county",
        "New York",
        "Town of Hamburg",
        "3602932402",
    ],
    [
        "Hamburg",
        "municipality",
        "Erie County",
        "county",
        "New York",
        "Village of Hamburg",
        "3632396",
    ],
    ["Seattle", "municipality", "Washington", "state", "", "City of Seattle", "5363000"],
    # A city and a township of one name that carries a designator word of its own.
    ["Cheyenne County", "county", "Kansas", "state", "", "Cheyenne County", "20023"],
    [
        "Bird City",
        "municipality",
        "Cheyenne County",
        "county",
        "Kansas",
        "City of Bird City",
        "2006825",
    ],
    [
        "Bird City",
        "municipality",
        "Cheyenne County",
        "county",
        "Kansas",
        "Township of Bird City",
        "2002306850",
    ],
    # Two townships: the second's name is no form of the first's.
    ["Knox County", "county", "Illinois", "state", "", "Knox County", "17095"],
    [
        "Galesburg",
        "municipality",
        "Knox County",
        "county",
        "Illinois",
        "Township of Galesburg",
        "1709528339",
    ],
    [
        "Galesburg City",
        "municipality",
        "Knox County",
        "county",
        "Illinois",
        "Township of Galesburg City",
        "1709528352",
    ],
]


def tiny_us_places(rows: list[list[str]], cache_dir: Path) -> ModuleType:
    """A list module of United States places, each parent named with its level and its own
    parent."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(US_COLUMNS)
    writer.writerows(rows)
    data = buffer.getvalue().encode()
    source = ListFile(
        name="tiny_estimates",
        title="The tiny estimates",
        url="https://census.example/estimates.csv",
        sha256=evidence.content_hash(data),
        format=Format.CSV,
    )
    source.cache_path(cache_dir).parent.mkdir(parents=True, exist_ok=True)
    source.cache_path(cache_dir).write_bytes(data)

    def entries(files: Mapping[str, OpenedFile], rules: countries.CountryRules) -> list[PlaceEntry]:
        assert rules.country_code == "US"
        return [
            PlaceEntry(
                name=row["name"],
                level=row["level"],
                parent=row["parent"],
                parent_level=row["parent_level"] or None,
                parent_parent=row["parent_parent"] or None,
                government=row["government"],
                code=Code(scheme=IdentifierScheme.FIPS, value=row["code"]),
                citations={"place": Citation(source=source.name, line=row.line)},
            )
            for row in files[source.name].rows
        ]

    module = list_module("tiny_us_places", source, entries)
    module.__dict__["COUNTRY"] = "US"
    return module


async def load(
    db: Database, store: MemoryObjectStore, module: ModuleType, cache_dir: Path, *, apply: bool
) -> service.LoadReport:
    async with db.session() as session:
        report = await service.load_list(session, store, module, cache_dir=cache_dir, apply=apply)
        if apply:
            await session.commit()
        else:
            await session.rollback()
    return report


async def dry_run(
    db: Database, store: MemoryObjectStore, module: ModuleType, cache_dir: Path
) -> service.LoadReport:
    return await load(db, store, module, cache_dir, apply=False)


async def apply(
    db: Database, store: MemoryObjectStore, module: ModuleType, cache_dir: Path
) -> service.LoadReport:
    return await load(db, store, module, cache_dir, apply=True)


async def count(db: Database, model: type, *where: ColumnElement[bool]) -> int:
    async with db.session() as session:
        query = select(func.count()).select_from(model)
        for clause in where:
            query = query.where(clause)
        return (await session.execute(query)).scalar_one()


@dataclass
class Oakville:
    place: Place
    parent: Place
    government: Institution
    aliases: list[str]
    identifier: Identifier
    metric: Metric
    homepage: Homepage
    webpage: Webpage
    domain: Domain
    quotes: dict[EvidenceKind, str]
    link: Evidence
    snapshot: Snapshot


async def read_oakville(db: Database) -> Oakville:
    async with db.session() as session:
        place = (await session.execute(select(Place).where(Place.name == "Oakville"))).scalar_one()
        assert place.parent_place_id is not None
        assert place.government_institution_id is not None
        government = await session.get_one(Institution, place.government_institution_id)
        homepage = (
            await session.execute(select(Homepage).where(Homepage.institution_id == government.id))
        ).scalar_one()
        webpage = await session.get_one(Webpage, homepage.webpage_id)
        quotes = (
            await session.execute(
                select(Evidence.kind, Evidence.quote).where(
                    Evidence.entity_id.in_([place.id, government.id, homepage.id])
                )
            )
        ).tuples()
        link = (
            await session.execute(select(Evidence).where(Evidence.entity_id == homepage.id))
        ).scalar_one()
        return Oakville(
            place=place,
            parent=await session.get_one(Place, place.parent_place_id),
            government=government,
            aliases=list(
                await session.scalars(
                    select(Alias.text).where(Alias.place_id == place.id).order_by(Alias.text)
                )
            ),
            identifier=(
                await session.execute(select(Identifier).where(Identifier.place_id == place.id))
            ).scalar_one(),
            metric=(
                await session.execute(select(Metric).where(Metric.place_id == place.id))
            ).scalar_one(),
            homepage=homepage,
            webpage=webpage,
            domain=await session.get_one(Domain, webpage.domain_id),
            quotes=dict(quotes.all()),
            link=link,
            snapshot=await session.get_one(Snapshot, link.snapshot_id),
        )


def test_a_dry_run_reports_and_writes_nothing(
    db: Database, object_store: MemoryObjectStore, tmp_path: Path
):
    db.run(seed, db)
    module = tiny_places(ROWS_V1, tmp_path)

    report = db.run(dry_run, db, object_store, module, tmp_path)

    assert not report.applied
    assert report.entries == 4
    assert report.count("add", "place") == 4
    assert report.count("add", "institution") == 3
    assert report.count("add", "identifier") == 4
    assert report.count("add", "metric") == 4
    assert report.count("add", "homepage") == 2
    assert report.count("add", "official_list") == 1
    assert report.count("add", "snapshot") == 1
    # The register's domain, trusted, and the two homepages' candidate domains.
    assert report.count("add", "domain") == 3
    assert report.skipped == []
    assert "dry run" in report.render()
    # Only Canada and Ontario.
    # The seed's Canada and thirteen provinces and territories, and nothing else.
    assert db.run(count, db, Place) == 14
    assert object_store.objects == {}


def test_an_apply_writes_the_rows_and_a_rerun_changes_nothing(
    db: Database, object_store: MemoryObjectStore, tmp_path: Path
):
    db.run(seed, db)
    module = tiny_places(ROWS_V1, tmp_path)

    report = db.run(apply, db, object_store, module, tmp_path)
    assert report.applied
    assert db.run(count, db, Place) == 14 + 4
    assert db.run(count, db, Institution) == 14 + 3
    assert db.run(count, db, Identifier) == 4
    assert db.run(count, db, Metric) == 4
    assert db.run(count, db, Homepage) == 2
    # Place, government and homepage quotes: 4 + 3 + 2.
    assert db.run(count, db, Evidence) == 9

    found = db.run(read_oakville, db)
    assert (found.place.status, found.place.entered_by) == (
        EntityStatus.VERIFIED,
        EnteredBy.SCRIPT,
    )
    assert found.place.administrative_level == "municipality"
    assert found.parent.name == "Elm"
    assert found.parent.administrative_level == "region"
    assert found.aliases == ["Oakville", "Oakville-les-Chênes"]
    assert found.government.name == "Town of Oakville"
    assert found.government.institution_type == "municipal_government"
    assert (found.government.status, found.government.entered_by) == (
        EntityStatus.VERIFIED,
        EnteredBy.SCRIPT,
    )
    assert (found.identifier.scheme, found.identifier.value) == (
        IdentifierScheme.STATCAN_SGC,
        "3598001",
    )
    assert found.identifier.official_list_id is not None
    assert (found.metric.name, found.metric.year, found.metric.value) == (
        MetricName.POPULATION,
        2021,
        Decimal(1200),
    )
    assert (found.homepage.status, found.homepage.entered_by) == (
        EntityStatus.CANDIDATE,
        EnteredBy.SCRIPT,
    )
    assert found.homepage.found_on_webpage_id is None
    assert found.webpage.url == "https://oakville.example/en/"
    assert (found.domain.name, found.domain.domain_kind, found.domain.status) == (
        "oakville.example",
        DomainKind.OFFICIAL,
        EntityStatus.CANDIDATE,
    )
    # Every quote is the list's own line, found in the stored text at its locator.
    line = " | ".join(ROWS_V1[2])
    assert found.quotes == {EvidenceKind.APPEARS_ON: line, EvidenceKind.LINKS_TO: line}
    assert found.link.link_url == "https://oakville.example/en/"
    assert found.link.entered_by == EnteredBy.SCRIPT
    assert found.link.locator is not None
    assert found.snapshot.text_key is not None
    text = object_store.objects[found.snapshot.text_key][0].decode()
    assert text.splitlines()[found.link.locator - 1] == line
    assert object_store.objects[found.snapshot.bytes_key][0] == csv_bytes(ROWS_V1)

    again = db.run(apply, db, object_store, module, tmp_path)
    assert again.changes == []
    assert again.skipped == []
    assert "nothing to change" in again.render()
    assert db.run(count, db, Evidence) == 9
    # The seed's 14 places and 14 governments, the 4 places, Oakville's French name, the 3
    # governments.
    assert db.run(count, db, Alias) == 28 + 4 + 1 + 3


def test_a_district_has_no_government_and_the_lists_domain_is_trusted(
    db: Database, object_store: MemoryObjectStore, tmp_path: Path
):
    db.run(seed, db)
    db.run(apply, db, object_store, tiny_places(ROWS_V1, tmp_path), tmp_path)

    async def read(db: Database) -> tuple[Place, Domain]:
        async with db.session() as session:
            nowhere = (
                await session.execute(select(Place).where(Place.name == "Nowhere"))
            ).scalar_one()
            register = (
                await session.execute(select(Domain).where(Domain.name == "register.example"))
            ).scalar_one()
            return nowhere, register

    nowhere, register = db.run(read, db)
    assert nowhere.government_institution_id is None
    assert nowhere.status is EntityStatus.VERIFIED
    assert (register.domain_kind, register.status, register.entered_by) == (
        DomainKind.OFFICIAL,
        EntityStatus.VERIFIED,
        EnteredBy.SCRIPT,
    )


def test_a_new_release_changes_what_moved_and_reports_what_left(
    db: Database, object_store: MemoryObjectStore, tmp_path: Path
):
    db.run(seed, db)
    db.run(apply, db, object_store, tiny_places(ROWS_V1, tmp_path), tmp_path)

    report = db.run(apply, db, object_store, tiny_places(ROWS_V2, tmp_path), tmp_path)

    changes = {(c.action, c.table, c.label) for c in report.changes}
    assert ("change", "metric", "Oakville (municipality)") in changes
    assert ("add", "place", "Birch (municipality)") in changes
    assert ("remove", "place", "Pine (municipality)") in changes
    assert ("add", "official_list", "tiny_places/tiny_register") in changes
    assert ("add", "snapshot", "places.csv") in changes
    # Elm's domain covers Birch's homepage: no new domain for it.
    assert report.count("add", "domain") == 0
    assert ("add", "place", "Elm (region)") not in changes
    # Pine is kept.
    assert db.run(count, db, Place, Place.name == "Pine") == 1
    assert db.run(count, db, Place) == 14 + 5

    async def oakville_population(db: Database) -> Decimal:
        async with db.session() as session:
            return (
                await session.execute(
                    select(Metric.value)
                    .join(Place, Place.id == Metric.place_id)
                    .where(Place.name == "Oakville")
                )
            ).scalar_one()

    assert db.run(oakville_population, db) == Decimal(1300)


def test_entries_the_loader_cannot_place_are_skipped_with_a_reason(
    db: Database, object_store: MemoryObjectStore, tmp_path: Path
):
    db.run(seed, db)
    rows = [
        ["Orphan", "municipality", "Atlantis", "Town of Orphan", "3598009", "10", "", ""],
        ["Elm", "region", "Ontario", "County of Elm", "3598", "5000", "", ""],
        # Elm's code at another level.
        ["Elmtown", "municipality", "Elm", "Town of Elmtown", "3598", "20", "", ""],
        ["Unknown", "parish", "Ontario", "Parish of Unknown", "3598010", "20", "", ""],
    ]
    report = db.run(apply, db, object_store, tiny_places(rows, tmp_path), tmp_path)

    assert report.count("add", "place") == 1
    assert len(report.skipped) == 3
    assert any("Orphan" in line and "Atlantis" in line for line in report.skipped)
    assert any("Elmtown" in line and "3598" in line for line in report.skipped)
    assert any("Unknown" in line and "parish" in line for line in report.skipped)


def test_an_institution_list_loads_under_the_places(
    db: Database, object_store: MemoryObjectStore, tmp_path: Path
):
    db.run(seed, db)
    db.run(apply, db, object_store, tiny_places(ROWS_V1, tmp_path), tmp_path)

    report = db.run(apply, db, object_store, tiny_libraries(tmp_path), tmp_path)
    assert report.count("add", "institution") == 1
    assert report.count("add", "served place") == 1
    assert report.count("add", "homepage") == 1
    assert report.skipped == []

    async def read(db: Database) -> tuple[Institution, Institution, Place, int]:
        async with db.session() as session:
            library = (
                await session.execute(
                    select(Institution).where(Institution.name == "Oakville Public Library")
                )
            ).scalar_one()
            assert library.parent_institution_id is not None
            parent = await session.get_one(Institution, library.parent_institution_id)
            served = (
                await session.execute(
                    select(Place)
                    .join(InstitutionServedPlace, InstitutionServedPlace.place_id == Place.id)
                    .where(InstitutionServedPlace.institution_id == library.id)
                )
            ).scalar_one()
            homepages = (
                await session.execute(
                    select(func.count())
                    .select_from(Homepage)
                    .where(Homepage.institution_id == library.id)
                )
            ).scalar_one()
            return library, parent, served, homepages

    library, parent, served, homepages = db.run(read, db)
    assert library.institution_type == "library"
    assert library.status is EntityStatus.VERIFIED
    assert parent.name == "Town of Oakville"
    assert served.name == "Pine"
    assert homepages == 1

    again = db.run(apply, db, object_store, tiny_libraries(tmp_path), tmp_path)
    assert again.changes == []


async def institutions_named(db: Database, name: str) -> list[tuple[str, list[str]]]:
    """Each institution of the name with the name of its place and its aliases."""
    async with db.session() as session:
        found = []
        for institution in await session.scalars(
            select(Institution).where(Institution.name == name)
        ):
            place = await session.get_one(Place, institution.place_id)
            aliases = list(
                await session.scalars(
                    select(Alias.text)
                    .where(Alias.institution_id == institution.id)
                    .order_by(Alias.text)
                )
            )
            found.append((place.name, sorted(aliases)))
        return sorted(found)


async def colleges_placed(db: Database) -> dict[str, tuple[str, str, str | None]]:
    """Each college's place: its name, level and parent's name."""
    async with db.session() as session:
        found = {}
        for institution in await session.scalars(
            select(Institution).where(Institution.institution_type == "college")
        ):
            place = await session.get_one(Place, institution.place_id)
            parent = None
            if place.parent_place_id is not None:
                parent = (await session.get_one(Place, place.parent_place_id)).name
            found[institution.name] = (place.name, place.administrative_level, parent)
        return found


def test_institutions_are_matched_by_their_whole_names(
    db: Database, object_store: MemoryObjectStore, tmp_path: Path
):
    """Two colleges "of Applied Arts and Technology" at one place are two bodies; a body is
    found again by its name or an alias, however the list spells it."""
    db.run(seed, db)
    db.run(apply, db, object_store, tiny_places(ROWS_V1, tmp_path), tmp_path)
    rows = [
        ["Centennial College of Applied Arts and Technology", "", "Oakville", "", ""],
        ["Seneca Polytechnic", "Seneca College of Applied Arts and Technology", "Oakville", "", ""],
    ]
    report = db.run(apply, db, object_store, tiny_colleges(tmp_path, rows), tmp_path)
    assert report.count("add", "institution") == 2
    assert report.skipped == []

    renamed = [
        ["seneca  college of applied arts & technology", "", "Oakville", "", ""],
        ["Centennial College of Applied Arts and Technology", "CCAAT", "Oakville", "", ""],
    ]
    again = db.run(apply, db, object_store, tiny_colleges(tmp_path, renamed), tmp_path)
    assert again.count("add", "institution") == 0
    assert again.count("add", "institution alias") == 2
    assert db.run(count, db, Institution, Institution.institution_type == "college") == 2
    assert db.run(institutions_named, db, "Seneca Polytechnic") == [
        (
            "Oakville",
            [
                "Seneca College of Applied Arts and Technology",
                "Seneca Polytechnic",
                "seneca college of applied arts & technology",
            ],
        )
    ]


def test_an_institution_names_the_place_it_means_by_level_and_parent(
    db: Database, object_store: MemoryObjectStore, tmp_path: Path
):
    db.run(seed, db)
    rows = [
        *ROWS_V1,
        # A municipality named like its region, and a township named like a city elsewhere.
        ["Elm", "municipality", "Elm", "City of Elm", "3598004", "900", "", ""],
        ["Oakville", "municipality", "Ontario", "Township of Oakville", "3598005", "90", "", ""],
    ]
    db.run(apply, db, object_store, tiny_places(rows, tmp_path), tmp_path)
    colleges = [
        ["Elm College", "", "Elm", "", ""],
        ["Elm City College", "", "Elm", "municipality", ""],
        ["Elm County College", "", "Elm", "region", ""],
        ["Oakville College", "", "Oakville", "municipality", ""],
        ["Oakville Town College", "", "Oakville", "municipality", "Elm"],
        ["Oakville Township College", "", "Oakville", "", "Ontario"],
        ["Atlantis College", "", "Oakville", "municipality", "Atlantis"],
        ["Parish College", "", "Oakville", "parish", ""],
    ]
    report = db.run(apply, db, object_store, tiny_colleges(tmp_path, colleges), tmp_path)

    assert [line.split(":")[0] for line in report.skipped] == [
        "Elm College",
        "Oakville College",
        "Atlantis College",
        "Parish College",
    ]
    assert "2 places go by 'Elm' at levels" in report.skipped[0]
    assert "2 places go by 'Oakville' at levels ['municipality']" in report.skipped[1]
    assert "no place named 'Oakville' sits under 'Atlantis'" in report.skipped[2]
    assert "no administrative level 'parish'" in report.skipped[3]
    assert report.count("add", "institution") == 4, report.render()

    found = db.run(colleges_placed, db)
    assert found == {
        "Elm City College": ("Elm", "municipality", "Elm"),
        "Elm County College": ("Elm", "region", "Ontario"),
        "Oakville Town College": ("Oakville", "municipality", "Elm"),
        "Oakville Township College": ("Oakville", "municipality", "Ontario"),
    }


async def read_lists(db: Database) -> list[tuple[str, Retrieval]]:
    async with db.session() as session:
        rows = await session.execute(
            select(OfficialList.name, OfficialList.retrieval).order_by(OfficialList.name)
        )
        return list(rows.tuples().all())


def test_a_manual_file_loads_like_a_fetched_one_and_is_recorded_as_manual(
    db: Database, object_store: MemoryObjectStore, tmp_path: Path
):
    db.run(seed, db)
    module = tiny_places(ROWS_V1, tmp_path, "tiny_manual", manual=True)

    report = db.run(apply, db, object_store, module, tmp_path)

    assert report.skipped == []
    assert report.count("add", "place") == 4
    changes = {(c.action, c.table, c.label, c.detail) for c in report.changes}
    assert ("add", "official_list", "tiny_manual/tiny_export", "manual") in changes
    assert db.run(read_lists, db) == [("tiny_manual/tiny_export", Retrieval.MANUAL)]
    assert db.run(apply, db, object_store, module, tmp_path).changes == []


def test_an_override_that_matches_nothing_is_reported(
    db: Database, object_store: MemoryObjectStore, tmp_path: Path
):
    db.run(seed, db)
    overrides = {
        "3598001": {"reason": "keyed by Oakville's code"},
        "Pine": {"reason": "keyed by a name"},
        "Oakville-les-Chênes": {"reason": "keyed by an alias"},
        "3598999": {"reason": "a code no row carries"},
    }
    module = tiny_places(ROWS_V1, tmp_path, overrides=overrides)

    report = db.run(dry_run, db, object_store, module, tmp_path)

    assert report.idle_overrides == ["3598999"]
    assert "overrides that matched nothing: 1" in report.render()


async def read_us_places(db: Database) -> dict[str, list[tuple[str, str | None]]]:
    """Each loaded place's name with its parent's name and its government's name."""
    async with db.session() as session:
        places = list(
            (
                await session.execute(
                    select(Place).where(
                        Place.country_code == "US",
                        Place.administrative_level.in_(["county", "municipality"]),
                    )
                )
            ).scalars()
        )
        found: dict[str, list[tuple[str, str | None]]] = {}
        for place in places:
            parent = await session.get_one(Place, place.parent_place_id)
            government = (
                await session.get_one(Institution, place.government_institution_id)
                if place.government_institution_id is not None
                else None
            )
            found.setdefault(place.name, []).append(
                (parent.name, government.name if government is not None else None)
            )
        return {name: sorted(rows) for name, rows in found.items()}


def test_a_parent_is_named_with_its_level_and_its_own_parent_and_a_designator_tells_places_apart(
    db: Database, object_store: MemoryObjectStore, tmp_path: Path
):
    db.run(seed_united_states, db)
    module = tiny_us_places(US_ROWS, tmp_path)

    report = db.run(apply, db, object_store, module, tmp_path)

    assert report.skipped == []
    assert report.count("add", "place") == 11
    assert report.count("change") == 0
    assert db.run(read_us_places, db) == {
        "Bird City": [
            ("Cheyenne County", "City of Bird City"),
            ("Cheyenne County", "Township of Bird City"),
        ],
        "Cheyenne County": [("Kansas", "Cheyenne County")],
        "Erie County": [("New York", "Erie County"), ("Pennsylvania", "Erie County")],
        "Galesburg": [("Knox County", "Township of Galesburg")],
        "Galesburg City": [("Knox County", "Township of Galesburg City")],
        "Knox County": [("Illinois", "Knox County")],
        # Two places under one county: a town and the village inside it.
        "Hamburg": [("Erie County", "Town of Hamburg"), ("Erie County", "Village of Hamburg")],
        # Under the state of Washington, not a Washington County.
        "Seattle": [("Washington", "City of Seattle")],
    }

    again = db.run(apply, db, object_store, module, tmp_path)
    assert again.changes == []
    assert again.skipped == []


def test_a_parent_two_places_go_by_is_refused_without_its_own_parent(
    db: Database, object_store: MemoryObjectStore, tmp_path: Path
):
    db.run(seed_united_states, db)
    rows = [
        *US_ROWS[:2],
        ["Buffalo", "municipality", "Erie County", "county", "", "City of Buffalo", "3611000"],
        ["Erie", "municipality", "Erie County", "", "", "City of Erie", "4224000"],
    ]
    module = tiny_us_places(rows, tmp_path)

    report = db.run(dry_run, db, object_store, module, tmp_path)

    assert report.count("add", "place") == 2
    assert report.skipped == [
        "Buffalo: 2 places go by 'Erie County' at levels ['county']",
        "Erie: 2 places go by 'Erie County' at levels ['country', 'state', 'county']",
    ]


ONTARIO_CACHED = all(
    source.cache_path(Settings().lists_cache_dir).exists() for source in ontario_places.SOURCES
)


@pytest.mark.skipif(not ONTARIO_CACHED, reason="the Ontario list's files are not cached")
def test_loading_ontario_gives_the_pilots_places(db: Database, object_store: MemoryObjectStore):
    db.run(seed, db)
    cache_dir = Settings().lists_cache_dir

    report = db.run(apply, db, object_store, ontario_places, cache_dir)

    assert report.skipped == []
    assert report.entries == 454
    assert db.run(count, db, Place, Place.administrative_level == "region") == 40
    assert db.run(count, db, Place, Place.administrative_level == "municipality") == 414
    # The 444 governments and the seed's fourteen.
    assert db.run(count, db, Institution) == 444 + 14
    assert db.run(count, db, Identifier) == 454
    assert db.run(count, db, Metric) == 454
    assert db.run(count, db, Homepage) == 441

    again = db.run(apply, db, object_store, ontario_places, cache_dir)
    assert again.changes == []
    assert again.skipped == []
