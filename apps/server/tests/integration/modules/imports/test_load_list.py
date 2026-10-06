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
from public_atlas.modules.countries.seeds import canada
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
)
from public_atlas.modules.imports.files import Format, OpenedFile, Source
from public_atlas.modules.imports.lists import ontario_places

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


def list_module(name: str, source: Source, entries: Callable[..., object]) -> ModuleType:
    """A list module as the loader reads one: the four names it looks for."""
    module = ModuleType(f"public_atlas.modules.imports.lists.{name}")
    module.__dict__.update(COUNTRY="CA", SOURCES=(source,), OVERRIDES={}, entries=entries)
    return module


def tiny_places(rows: list[list[str]], cache_dir: Path, name: str = "tiny_places") -> ModuleType:
    """A list module written for the test, its one file placed in the cache."""
    data = csv_bytes(rows)
    source = Source(
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

    return list_module(name, source, entries)


def tiny_libraries(cache_dir: Path) -> ModuleType:
    data = b"name,place,served\nOakville Public Library,Oakville,Pine\n"
    source = Source(
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
                served_places=(row["served"],),
                homepage="https://oakville.example/library",
                citations={
                    "institution": Citation(source=source.name, line=row.line),
                    "homepage": Citation(source=source.name, line=row.line),
                },
            )
            for row in files[source.name].rows
        ]

    return list_module("tiny_libraries", source, entries)


async def seed(db: Database) -> None:
    async with db.session() as session:
        await countries.seed(session, canada.SEED)
        await session.commit()


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
    assert db.run(count, db, Place) == 2
    assert object_store.objects == {}


def test_an_apply_writes_the_rows_and_a_rerun_changes_nothing(
    db: Database, object_store: MemoryObjectStore, tmp_path: Path
):
    db.run(seed, db)
    module = tiny_places(ROWS_V1, tmp_path)

    report = db.run(apply, db, object_store, module, tmp_path)
    assert report.applied
    assert db.run(count, db, Place) == 6
    assert db.run(count, db, Institution) == 4
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
    assert db.run(count, db, Alias) == 3 + 4 + 1 + 3


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
    assert db.run(count, db, Place) == 7

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
    # The 444 governments and the Government of Ontario.
    assert db.run(count, db, Institution) == 445
    assert db.run(count, db, Identifier) == 454
    assert db.run(count, db, Metric) == 454
    assert db.run(count, db, Homepage) == 441

    again = db.run(apply, db, object_store, ontario_places, cache_dir)
    assert again.changes == []
    assert again.skipped == []
