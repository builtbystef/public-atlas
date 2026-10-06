"""The review queue: raising folds into one item per entity and gives it a kind; every
decision runs the status change the rules run and says what to spawn; kinds are decided
together; and an edit of the country tables settles the type questions it answers."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.evidence.models import EvidenceKind
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import (
    Alias,
    Domain,
    EnteredBy,
    EntityStatus,
    Homepage,
    Institution,
)
from public_atlas.modules.review import service as review
from public_atlas.modules.review.models import ReviewItem

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from tests.integration.conftest import Database
    from tests.integration.modules.conftest import Build, World

    from public_atlas.integrations.storage.memory import MemoryObjectStore

AGENT = EnteredBy.AGENT


def test_raising_folds_into_one_item_per_entity_and_gives_it_the_rules_kind(
    db: Database, world: World, build: type[Build]
):
    async def scenario() -> tuple[ReviewItem, ReviewItem, Institution, ReviewItem, Institution]:
        async with db.session() as session:
            library = await build.candidate_institution(session, world.elm, "Elm Library")
            first = await review.raise_review(
                session,
                library,
                rule=review.Rule.NAME_PATTERN,
                reason="odd name",
                question={"institution_type": "library"},
            )
            second = await review.raise_review(
                session,
                library,
                rule=review.Rule.TYPE_LEVEL,
                reason="a library under a region",
                question={"institution_type": "library", "level": "region"},
            )
            again = await review.raise_review(
                session, library, rule=review.Rule.TYPE_LEVEL, reason="a library under a region"
            )
            assert again.id is first.id
            town = await session.get_one(Institution, world.town.id)
            on_verified = await review.raise_review(
                session, town, rule=review.Rule.AGENT, reason="is this still the town?"
            )
            await session.commit()
            return first, second, library, on_verified, town

    first, second, library, on_verified, town = db.run(scenario)
    assert first.id == second.id
    assert first.question == {
        "reasons": ["odd name", "a library under a region"],
        "institution_type": "library",
        "level": "region",
    }
    assert (first.rule, first.kind) == (review.Rule.TYPE_LEVEL, "type_level:library@region")
    assert library.status is EntityStatus.NEEDS_REVIEW
    # A verified entity keeps its status while the question is open.
    assert (on_verified.kind, town.status) == (None, EntityStatus.VERIFIED)


def test_approving_a_domain_trusts_it_and_verifies_the_homepage_in_question(
    client: TestClient, db: Database, world: World, build: type[Build]
):
    async def make() -> tuple[ReviewItem, Homepage, Homepage, Domain]:
        async with db.session() as session:
            town = await session.get_one(Institution, world.town.id)
            library = await build.candidate_institution(session, world.oakville, "Oakville Library")
            towns = await build.claim(session, town, "https://www.oakville.example/")
            librarys = await build.claim(session, library, "https://www.oakville.example/library")
            domain = await graph.domain_of_host(session, "www.oakville.example")
            assert domain is not None
            item = await review.raise_review(
                session,
                domain,
                rule=review.Rule.DOMAIN_CHECKS,
                reason="no trusted page links to it",
                question={"homepage_id": str(towns.id)},
            )
            await session.commit()
            return item, towns, librarys, domain

    item, towns, librarys, domain = db.run(make)
    listed = client.get("/review-items").json()
    assert [row["id"] for row in listed] == [str(item.id)]
    assert client.get("/review-items", params={"status": "approved"}).json() == []

    approved = client.post(f"/review-items/{item.id}/approve", json={"note": "it is the town"})
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["review_item"]["status"] == "approved"
    assert body["review_item"]["note"] == "it is the town"
    assert body["spawn"] == [
        {"type": "find_sources", "subject_id": str(world.town.id)},
        {"type": "find_institutions", "subject_id": str(world.oakville.id)},
    ]
    assert client.post(f"/review-items/{item.id}/approve", json={}).status_code == 409

    async def check() -> tuple[Domain, Homepage, Homepage, Institution]:
        async with db.session() as session:
            return (
                await session.get_one(Domain, domain.id),
                await session.get_one(Homepage, towns.id),
                await session.get_one(Homepage, librarys.id),
                await session.get_one(Institution, world.town.id),
            )

    domain, towns, librarys, town = db.run(check)
    assert (domain.status, domain.entered_by) == (EntityStatus.VERIFIED, EnteredBy.MANUAL)
    assert graph.is_trusted(domain)
    assert (towns.status, town.homepage_id) == (EntityStatus.VERIFIED, towns.id)
    # The library's claim is another question; its own assignment finds the domain trusted.
    assert librarys.status is EntityStatus.CANDIDATE


def test_rejecting_a_domain_sends_the_claimant_looking_again(
    client: TestClient, db: Database, world: World, build: type[Build]
):
    async def make() -> tuple[ReviewItem, Homepage]:
        async with db.session() as session:
            town = await session.get_one(Institution, world.town.id)
            towns = await build.claim(session, town, "https://www.oakville.example/")
            domain = await graph.domain_of_host(session, "www.oakville.example")
            assert domain is not None
            item = await review.raise_review(
                session, domain, rule=review.Rule.DOMAIN_CHECKS, reason="looks like a reseller"
            )
            await session.commit()
            return item, towns

    item, towns = db.run(make)
    rejected = client.post(f"/review-items/{item.id}/reject", json={"note": "a parked page"})
    assert rejected.status_code == 200, rejected.text
    body = rejected.json()
    assert body["review_item"]["status"] == "rejected"
    assert body["spawn"] == [{"type": "find_homepage", "subject_id": str(world.town.id)}]

    async def check() -> Homepage:
        async with db.session() as session:
            return await session.get_one(Homepage, towns.id)

    towns = db.run(check)
    assert (towns.status, towns.rejected_reason) == (EntityStatus.REJECTED, "a parked page")


def test_approving_an_institution_may_give_it_its_type_and_rejecting_one_closes_it(
    client: TestClient, db: Database, world: World, build: type[Build]
):
    async def make() -> tuple[ReviewItem, ReviewItem, uuid.UUID, uuid.UUID]:
        async with db.session() as session:
            housing = await build.candidate_institution(
                session, world.oakville, "Oakville Housing", "other", suggested_type="Housing Corp"
            )
            typed = await review.raise_review(
                session,
                housing,
                rule=review.Rule.NEW_TYPE,
                reason="no type fits",
                question={"suggested_type": "Housing Corp", "level": "municipality"},
            )
            club = await build.candidate_institution(
                session, world.oakville, "Oakville Curling Club"
            )
            wrong = await review.raise_review(
                session, club, rule=review.Rule.AGENT, reason="is a club public?"
            )
            await session.commit()
            return typed, wrong, housing.id, club.id

    typed, wrong, housing_id, club_id = db.run(make)
    unknown = client.post(
        f"/review-items/{typed.id}/approve", json={"institution_type": "housing_corp"}
    )
    assert unknown.status_code == 422
    assert "housing_corp" in unknown.json()["detail"]
    approved = client.post(
        f"/review-items/{typed.id}/approve", json={"institution_type": "municipal_corporation"}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["spawn"] == [{"type": "find_homepage", "subject_id": str(housing_id)}]
    rejected = client.post(f"/review-items/{wrong.id}/reject", json={"note": "private"})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["spawn"] == []
    assert client.post(f"/review-items/{uuid.uuid7()}/reject", json={}).status_code == 404

    async def check() -> tuple[Institution, Institution]:
        async with db.session() as session:
            return (
                await session.get_one(Institution, housing_id),
                await session.get_one(Institution, club_id),
            )

    housing, club = db.run(check)
    assert (housing.institution_type, housing.suggested_type, housing.status) == (
        "municipal_corporation",
        None,
        EntityStatus.VERIFIED,
    )
    assert housing.entered_by is EnteredBy.MANUAL
    assert club.status is EntityStatus.REJECTED


def test_merging_through_the_api_closes_the_item_and_remembers_where_the_entity_went(
    client: TestClient, db: Database, world: World, build: type[Build]
):
    async def make() -> tuple[ReviewItem, ReviewItem, uuid.UUID, uuid.UUID]:
        async with db.session() as session:
            kept = await build.candidate_institution(
                session, world.oakville, "Oakville Public Library"
            )
            await status_changes.verify_institution(session, kept, entered_by=AGENT)
            duplicate = await build.candidate_institution(
                session, world.oakville, "Oakville Library"
            )
            item = await review.raise_review(
                session,
                duplicate,
                rule=review.Rule.DUPLICATE,
                reason="possible duplicate",
                question={"duplicate_of": [str(kept.id)]},
            )
            domain_item = await review.raise_review(
                session,
                await session.get_one(Domain, world.elm_domain.id),
                rule=review.Rule.AGENT,
                reason="a domain",
            )
            await session.commit()
            return item, domain_item, kept.id, duplicate.id

    item, domain_item, kept_id, duplicate_id = db.run(make)
    missing = client.post(f"/review-items/{item.id}/merge", json={"into_id": str(uuid.uuid7())})
    assert missing.status_code == 404
    not_mergeable = client.post(
        f"/review-items/{domain_item.id}/merge", json={"into_id": str(kept_id)}
    )
    assert not_mergeable.status_code == 422
    merged = client.post(f"/review-items/{item.id}/merge", json={"into_id": str(kept_id)})
    assert merged.status_code == 200, merged.text
    body = merged.json()["review_item"]
    assert body["status"] == "merged"
    assert body["question"]["merged_into_id"] == str(kept_id)

    async def check() -> tuple[Institution, list[str]]:
        async with db.session() as session:
            aliases = sorted(
                await session.scalars(select(Alias.text).where(Alias.institution_id == kept_id))
            )
            return await session.get_one(Institution, duplicate_id), aliases

    duplicate, aliases = db.run(check)
    assert duplicate.status is EntityStatus.REJECTED
    assert aliases == ["Oakville Library", "Oakville Public Library"]
    assert client.get("/review-items").json()[0]["id"] == str(domain_item.id)


def test_a_kind_is_decided_once_for_every_item_of_it(
    client: TestClient, db: Database, world: World, build: type[Build]
):
    async def make() -> dict[str, uuid.UUID]:
        bodies: dict[str, uuid.UUID] = {}
        async with db.session() as session:
            there = await build.verified_place(session, "There", "region", world.ontario)
            for region, library_name, housing_name in (
                (world.elm, "Elm Public Library", "Elm Housing Corporation"),
                (there, "There Public Library", "There Housing Corporation"),
            ):
                library = await build.candidate_institution(session, region, library_name)
                await review.raise_review(
                    session,
                    library,
                    rule=review.Rule.TYPE_LEVEL,
                    reason="a library under a region",
                    question={"institution_type": "library", "level": "region"},
                )
                housing = await build.candidate_institution(
                    session, region, housing_name, "other", suggested_type="Housing Corporation"
                )
                await review.raise_review(
                    session,
                    housing,
                    rule=review.Rule.NEW_TYPE,
                    reason="no type fits",
                    question={"suggested_type": "Housing Corporation", "level": "region"},
                )
                bodies[library_name] = library.id
                bodies[housing_name] = housing.id
            port = await build.candidate_institution(
                session, there, "There Port Authority", "other", suggested_type="port authority"
            )
            await review.raise_review(
                session,
                port,
                rule=review.Rule.NEW_TYPE,
                reason="no type",
                question={"suggested_type": "port authority", "level": "region"},
            )
            bodies["There Port Authority"] = port.id
            await session.commit()
        return bodies

    bodies = db.run(make)
    kinds = client.get("/review-items/kinds")
    assert kinds.status_code == 200, kinds.text
    assert [(k["kind"], k["count"], k["names"], k["question"]) for k in kinds.json()] == [
        (
            "new_type:housing_corporation",
            2,
            ["Elm Housing Corporation", "There Housing Corporation"],
            {"suggested_type": "Housing Corporation", "level": "region"},
        ),
        (
            "type_level:library@region",
            2,
            ["Elm Public Library", "There Public Library"],
            {"institution_type": "library", "level": "region"},
        ),
        (
            "new_type:port_authority",
            1,
            ["There Port Authority"],
            {"suggested_type": "port authority", "level": "region"},
        ),
    ]

    libraries = client.post(
        "/review-items/kinds/approve",
        json={"kind": "type_level:library@region", "note": "a county library"},
    )
    assert libraries.status_code == 200, libraries.text
    body = libraries.json()
    assert [item["status"] for item in body["review_items"]] == ["approved", "approved"]
    assert [s["type"] for s in body["spawn"]] == ["find_homepage", "find_homepage"]

    # The type must exist before bodies can be given it.
    no_type = client.post(
        "/review-items/kinds/approve", json={"kind": "new_type:housing_corporation"}
    )
    assert no_type.status_code == 422
    assert (
        client.put(
            "/institution-types/housing_corporation",
            json={"name": "housing_corporation", "description": "Community housing"},
        ).status_code
        == 200
    )
    housing = client.post(
        "/review-items/kinds/approve", json={"kind": "new_type:housing_corporation"}
    )
    assert housing.status_code == 200, housing.text
    wrong_kind = client.post(
        "/review-items/kinds/approve",
        json={"kind": "new_type:port_authority", "institution_type": "Port"},
    )
    assert wrong_kind.status_code == 422
    ports = client.post(
        "/review-items/kinds/reject", json={"kind": "new_type:port_authority", "note": "federal"}
    )
    assert ports.status_code == 200, ports.text
    assert ports.json()["review_items"][0]["status"] == "rejected"
    gone = client.post("/review-items/kinds/reject", json={"kind": "new_type:port_authority"})
    assert gone.status_code == 404
    assert client.get("/review-items/kinds").json() == []

    async def check() -> dict[str, tuple[str, EntityStatus]]:
        async with db.session() as session:
            found = {}
            for name, body_id in bodies.items():
                row = await session.get_one(Institution, body_id)
                found[name] = (row.institution_type, row.status)
            return found

    assert db.run(check) == {
        "Elm Public Library": ("library", EntityStatus.VERIFIED),
        "There Public Library": ("library", EntityStatus.VERIFIED),
        "Elm Housing Corporation": ("housing_corporation", EntityStatus.VERIFIED),
        "There Housing Corporation": ("housing_corporation", EntityStatus.VERIFIED),
        "There Port Authority": ("other", EntityStatus.REJECTED),
    }


def test_an_edit_of_the_country_tables_settles_the_type_items_it_answers(
    client: TestClient, db: Database, world: World, build: type[Build]
):
    async def make() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
        async with db.session() as session:
            library = await build.candidate_institution(session, world.elm, "Elm Public Library")
            await review.raise_review(
                session,
                library,
                rule=review.Rule.TYPE_LEVEL,
                reason="a library under a region",
                question={"institution_type": "library", "level": "region"},
            )
            housing = await build.candidate_institution(
                session, world.elm, "Elm Housing", "other", suggested_type="Housing Corporation"
            )
            await review.raise_review(
                session,
                housing,
                rule=review.Rule.NEW_TYPE,
                reason="no type fits",
                question={"suggested_type": "Housing Corporation", "level": "region"},
            )
            zoo = await build.candidate_institution(
                session, world.elm, "Elm Zoo", "other", suggested_type="zoo"
            )
            await review.raise_review(
                session,
                zoo,
                rule=review.Rule.NEW_TYPE,
                reason="no type fits",
                question={"suggested_type": "zoo", "level": "region"},
            )
            await session.commit()
            return library.id, housing.id, zoo.id

    library_id, housing_id, zoo_id = db.run(make)
    region = client.get("/countries/CA").json()["administrative_levels"][2]
    assert region["name"] == "region"
    region["expected_institution_types"].append("library")
    assert client.put("/countries/CA/administrative-levels/region", json=region).status_code == 200
    assert (
        client.put(
            "/institution-types/housing_corporation",
            json={"name": "housing_corporation", "description": "Community housing"},
        ).status_code
        == 200
    )
    use = {"institution_type": "housing_corporation", "expected_source_types": ["procurement"]}
    assert (
        client.put("/countries/CA/institution-types/housing_corporation", json=use).status_code
        == 200
    )

    async def check() -> tuple[Institution, Institution, Institution, list[tuple[str, str | None]]]:
        async with db.session() as session:
            items = [
                (row.status.value, row.note)
                for row in await session.scalars(select(ReviewItem).order_by(ReviewItem.id))
            ]
            return (
                await session.get_one(Institution, library_id),
                await session.get_one(Institution, housing_id),
                await session.get_one(Institution, zoo_id),
                items,
            )

    library, housing, zoo, items = db.run(check)
    assert library.status is EntityStatus.VERIFIED
    assert (housing.status, housing.institution_type) == (
        EntityStatus.VERIFIED,
        "housing_corporation",
    )
    assert (zoo.status, zoo.institution_type) == (EntityStatus.NEEDS_REVIEW, "other")
    assert items == [
        ("approved", "settled: level region now expects library"),
        ("approved", "settled: Canada now uses housing_corporation"),
        ("open", None),
    ]
    assert client.get("/review-items", params={"kind": "new_type:zoo"}).json()[0]["kind"] == (
        "new_type:zoo"
    )


def test_reading_an_item_shows_the_entity_and_its_quotes_with_links_to_the_stored_pages(
    client: TestClient,
    db: Database,
    object_store: MemoryObjectStore,
    world: World,
    build: type[Build],
):
    async def make() -> uuid.UUID:
        async with db.session() as session:
            library = await build.candidate_institution(session, world.oakville, "Oakville Library")
            await graph.add_alias(
                session, library, "OPL", language="en", entered_by=AGENT, is_acronym=True
            )
            _, snapshot = await build.capture(
                session,
                object_store,
                "https://www.elmcounty.ca/libraries",
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
            item = await review.raise_review(
                session, library, rule=review.Rule.AGENT, reason="a branch or a body?"
            )
            await session.commit()
            return item.id

    item_id = db.run(make)
    detail = client.get(f"/review-items/{item_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["entity_kind"] == "institution"
    assert body["entity_status"] == "needs_review"
    assert body["label"] == "Oakville Library"
    assert body["names"] == ["Oakville Library", "OPL"]
    assert body["entity"]["institution_type"] == "library"
    assert body["entity"]["place_id"] == str(world.oakville.id)
    assert body["question"] == {"reasons": ["a branch or a body?"]}
    (quote,) = body["evidence"]
    assert quote["quote"] == "Oakville Library, 120 Navy Street"
    assert quote["page_url"] == "https://www.elmcounty.ca/libraries"
    assert quote["snapshot_url"].startswith("memory://snapshots/")
    assert client.get(f"/review-items/{uuid.uuid7()}").status_code == 404
