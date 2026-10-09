"""The graph view's payload: the places under a root, the institutions in them, their homepages
and sources and the domains those sit on, as nodes and edges; its filters; an expansion from one
place or one institution; and the cap that cuts a big picture down to places and governments."""

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes, subgraph
from public_atlas.modules.graph.models import DomainKind, EnteredBy, InstitutionServedPlace

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from tests.integration.conftest import Database
    from tests.integration.modules.conftest import Build, World

BY = EnteredBy.SCRIPT


@dataclass(frozen=True, slots=True)
class Picture:
    """What the test adds to the world: a second municipality with its government, a verified
    source for the county on its own domain, a candidate library on a platform that serves the
    new town too, and a rejected body."""

    milton: uuid.UUID
    milton_government: uuid.UUID
    source: uuid.UUID
    platform: uuid.UUID
    library: uuid.UUID
    library_claim: uuid.UUID
    rejected: uuid.UUID


async def make_picture(db: Database, world: World, build: type[Build]) -> Picture:
    async with db.session() as session:
        milton = await build.verified_place(session, "Milton", "municipality", world.elm)
        milton_government = await build.verified_government(session, milton, "Town of Milton")
        tenders = await graph.ensure_webpage(session, "https://www.elmcounty.ca/tenders")
        source = await graph.create_source(
            session, world.county, tenders, source_type="tender", entered_by=BY
        )
        await status_changes.verify_source(session, source, entered_by=BY)
        platform = await graph.create_domain(
            session, "sites.example", kind=DomainKind.PLATFORM, entered_by=BY
        )
        library = await build.candidate_institution(session, world.oakville, "Oakville Library")
        claim = await build.claim(session, library, "https://sites.example/oakville-library/")
        session.add(InstitutionServedPlace(institution_id=library.id, place_id=milton.id))
        rejected = await build.candidate_institution(
            session, milton, "Milton Arena Board", "agency"
        )
        await status_changes.reject_institution(session, rejected, entered_by=BY)
        await session.commit()
        return Picture(
            milton=milton.id,
            milton_government=milton_government.id,
            source=source.id,
            platform=platform.id,
            library=library.id,
            library_claim=claim.id,
            rejected=rejected.id,
        )


def labels(body: dict, kind: str | None = None) -> set[str]:
    return {n["label"] for n in body["nodes"] if kind is None or n["kind"] == kind}


def edges(body: dict) -> set[tuple[str, str, str]]:
    by_id = {n["id"]: n["label"] for n in body["nodes"]}
    return {(by_id[e["source"]], by_id[e["target"]], e["relation"]) for e in body["edges"]}


def test_the_graph_under_a_region(
    client: TestClient, db: Database, world: World, build: type[Build]
):
    picture = db.run(make_picture, db, world, build)

    response = client.get("/graph", params={"place_id": str(world.elm.id)})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["root_id"] == str(world.elm.id)
    assert body["truncated"] is False
    # Every kind, the rejected body and the platform domain left out.
    assert labels(body, "place") == {"Elm", "Oakville", "Milton"}
    assert labels(body, "institution") == {
        "County of Elm",
        "Town of Oakville",
        "Town of Milton",
        "Oakville Library",
    }
    assert labels(body, "homepage") == {
        "https://www.elmcounty.ca/",
        "https://sites.example/oakville-library/",
    }
    assert labels(body, "source") == {"https://www.elmcounty.ca/tenders"}
    assert labels(body, "domain") == {"elmcounty.ca"}
    assert edges(body) == {
        ("Oakville", "Elm", "parent"),
        ("Milton", "Elm", "parent"),
        ("Elm", "County of Elm", "government"),
        ("Oakville", "Town of Oakville", "government"),
        ("Milton", "Town of Milton", "government"),
        ("Oakville Library", "Oakville", "place"),
        ("Oakville Library", "Town of Oakville", "parent"),
        ("Oakville Library", "Milton", "serves"),
        ("https://www.elmcounty.ca/", "County of Elm", "homepage"),
        ("https://www.elmcounty.ca/", "elmcounty.ca", "domain"),
        ("https://sites.example/oakville-library/", "Oakville Library", "homepage"),
        ("https://www.elmcounty.ca/tenders", "County of Elm", "source"),
        ("https://www.elmcounty.ca/tenders", "elmcounty.ca", "domain"),
    }
    # What each node carries: the figures the sizes follow, and the kind's own detail.
    by_label = {n["label"]: n for n in body["nodes"]}
    assert by_label["Elm"]["administrative_level"] == "region"
    assert by_label["Elm"]["population"] is None
    assert by_label["County of Elm"]["source_count"] == 1
    assert by_label["County of Elm"]["institution_type"] == "regional_government"
    assert by_label["Oakville Library"]["status"] == "candidate"
    assert by_label["https://www.elmcounty.ca/tenders"]["source_type"] == "tender"
    assert by_label["elmcounty.ca"]["domain_kind"] == "official"
    # What an expansion would bring, and the coverage: the rejected body is not counted.
    assert (
        by_label["Elm"]
        | {"child_count": 2, "institution_count": 1, "governed": True, "online": True}
        == by_label["Elm"]
    )
    assert (
        by_label["Milton"]
        | {"child_count": 0, "institution_count": 1, "governed": True, "online": False}
        == by_label["Milton"]
    )
    assert (
        by_label["County of Elm"] | {"has_homepage": True, "homepage_count": 1}
        == by_label["County of Elm"]
    )
    assert (
        by_label["Oakville Library"] | {"has_homepage": False, "homepage_count": 1}
        == by_label["Oakville Library"]
    )
    assert (
        by_label["Town of Milton"] | {"has_homepage": False, "homepage_count": 0}
        == by_label["Town of Milton"]
    )
    assert by_label["elmcounty.ca"]["child_count"] is None
    # The breadcrumb: the places above the root, from the top.
    assert [a["label"] for a in body["ancestors"]] == ["Canada", "Ontario"]
    assert body["ancestors"][1]["id"] == str(world.ontario.id)

    # The platform domain, when asked for, with the claim's edge to it.
    with_platforms = client.get(
        "/graph", params={"place_id": str(world.elm.id), "platforms": "true"}
    ).json()
    assert labels(with_platforms, "domain") == {"elmcounty.ca", "sites.example"}
    assert ("https://sites.example/oakville-library/", "sites.example", "domain") in edges(
        with_platforms
    )
    assert str(picture.platform) in {n["id"] for n in with_platforms["nodes"]}


def test_the_default_root_is_the_country(
    client: TestClient, db: Database, world: World, build: type[Build]
):
    db.run(make_picture, db, world, build)

    body = client.get("/graph").json()
    assert body["root_id"] == str(next(n["id"] for n in body["nodes"] if n["label"] == "Canada"))
    assert {"Canada", "Ontario", "Elm", "Oakville", "Milton"} <= labels(body, "place")
    assert "Government of Ontario" in labels(body, "institution")
    assert body["ancestors"] == []
    assert client.get("/graph", params={"country_code": "CA"}).json()["root_id"] == body["root_id"]
    assert client.get("/graph", params={"country_code": "FR"}).status_code == 404
    assert client.get("/graph", params={"place_id": str(uuid.uuid4())}).status_code == 404


def test_filters_keep_the_root_and_narrow_the_rest(
    client: TestClient, db: Database, world: World, build: type[Build]
):
    picture = db.run(make_picture, db, world, build)
    root = {"place_id": str(world.elm.id)}

    # Kinds: only what is asked for, and no edges to what is not.
    places_only = client.get("/graph", params={**root, "kinds": ["place"]}).json()
    assert {n["kind"] for n in places_only["nodes"]} == {"place"}
    assert edges(places_only) == {("Oakville", "Elm", "parent"), ("Milton", "Elm", "parent")}
    two = client.get("/graph", params={**root, "kinds": ["place", "institution"]}).json()
    assert {n["kind"] for n in two["nodes"]} == {"place", "institution"}
    # The governments alone: the hierarchy, as the cap's fallback draws it.
    hierarchy = client.get("/graph", params={**root, "governments": "true"}).json()
    assert labels(hierarchy, "institution") == {
        "County of Elm",
        "Town of Oakville",
        "Town of Milton",
    }
    assert labels(hierarchy, "homepage") == {"https://www.elmcounty.ca/"}
    # Domains alone still hang off the institutions' web, which is walked but not drawn.
    domains_only = client.get("/graph", params={**root, "kinds": ["domain"]}).json()
    assert labels(domains_only) == {"elmcounty.ca"}

    # The level: places at it and the institutions in them, plus the root.
    municipal = client.get("/graph", params={**root, "administrative_level": "municipality"})
    assert labels(municipal.json(), "place") == {"Elm", "Oakville", "Milton"}
    assert labels(municipal.json(), "institution") == {
        "Town of Oakville",
        "Town of Milton",
        "Oakville Library",
    }
    regional = client.get("/graph", params={**root, "administrative_level": "region"}).json()
    assert labels(regional, "place") == {"Elm"}
    assert labels(regional, "institution") == {"County of Elm"}

    # The type.
    libraries = client.get("/graph", params={**root, "institution_type": "library"}).json()
    assert labels(libraries, "institution") == {"Oakville Library"}
    assert labels(libraries, "homepage") == {"https://sites.example/oakville-library/"}
    assert labels(libraries, "source") == set()

    # The status, on every kind; rejected only when asked for.
    verified = client.get("/graph", params={**root, "status": "verified"}).json()
    assert "Oakville Library" not in labels(verified)
    assert "https://sites.example/oakville-library/" not in labels(verified)
    assert labels(verified, "domain") == {"elmcounty.ca"}
    rejected = client.get("/graph", params={**root, "status": "rejected"}).json()
    assert labels(rejected) == {"Elm", "Milton Arena Board"}
    assert str(picture.rejected) in {n["id"] for n in rejected["nodes"]}


def test_a_big_picture_is_cut_down_to_places_and_governments(
    client: TestClient,
    db: Database,
    world: World,
    build: type[Build],
    monkeypatch: pytest.MonkeyPatch,
):
    picture = db.run(make_picture, db, world, build)

    # Three places, four institutions: the web takes it over a cap of eight.
    monkeypatch.setattr(subgraph, "MAX_NODES", 8)
    body = client.get("/graph", params={"place_id": str(world.elm.id)}).json()
    assert body["truncated"] is True
    assert labels(body) == {
        "Elm",
        "Oakville",
        "Milton",
        "County of Elm",
        "Town of Oakville",
        "Town of Milton",
    }
    assert str(picture.milton_government) in {n["id"] for n in body["nodes"]}
    assert ("Milton", "Town of Milton", "government") in edges(body)
    # Over the cap before the web is even read.
    monkeypatch.setattr(subgraph, "MAX_NODES", 4)
    body = client.get("/graph", params={"place_id": str(world.elm.id)}).json()
    assert body["truncated"] is True
    assert labels(body, "institution") == {"County of Elm", "Town of Oakville", "Town of Milton"}
    # A small place on its own fits.
    body = client.get("/graph", params={"place_id": str(picture.milton)}).json()
    assert body["truncated"] is False
    assert labels(body) == {"Milton", "Town of Milton"}
