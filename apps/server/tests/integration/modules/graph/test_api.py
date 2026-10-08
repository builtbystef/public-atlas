"""The graph API lists institutions with search and filters, reads one with everything attached
to it, and serves the places a filter or a picker needs."""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from public_atlas.modules.assignments.models import AssignmentType
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.evidence.models import EvidenceKind
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import (
    EnteredBy,
    Institution,
    InstitutionServedPlace,
    Metric,
    MetricName,
)

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from tests.integration.conftest import Database
    from tests.integration.modules.conftest import Build, World

    from public_atlas.integrations.storage.memory import MemoryObjectStore

AGENT = EnteredBy.AGENT


async def make_library(
    db: Database, store: MemoryObjectStore, world: World, build: type[Build]
) -> tuple[uuid.UUID, uuid.UUID]:
    """A verified library under Oakville with an acronym, a verified homepage on the county's
    trusted domain, a source, a quote for each, and the county as the place it serves too."""
    async with db.session() as session:
        library = await build.candidate_institution(session, world.oakville, "Oakville Library")
        await graph.add_alias(
            session, library, "OPL", language="en", entered_by=AGENT, is_acronym=True
        )
        await status_changes.verify_institution(session, library, entered_by=AGENT)
        page, snapshot = await build.capture(
            session,
            store,
            "https://www.elmcounty.ca/library",
            "<html><body>Oakville Library, 120 Navy Street</body></html>",
            "Oakville Library, 120 Navy Street",
        )
        await evidence.add_evidence(
            session,
            entity_id=library.id,
            snapshot=snapshot,
            kind=EvidenceKind.APPEARS_ON,
            quote="Oakville Library, 120 Navy Street",
            entered_by=AGENT,
        )
        homepage = await graph.create_homepage(session, library, page, entered_by=AGENT)
        await status_changes.verify_homepage(session, homepage, entered_by=AGENT)
        tenders = await graph.ensure_webpage(session, "https://www.elmcounty.ca/library/tenders")
        source = await graph.create_source(
            session, library, tenders, source_type="tender", entered_by=AGENT
        )
        await status_changes.verify_source(session, source, entered_by=AGENT)
        session.add(InstitutionServedPlace(institution_id=library.id, place_id=world.elm.id))
        await session.commit()
        return library.id, homepage.id


def test_listing_institutions_with_search_filters_and_sorting(
    client: TestClient,
    db: Database,
    object_store: MemoryObjectStore,
    world: World,
    build: type[Build],
):
    library_id, _ = db.run(make_library, db, object_store, world, build)

    everything = client.get("/institutions", params={"country_code": "CA"}).json()
    assert everything["total"] == 4
    assert [row["name"] for row in everything["items"]] == [
        "County of Elm",
        "Government of Ontario",
        "Oakville Library",
        "Town of Oakville",
    ]
    by_acronym = client.get("/institutions", params={"q": "opl"}).json()
    assert [row["id"] for row in by_acronym["items"]] == [str(library_id)]
    row = by_acronym["items"][0]
    assert (row["place"]["name"], row["status"], row["homepage_url"]) == (
        "Oakville",
        "verified",
        "https://www.elmcounty.ca/library",
    )
    # The place filter admits the place and everything under it.
    under_elm = client.get("/institutions", params={"place_id": str(world.elm.id)}).json()
    assert {row["name"] for row in under_elm["items"]} == {
        "County of Elm",
        "Oakville Library",
        "Town of Oakville",
    }
    by_type = client.get("/institutions", params={"institution_type": "library"}).json()
    assert by_type["total"] == 1
    by_level = client.get(
        "/institutions", params={"administrative_level": "municipality", "sort": "created_at"}
    ).json()
    assert [row["name"] for row in by_level["items"]] == ["Town of Oakville", "Oakville Library"]
    newest = client.get(
        "/institutions",
        params={"administrative_level": "municipality", "sort": "created_at", "order": "desc"},
    ).json()
    assert [row["name"] for row in newest["items"]] == ["Oakville Library", "Town of Oakville"]
    paged = client.get("/institutions", params={"limit": 1, "offset": 1}).json()
    assert (paged["total"], len(paged["items"]), paged["offset"]) == (4, 1, 1)
    assert client.get("/institutions", params={"status": "rejected"}).json()["items"] == []


def test_reading_an_institution_with_everything_attached(
    client: TestClient,
    db: Database,
    object_store: MemoryObjectStore,
    world: World,
    build: type[Build],
):
    library_id, homepage_id = db.run(make_library, db, object_store, world, build)

    response = client.get(f"/institutions/{library_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Oakville Library"
    assert [alias["text"] for alias in body["aliases"]] == ["Oakville Library", "OPL"]
    assert body["aliases"][1]["is_acronym"] is True
    assert [place["name"] for place in body["places"]] == ["Oakville", "Elm", "Ontario", "Canada"]
    assert body["parent"]["name"] == "Town of Oakville"
    assert body["served_places"] == [
        {"id": str(world.elm.id), "name": "Elm", "administrative_level": "region"}
    ]
    assert body["homepage_id"] == str(homepage_id)
    assert body["homepage_url"] == "https://www.elmcounty.ca/library"
    (homepage,) = body["homepages"]
    assert (homepage["status"], homepage["domain"], homepage["domain_status"]) == (
        "verified",
        "elmcounty.ca",
        "verified",
    )
    (source,) = body["sources"]
    assert (source["source_type"], source["url"], source["status"]) == (
        "tender",
        "https://www.elmcounty.ca/library/tenders",
        "verified",
    )
    (quote,) = body["evidence"]
    assert quote["entity_id"] == str(library_id)
    assert quote["quote"] == "Oakville Library, 120 Navy Street"
    assert quote["page_url"] == "https://www.elmcounty.ca/library"
    assert quote["snapshot_url"].startswith("memory://snapshots/")

    town = client.get(f"/institutions/{world.town.id}").json()
    assert [child["name"] for child in town["children"]] == ["Oakville Library"]
    assert town["parent"] is None
    assert client.get(f"/institutions/{uuid.uuid7()}").status_code == 404


def test_listing_and_reading_places(client: TestClient, world: World):
    listed = client.get("/places", params={"country_code": "CA"}).json()
    assert [row["name"] for row in listed["items"]] == ["Canada", "Elm", "Oakville", "Ontario"]
    assert listed["total"] == 4
    regions = client.get("/places", params={"administrative_level": "region"}).json()
    assert [row["name"] for row in regions["items"]] == ["Elm"]
    under_elm = client.get("/places", params={"parent_place_id": str(world.elm.id)}).json()
    assert [row["name"] for row in under_elm["items"]] == ["Oakville"]
    by_name = client.get("/places", params={"q": "oak"}).json()
    assert [row["id"] for row in by_name["items"]] == [str(world.oakville.id)]

    detail = client.get(f"/places/{world.oakville.id}").json()
    assert [parent["name"] for parent in detail["parents"]] == ["Elm", "Ontario", "Canada"]
    assert detail["government"]["name"] == "Town of Oakville"
    assert client.get(f"/places/{uuid.uuid7()}").status_code == 404


async def count_people(db: Database, world: World) -> None:
    """Census figures for Ontario, Elm and Oakville, with an older one for Oakville that the
    newer one replaces; Canada has none."""
    figures = [
        (world.ontario.id, 2021, 14_223_942),
        (world.elm.id, 2021, 650_000),
        (world.oakville.id, 2016, 193_832),
        (world.oakville.id, 2021, 213_759),
    ]
    async with db.session() as session:
        session.add_all(
            Metric(place_id=place_id, name=MetricName.POPULATION, year=year, value=Decimal(value))
            for place_id, year, value in figures
        )
        await session.commit()


def test_places_carry_their_newest_population_and_filter_and_sort_by_it(
    client: TestClient, db: Database, world: World
):
    db.run(count_people, db, world)

    by_size = client.get("/places", params={"sort": "population", "order": "desc"}).json()
    # A place with no figure comes last whichever way the list runs.
    assert [(row["name"], row["population"]) for row in by_size["items"]] == [
        ("Ontario", 14_223_942),
        ("Elm", 650_000),
        ("Oakville", 213_759),
        ("Canada", None),
    ]
    smallest = client.get("/places", params={"sort": "population"}).json()
    assert [row["name"] for row in smallest["items"]] == ["Oakville", "Elm", "Ontario", "Canada"]
    middling = client.get(
        "/places", params={"min_population": 200_000, "max_population": 650_000}
    ).json()
    assert ([row["name"] for row in middling["items"]], middling["total"]) == (
        ["Elm", "Oakville"],
        2,
    )
    assert client.get(f"/places/{world.oakville.id}").json()["population"] == 213_759
    assert client.get("/places", params={"min_population": -1}).status_code == 422


def test_institutions_filter_and_sort_by_their_places_population(
    client: TestClient, db: Database, world: World
):
    db.run(count_people, db, world)

    local = client.get(
        "/institutions", params={"max_population": 1_000_000, "sort": "population"}
    ).json()
    assert [(row["name"], row["place_population"]) for row in local["items"]] == [
        ("Town of Oakville", 213_759),
        ("County of Elm", 650_000),
    ]
    assert local["total"] == 2
    large = client.get("/institutions", params={"min_population": 1_000_000}).json()
    assert [row["name"] for row in large["items"]] == ["Government of Ontario"]
    town = client.get(f"/institutions/{world.town.id}").json()
    assert town["place_population"] == 213_759


def test_a_rejected_institution_is_listed_by_status(
    client: TestClient, db: Database, world: World, build: type[Build]
):
    async def reject_one() -> uuid.UUID:
        async with db.session() as session:
            archive = await build.candidate_institution(session, world.oakville, "Oakville Archive")
            await status_changes.reject_institution(session, archive, entered_by=EnteredBy.MANUAL)
            await session.commit()
            return archive.id

    archive_id = db.run(reject_one)
    rejected = client.get("/institutions", params={"status": "rejected"}).json()
    assert [row["id"] for row in rejected["items"]] == [str(archive_id)]

    async def check() -> Institution:
        async with db.session() as session:
            return await session.get_one(Institution, archive_id)

    assert db.run(check).status.value == "rejected"


def test_a_quote_is_read_in_the_context_of_its_page(
    client: TestClient,
    db: Database,
    object_store: MemoryObjectStore,
    world: World,
    build: type[Build],
):
    library_id, _ = db.run(make_library, db, object_store, world, build)
    (quote,) = client.get(f"/institutions/{library_id}").json()["evidence"]
    context = client.get(f"/evidence/{quote['id']}/context").json()
    assert context["found"] is True
    assert context["quote"] == "Oakville Library, 120 Navy Street"
    assert (context["before"], context["after"], context["page"]) == ("", "", None)
    assert client.get(f"/evidence/{uuid.uuid7()}/context").status_code == 404


def test_an_assignments_findings_are_the_quotes_it_recorded(
    client: TestClient,
    db: Database,
    object_store: MemoryObjectStore,
    world: World,
    build: type[Build],
):
    async def make() -> tuple[uuid.UUID, uuid.UUID]:
        async with db.session() as session:
            assignment = await build.open_assignment(
                session, world.run, AssignmentType.FIND_INSTITUTIONS, world.oakville.id
            )
            library = await build.candidate_institution(session, world.oakville, "Oakville Library")
            _, snapshot = await build.capture(
                session,
                object_store,
                "https://www.elmcounty.ca/bodies",
                "<html><body>Oakville Library serves the town</body></html>",
                "Oakville Library serves the town",
                assignment_id=assignment.id,
            )
            await evidence.add_evidence(
                session,
                entity_id=library.id,
                snapshot=snapshot,
                kind=EvidenceKind.APPEARS_ON,
                quote="Oakville Library serves the town",
                entered_by=AGENT,
                assignment_id=assignment.id,
            )
            await session.commit()
            return assignment.id, library.id

    assignment_id, library_id = db.run(make)
    findings = client.get(f"/assignments/{assignment_id}/findings").json()
    assert len(findings) == 1
    finding = findings[0]
    assert (finding["entity_id"], finding["entity_kind"], finding["label"]) == (
        str(library_id),
        "institution",
        "Oakville Library",
    )
    assert finding["institution_id"] == str(library_id)
    assert finding["page_url"] == "https://www.elmcounty.ca/bodies"
    assert finding["snapshot_url"].startswith("memory://snapshots/")
    assert client.get(f"/assignments/{uuid.uuid7()}/findings").status_code == 404
