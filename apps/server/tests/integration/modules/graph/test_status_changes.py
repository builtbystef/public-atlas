"""Every status change goes through `status_changes.py`: each one sets the status once, records
who did it, keeps the links the tables enforce, and says what to spawn."""

import logging
import re
import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.assignments.models import Assignment, AssignmentStatus, AssignmentType
from public_atlas.modules.assignments.service import Spawn
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.evidence.models import Evidence, EvidenceKind
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
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
    Source,
)
from public_atlas.shared.exceptions import ConflictError, UnprocessableError

if TYPE_CHECKING:
    from tests.integration.conftest import Database
    from tests.integration.modules.conftest import Build, World

    from public_atlas.integrations.storage.memory import MemoryObjectStore

AGENT = EnteredBy.AGENT
MANUAL = EnteredBy.MANUAL


def test_an_entity_starts_a_candidate_and_only_an_official_domain_is_trusted(
    db: Database, world: World, build: type[Build]
):
    async def scenario() -> tuple[Domain, Domain, Domain]:
        async with db.session() as session:
            official = await graph.create_domain(
                session, "oakville.example", kind=DomainKind.OFFICIAL, entered_by=AGENT
            )
            before = (official.status, official.entered_by, graph.is_trusted(official))
            assert before == (EntityStatus.CANDIDATE, AGENT, False)
            assert await status_changes.verify_domain(session, official, entered_by=MANUAL) == []
            platform = await graph.create_domain(
                session, "sites.example", kind=DomainKind.PLATFORM, entered_by=MANUAL
            )
            await status_changes.verify_domain(session, platform, entered_by=MANUAL)
            await session.commit()
            return official, platform, await session.get_one(Domain, world.elm_domain.id)

    official, platform, elm = db.run(scenario)
    # Who verified it is recorded; a second verification changes nothing.
    assert (official.status, official.entered_by) == (EntityStatus.VERIFIED, MANUAL)
    assert graph.is_trusted(official)
    assert platform.status is EntityStatus.VERIFIED
    assert not graph.is_trusted(platform)
    assert graph.is_trusted(elm)


def test_verifying_a_homepage_links_it_supersedes_other_claims_and_spawns(
    db: Database, world: World, build: type[Build]
):
    async def scenario() -> tuple[
        Homepage, Homepage, Institution, Institution, list[Spawn], list[Spawn]
    ]:
        async with db.session() as session:
            town = await session.get_one(Institution, world.town.id)
            first = await build.claim(session, town, "https://www.elmcounty.ca/oakville/")
            second = await build.claim(session, town, "https://www.elmcounty.ca/towns/oakville")
            spawn = await status_changes.verify_homepage(session, first, entered_by=AGENT)
            assert await status_changes.verify_homepage(session, first, entered_by=MANUAL) == []
            library = await build.candidate_institution(session, world.oakville, "Oakville Library")
            page = await build.claim(session, library, "https://www.elmcounty.ca/library/")
            library_spawn = await status_changes.verify_homepage(session, page, entered_by=AGENT)
            await session.commit()
            return first, second, town, library, spawn, library_spawn

    first, second, town, library, spawn, library_spawn = db.run(scenario)
    assert (first.status, first.entered_by, first.trusted_path) == (
        EntityStatus.VERIFIED,
        AGENT,
        None,
    )
    assert town.homepage_id == first.id
    assert (second.status, second.rejected_reason) == (
        EntityStatus.REJECTED,
        status_changes.SUPERSEDED,
    )
    # A government's place gets its institutions looked for; any institution its sources.
    assert spawn == [
        Spawn(AssignmentType.FIND_SOURCES, town.id),
        Spawn(AssignmentType.FIND_INSTITUTIONS, world.oakville.id),
    ]
    assert library_spawn == [Spawn(AssignmentType.FIND_SOURCES, library.id)]


def test_a_homepage_is_refused_off_a_trusted_domain_or_when_the_page_is_taken(
    db: Database, world: World, build: type[Build]
):
    async def scenario() -> tuple[list[tuple[EntityStatus, str | None]], bool]:
        async with db.session() as session:
            town = await session.get_one(Institution, world.town.id)
            untrusted = await build.claim(session, town, "https://www.oakville.example/")
            with pytest.raises(UnprocessableError, match="not trusted"):
                await status_changes.verify_homepage(session, untrusted, entered_by=AGENT)
            taken = await build.claim(session, town, "https://www.elmcounty.ca/")
            with pytest.raises(ConflictError, match="verified homepage of 'County of Elm'"):
                await status_changes.verify_homepage(session, taken, entered_by=AGENT)
            first = await build.claim(session, town, "https://www.elmcounty.ca/oakville/")
            await status_changes.verify_homepage(session, first, entered_by=AGENT)
            another = await build.claim(session, town, "https://www.elmcounty.ca/oakville-too/")
            with pytest.raises(ConflictError, match="has a verified homepage already"):
                await status_changes.verify_homepage(session, another, entered_by=AGENT)
            await session.commit()
            refused = [
                (claim.status, claim.rejected_reason) for claim in (untrusted, taken, another)
            ]
            return refused, town.homepage_id == first.id

    # A refused claim is left a candidate until a homepage is verified, which supersedes the
    # claims before it; the one made after stays a candidate; the town keeps the verified one.
    assert db.run(scenario) == (
        [
            (EntityStatus.REJECTED, status_changes.SUPERSEDED),
            (EntityStatus.REJECTED, status_changes.SUPERSEDED),
            (EntityStatus.CANDIDATE, None),
        ],
        True,
    )


def test_a_homepage_on_a_platform_gets_a_trusted_path(
    db: Database, world: World, build: type[Build]
):
    async def scenario() -> tuple[Homepage, Homepage]:
        async with db.session() as session:
            town = await session.get_one(Institution, world.town.id)
            channel = await build.claim(
                session, town, "https://www.youtube.com/@TownOfOakville/videos"
            )
            root = await build.claim(session, town, "https://www.youtube.com/")
            with pytest.raises(UnprocessableError, match="root"):
                await status_changes.verify_homepage(session, root, entered_by=MANUAL)
            await status_changes.verify_homepage(session, channel, entered_by=MANUAL)
            await session.commit()
            return channel, root

    channel, root = db.run(scenario)
    assert channel.status is EntityStatus.VERIFIED
    assert channel.trusted_path == "https://www.youtube.com/@TownOfOakville/videos/"
    assert graph.under_trusted_path(
        "https://www.youtube.com/@TownOfOakville/videos", channel.trusted_path
    )
    # The institution's other open claim is superseded.
    assert (root.status, root.rejected_reason) == (EntityStatus.REJECTED, status_changes.SUPERSEDED)


def test_rejecting_a_domain_rejects_its_claims_and_sends_the_claimants_looking_again(
    db: Database, world: World, build: type[Build]
):
    async def scenario() -> tuple[Domain, list[Homepage], list[Spawn]]:
        async with db.session() as session:
            town = await session.get_one(Institution, world.town.id)
            library = await build.candidate_institution(session, world.oakville, "Oakville Library")
            first = await build.claim(session, town, "https://www.oakville.example/")
            domain = await graph.domain_of_host(session, "www.oakville.example")
            assert domain is not None
            # A page captured before the domain had a row: found by its host.
            early = await graph.ensure_webpage(session, "https://en.oakville.example/library")
            early.domain_id = None
            second = await graph.create_homepage(session, library, early, entered_by=AGENT)
            spawn = await status_changes.reject_domain(
                session, domain, entered_by=MANUAL, reason="a parked page"
            )
            await session.commit()
            return domain, [first, second], spawn

    domain, claims, spawn = db.run(scenario)
    assert (domain.status, domain.entered_by) == (EntityStatus.REJECTED, MANUAL)
    for homepage in claims:
        assert (homepage.status, homepage.rejected_reason) == (
            EntityStatus.REJECTED,
            "a parked page",
        )
    assert {(s.type, s.subject_id) for s in spawn} == {
        (AssignmentType.FIND_HOMEPAGE, claims[0].institution_id),
        (AssignmentType.FIND_HOMEPAGE, claims[1].institution_id),
    }


def test_verifying_and_rejecting_an_institution(db: Database, world: World, build: type[Build]):
    async def scenario() -> tuple[list[Spawn], list[Spawn], Institution, Institution, Homepage]:
        async with db.session() as session:
            library = await build.candidate_institution(session, world.oakville, "Oakville Library")
            spawn = await status_changes.verify_institution(session, library, entered_by=AGENT)
            page = await build.claim(session, library, "https://www.elmcounty.ca/library/")
            await status_changes.verify_homepage(session, page, entered_by=AGENT)
            none = await status_changes.verify_institution(session, library, entered_by=MANUAL)
            archive = await build.candidate_institution(session, world.oakville, "Oakville Archive")
            archive_claim = await build.claim(session, archive, "https://www.archive.example/")
            await status_changes.reject_institution(session, archive, entered_by=MANUAL)
            town = await session.get_one(Institution, world.town.id)
            with pytest.raises(ConflictError, match="government"):
                await status_changes.reject_institution(session, town, entered_by=MANUAL)
            await session.commit()
            return spawn, none, library, archive, archive_claim

    spawn, none, library, archive, archive_claim = db.run(scenario)
    assert spawn == [Spawn(AssignmentType.FIND_HOMEPAGE, library.id)]
    assert none == []
    assert (archive.status, archive.entered_by) == (EntityStatus.REJECTED, MANUAL)
    assert (archive_claim.status, archive_claim.rejected_reason) == (
        EntityStatus.REJECTED,
        status_changes.INSTITUTION_REJECTED,
    )


def test_sending_to_review_moves_only_a_candidate(db: Database, world: World, build: type[Build]):
    async def scenario() -> tuple[bool, EntityStatus, bool, EntityStatus]:
        async with db.session() as session:
            library = await build.candidate_institution(session, world.oakville, "Oakville Library")
            moved = await status_changes.send_to_review(session, library)
            town = await session.get_one(Institution, world.town.id)
            kept = await status_changes.send_to_review(session, town)
            await session.commit()
            return moved, library.status, kept, town.status

    assert db.run(scenario) == (True, EntityStatus.NEEDS_REVIEW, False, EntityStatus.VERIFIED)


def test_merging_institutions_moves_what_the_survivor_lacks_and_keeps_its_own(  # noqa: PLR0915
    db: Database, object_store: MemoryObjectStore, world: World, build: type[Build]
):
    async def scenario() -> dict[str, Any]:
        async with db.session() as session:
            kept = await build.candidate_institution(
                session, world.oakville, "Oakville Public Library"
            )
            await status_changes.verify_institution(session, kept, entered_by=AGENT)
            duplicate = await build.candidate_institution(
                session, world.oakville, "Oakville Library"
            )
            await graph.add_alias(session, duplicate, "OPL", language="en", entered_by=AGENT)
            await graph.add_alias(session, kept, "OPL", language="en", entered_by=AGENT)
            _, snapshot = await build.capture(
                session,
                object_store,
                "https://www.elmcounty.ca/libraries",
                "<html><body>Oakville Public Library serves Oakville</body></html>",
                "Oakville Public Library serves Oakville",
            )
            for entity in (kept, duplicate):
                await evidence.add_evidence(
                    session,
                    entity_id=entity.id,
                    snapshot=snapshot,
                    kind=EvidenceKind.APPEARS_ON,
                    quote="Oakville Public Library serves Oakville",
                    entered_by=AGENT,
                )
            await evidence.add_evidence(
                session,
                entity_id=duplicate.id,
                snapshot=snapshot,
                kind=EvidenceKind.APPEARS_ON,
                quote="serves Oakville",
                entered_by=AGENT,
            )
            session.add_all(
                [
                    Identifier(
                        institution_id=duplicate.id, scheme=IdentifierScheme.STATCAN_SGC, value="9"
                    ),
                    Metric(
                        institution_id=duplicate.id, name=MetricName.POPULATION, year=2021, value=5
                    ),
                    Metric(institution_id=kept.id, name=MetricName.POPULATION, year=2021, value=7),
                    InstitutionServedPlace(institution_id=duplicate.id, place_id=world.elm.id),
                    InstitutionServedPlace(institution_id=kept.id, place_id=world.elm.id),
                    InstitutionServedPlace(institution_id=duplicate.id, place_id=world.ontario.id),
                ]
            )
            child = await graph.create_institution(
                session,
                name="Friends of the Library",
                institution_type="other",
                place=world.oakville,
                entered_by=AGENT,
                parent=duplicate,
            )
            budget = await graph.ensure_webpage(session, "https://www.elmcounty.ca/library/budget")
            tenders = await graph.ensure_webpage(session, "https://www.elmcounty.ca/library/bids")
            shared_source = await graph.create_source(
                session, duplicate, budget, source_type="budget", entered_by=AGENT
            )
            kept_source = await graph.create_source(
                session, kept, budget, source_type="budget", entered_by=AGENT
            )
            moved_source = await graph.create_source(
                session, duplicate, tenders, source_type="tender", entered_by=AGENT
            )
            await evidence.add_evidence(
                session,
                entity_id=shared_source.id,
                snapshot=snapshot,
                kind=EvidenceKind.APPEARS_ON,
                quote="Oakville Public Library serves Oakville",
                entered_by=AGENT,
            )
            homepage = await build.claim(session, duplicate, "https://www.elmcounty.ca/library/")
            await status_changes.verify_homepage(session, homepage, entered_by=AGENT)
            pending = await build.claim(session, kept, "https://www.elmcounty.ca/opl/")
            moved_work = await build.open_assignment(
                session, world.run, AssignmentType.FIND_HOMEPAGE, duplicate.id
            )
            cancelled_work = await build.open_assignment(
                session, world.run, AssignmentType.FIND_SOURCES, duplicate.id
            )
            await build.open_assignment(session, world.run, AssignmentType.FIND_SOURCES, kept.id)

            await status_changes.merge_entities(session, duplicate, kept, entered_by=MANUAL)
            await session.commit()

            aliases = sorted(
                await session.scalars(select(Alias.text).where(Alias.institution_id == kept.id))
            )
            left = list(
                await session.scalars(select(Alias).where(Alias.institution_id == duplicate.id))
            )
            quotes = sorted(
                await session.scalars(select(Evidence.quote).where(Evidence.entity_id == kept.id))
            )
            identifier = (
                await session.execute(select(Identifier).where(Identifier.value == "9"))
            ).scalar_one()
            metrics = list(
                await session.scalars(select(Metric).where(Metric.institution_id == kept.id))
            )
            served = sorted(
                await session.scalars(
                    select(InstitutionServedPlace.place_id).where(
                        InstitutionServedPlace.institution_id == kept.id
                    )
                )
            )
            source_rows = {row.id: row for row in await session.scalars(select(Source))}
            source_quotes = list(
                await session.scalars(
                    select(Evidence.quote).where(Evidence.entity_id == kept_source.id)
                )
            )
            work = {
                row.id: (row.subject_id, row.status)
                for row in await session.scalars(select(Assignment))
            }
            return {
                "aliases": aliases,
                "left": left,
                "quotes": quotes,
                "identifier_owner": identifier.institution_id,
                "metrics": [(m.year, int(m.value)) for m in metrics],
                "served": served,
                "child_parent": (
                    await session.get_one(Institution, child.id)
                ).parent_institution_id,
                "sources": {
                    "shared": (
                        source_rows[shared_source.id].institution_id,
                        source_rows[shared_source.id].status,
                    ),
                    "kept": source_rows[kept_source.id].institution_id,
                    "moved": source_rows[moved_source.id].institution_id,
                },
                "source_quotes": source_quotes,
                "kept": await session.get_one(Institution, kept.id),
                "duplicate": await session.get_one(Institution, duplicate.id),
                "homepage": await session.get_one(Homepage, homepage.id),
                "pending": await session.get_one(Homepage, pending.id),
                "work": (work[moved_work.id], work[cancelled_work.id]),
                "ids": (kept.id, duplicate.id),
            }

    out = db.run(scenario)
    kept_id, duplicate_id = out["ids"]
    assert out["aliases"] == ["OPL", "Oakville Library", "Oakville Public Library"]
    assert out["left"] == []
    assert out["quotes"] == ["Oakville Public Library serves Oakville", "serves Oakville"]
    assert out["identifier_owner"] == kept_id
    # The survivor's figure for the year stays; the duplicate's is left behind.
    assert out["metrics"] == [(2021, 7)]
    assert out["served"] == sorted([world.elm.id, world.ontario.id])
    assert out["child_parent"] == kept_id
    assert out["sources"] == {
        "shared": (duplicate_id, EntityStatus.REJECTED),
        "kept": kept_id,
        "moved": kept_id,
    }
    assert out["source_quotes"] == ["Oakville Public Library serves Oakville"]
    kept, duplicate = out["kept"], out["duplicate"]
    homepage, pending = out["homepage"], out["pending"]
    assert (duplicate.status, duplicate.entered_by, duplicate.homepage_id) == (
        EntityStatus.REJECTED,
        MANUAL,
        None,
    )
    assert (homepage.institution_id, kept.homepage_id) == (kept_id, homepage.id)
    assert (pending.status, pending.rejected_reason) == (
        EntityStatus.REJECTED,
        status_changes.SUPERSEDED,
    )
    assert out["work"] == (
        (kept_id, AssignmentStatus.QUEUED),
        (duplicate_id, AssignmentStatus.CANCELLED),
    )


def test_merge_conflicts_are_found_before_anything_moves(
    db: Database, world: World, build: type[Build]
):
    async def attachments(session: AsyncSession, institution: Institution) -> dict[str, Any]:
        """Everything hanging off an institution, as a merge would move it."""
        await session.refresh(institution)
        return {
            "status": institution.status,
            "homepage_id": institution.homepage_id,
            "aliases": sorted(
                await session.scalars(
                    select(Alias.text).where(Alias.institution_id == institution.id)
                )
            ),
            "homepages": sorted(
                await session.scalars(
                    select(Homepage.webpage_id).where(Homepage.institution_id == institution.id)
                )
            ),
            "sources": sorted(
                await session.scalars(
                    select(Source.webpage_id).where(Source.institution_id == institution.id)
                )
            ),
            "served": sorted(
                await session.scalars(
                    select(InstitutionServedPlace.place_id).where(
                        InstitutionServedPlace.institution_id == institution.id
                    )
                )
            ),
            "identifiers": sorted(
                await session.scalars(
                    select(Identifier.value).where(Identifier.institution_id == institution.id)
                )
            ),
            "metrics": sorted(
                await session.scalars(
                    select(Metric.year).where(Metric.institution_id == institution.id)
                )
            ),
            "evidence": sorted(
                await session.scalars(
                    select(Evidence.quote).where(Evidence.entity_id == institution.id)
                )
            ),
            "children": sorted(
                await session.scalars(
                    select(Institution.name).where(
                        Institution.parent_institution_id == institution.id
                    )
                )
            ),
        }

    async def scenario() -> tuple[dict[str, Any], dict[str, Any], dict[str, uuid.UUID]]:
        async with db.session() as session:
            one = await build.candidate_institution(session, world.oakville, "Oakville Library")
            two = await build.candidate_institution(
                session, world.oakville, "Oakville Public Library"
            )
            await graph.add_alias(session, one, "The library", language="en", entered_by=AGENT)
            session.add_all(
                [
                    Identifier(
                        institution_id=one.id, scheme=IdentifierScheme.STATCAN_SGC, value="9"
                    ),
                    Metric(institution_id=one.id, name=MetricName.POPULATION, year=2021, value=5),
                    InstitutionServedPlace(institution_id=one.id, place_id=world.elm.id),
                ]
            )
            tenders = await graph.ensure_webpage(session, "https://www.elmcounty.ca/library/bids")
            await graph.create_source(session, one, tenders, source_type="tender", entered_by=AGENT)
            await graph.create_institution(
                session,
                name="Friends of the Library",
                institution_type="other",
                place=world.oakville,
                entered_by=AGENT,
                parent=one,
            )
            ids = {"tenders": tenders.id}
            for name, institution, url in (("one", one, "/library/"), ("two", two, "/opl/")):
                homepage = await build.claim(session, institution, f"https://www.elmcounty.ca{url}")
                await status_changes.verify_homepage(session, homepage, entered_by=AGENT)
                ids[f"{name}_homepage"] = homepage.id
                ids[f"{name}_page"] = homepage.webpage_id
            rejected = await build.candidate_institution(session, world.oakville, "Gone")
            await status_changes.reject_institution(session, rejected, entered_by=AGENT)
            await session.commit()
            before = (await attachments(session, one), await attachments(session, two))
            cases = [
                (one, two, "both institutions have a verified homepage; reject one first"),
                (one, one, "an entity cannot be merged into itself"),
                (one, rejected, "'Gone' is rejected; merge into a live entity"),
                (one, world.oakville, "a place and an institution cannot be merged"),
            ]
            for duplicate, into, message in cases:
                with pytest.raises(ConflictError, match=re.escape(message)):
                    await status_changes.merge_entities(session, duplicate, into, entered_by=MANUAL)
            await session.commit()
            after = (await attachments(session, one), await attachments(session, two))
            assert after == before
            return before[0], before[1], ids

    one, two, ids = db.run(scenario)
    assert one == {
        "status": EntityStatus.CANDIDATE,
        "homepage_id": ids["one_homepage"],
        "aliases": ["Oakville Library", "The library"],
        "homepages": [ids["one_page"]],
        "sources": [ids["tenders"]],
        "served": [world.elm.id],
        "identifiers": ["9"],
        "metrics": [2021],
        "evidence": [],
        "children": ["Friends of the Library"],
    }
    assert two == {
        "status": EntityStatus.CANDIDATE,
        "homepage_id": ids["two_homepage"],
        "aliases": ["Oakville Public Library"],
        "homepages": [ids["two_page"]],
        "sources": [],
        "served": [],
        "identifiers": [],
        "metrics": [],
        "evidence": [],
        "children": [],
    }


def test_merging_a_government_sets_the_place_link(db: Database, world: World, build: type[Build]):
    async def scenario() -> tuple[Place, Institution, str]:
        async with db.session() as session:
            # The agent saved the town's government again under another name.
            corporation = await build.candidate_institution(
                session,
                world.oakville,
                "The Corporation of the Town of Oakville",
                "municipal_government",
            )
            elsewhere = await build.candidate_institution(session, world.elm, "Oakville Township")
            town = await session.get_one(Institution, world.town.id)
            with pytest.raises(ConflictError) as raised:
                await status_changes.merge_entities(session, town, elsewhere, entered_by=MANUAL)
            await status_changes.merge_entities(session, town, corporation, entered_by=MANUAL)
            await session.commit()
            return (
                await session.get_one(Place, world.oakville.id),
                await session.get_one(Institution, corporation.id),
                str(raised.value),
            )

    oakville, corporation, message = db.run(scenario)
    assert oakville.government_institution_id == corporation.id
    assert "only an institution at that place" in message


def test_merging_places_moves_children_and_merges_their_governments(
    db: Database, world: World, build: type[Build]
):
    async def scenario() -> dict[str, Any]:
        async with db.session() as session:
            pine = await build.verified_place(session, "Pine", "municipality", world.elm)
            pine_government = await build.verified_government(session, pine, "Township of Pine")
            twin = await build.verified_place(session, "Pine Township", "municipality", world.elm)
            twin_government = await build.verified_government(
                session, twin, "Pine Township Council"
            )
            library = await build.candidate_institution(session, pine, "Pine Library")
            session.add(
                Identifier(place_id=pine.id, scheme=IdentifierScheme.STATCAN_SGC, value="3598777")
            )
            hamlet = await build.verified_place(session, "Pine Hamlet", "municipality", pine)
            await build.open_assignment(
                session, world.run, AssignmentType.FIND_INSTITUTIONS, pine.id
            )
            with pytest.raises(ConflictError, match="is a municipality and"):
                await status_changes.merge_entities(session, pine, world.elm, entered_by=MANUAL)
            # A place without a government takes the duplicate's.
            bare = await build.verified_place(session, "Bare", "municipality", world.elm)
            bare_twin = await build.verified_place(session, "Bare Twin", "municipality", world.elm)
            bare_government = await build.verified_government(session, bare, "Township of Bare")
            await status_changes.merge_entities(session, bare, bare_twin, entered_by=MANUAL)

            await status_changes.merge_entities(session, pine, twin, entered_by=MANUAL)
            await session.commit()
            return {
                "pine": await session.get_one(Place, pine.id),
                "twin": await session.get_one(Place, twin.id),
                "pine_government": await session.get_one(Institution, pine_government.id),
                "twin_government": await session.get_one(Institution, twin_government.id),
                "library_place": (await session.get_one(Institution, library.id)).place_id,
                "hamlet_parent": (await session.get_one(Place, hamlet.id)).parent_place_id,
                "code_owner": (
                    await session.execute(select(Identifier).where(Identifier.value == "3598777"))
                )
                .scalar_one()
                .place_id,
                "aliases": sorted(
                    await session.scalars(select(Alias.text).where(Alias.place_id == twin.id))
                ),
                "government_aliases": sorted(
                    await session.scalars(
                        select(Alias.text).where(Alias.institution_id == twin_government.id)
                    )
                ),
                "work": [
                    (row.subject_id, row.status)
                    for row in await session.scalars(
                        select(Assignment).where(
                            Assignment.type == AssignmentType.FIND_INSTITUTIONS
                        )
                    )
                ],
                "bare_twin": await session.get_one(Place, bare_twin.id),
                "bare_government": await session.get_one(Institution, bare_government.id),
                "bare": await session.get_one(Place, bare.id),
            }

    out = db.run(scenario)
    pine, twin = out["pine"], out["twin"]
    assert (pine.status, pine.government_institution_id) == (EntityStatus.REJECTED, None)
    assert twin.government_institution_id == out["twin_government"].id
    pine_government = out["pine_government"]
    assert (pine_government.status, pine_government.place_id) == (EntityStatus.REJECTED, twin.id)
    assert out["library_place"] == twin.id
    assert out["hamlet_parent"] == twin.id
    assert out["code_owner"] == twin.id
    assert out["aliases"] == ["Pine", "Pine Township"]
    assert out["government_aliases"] == ["Pine Township Council", "Township of Pine"]
    assert out["work"] == [(twin.id, AssignmentStatus.QUEUED)]
    bare_twin, bare_government = out["bare_twin"], out["bare_government"]
    assert bare_twin.government_institution_id == bare_government.id
    assert bare_government.place_id == bare_twin.id
    assert out["bare"].status is EntityStatus.REJECTED


def test_verifying_a_homepage_elsewhere_rejects_the_superseded_candidate_domain(
    db: Database, world: World, build: type[Build]
):
    """The directory's old address of a government whose homepage was verified on another
    domain is a candidate domain nothing would decide again: it is rejected with the claim. A
    domain another institution still claims is left to that institution's own search."""

    async def scenario() -> tuple[Homepage, Homepage, Domain, Domain, list[Spawn]]:
        async with db.session() as session:
            town = await session.get_one(Institution, world.town.id)
            old = await build.claim(session, town, "https://www.oakville-old.ca/")
            await build.claim(session, town, "https://www.oakville-shared.ca/")
            library = await build.candidate_institution(session, world.oakville, "Oakville Library")
            theirs = await build.claim(session, library, "https://www.oakville-shared.ca/library")
            current = await build.claim(session, town, "https://www.elmcounty.ca/oakville/")
            spawn = await status_changes.verify_homepage(session, current, entered_by=AGENT)
            old_domain = await graph.domain_by_name(session, "oakville-old.ca")
            shared_domain = await graph.domain_by_name(session, "oakville-shared.ca")
            assert old_domain is not None
            assert shared_domain is not None
            await session.commit()
            return old, theirs, old_domain, shared_domain, spawn

    old, theirs, old_domain, shared_domain, spawn = db.run(scenario)
    assert (old.status, old.rejected_reason) == (EntityStatus.REJECTED, status_changes.SUPERSEDED)
    assert (old_domain.status, old_domain.entered_by) == (EntityStatus.REJECTED, AGENT)
    assert (shared_domain.status, theirs.status) == (EntityStatus.CANDIDATE, EntityStatus.CANDIDATE)
    # The town has its homepage: nothing sends it looking again.
    assert [s.type for s in spawn] == [
        AssignmentType.FIND_SOURCES,
        AssignmentType.FIND_INSTITUTIONS,
    ]


def test_rejecting_a_domain_with_a_verified_homepage_on_it(
    db: Database, world: World, build: type[Build]
):
    """A rejected domain is dead or nobody's, so a homepage verified on it cannot stand: the
    claim is rejected with the reason, the institution loses its link and looks again, like
    every open claim on the domain (spec section 7.3)."""

    async def scenario() -> tuple[Domain, Homepage, Homepage, Institution, list[Spawn]]:
        async with db.session() as session:
            town = await session.get_one(Institution, world.town.id)
            library = await build.candidate_institution(session, world.oakville, "Oakville Library")
            towns = await build.claim(session, town, "https://www.oakville.example/")
            librarys = await build.claim(session, library, "https://www.oakville.example/library")
            domain = await graph.domain_of_host(session, "www.oakville.example")
            assert domain is not None
            await status_changes.verify_domain(session, domain, entered_by=MANUAL)
            await status_changes.verify_homepage(session, towns, entered_by=AGENT)
            assert town.homepage_id == towns.id
            spawn = await status_changes.reject_domain(
                session, domain, entered_by=MANUAL, reason="the site is dead"
            )
            await session.commit()
            return domain, towns, librarys, town, spawn

    domain, towns, librarys, town, spawn = db.run(scenario)
    assert (domain.status, domain.entered_by) == (EntityStatus.REJECTED, MANUAL)
    assert (towns.status, towns.entered_by, towns.rejected_reason) == (
        EntityStatus.REJECTED,
        MANUAL,
        "the site is dead",
    )
    assert (librarys.status, librarys.rejected_reason) == (
        EntityStatus.REJECTED,
        "the site is dead",
    )
    assert town.homepage_id is None
    assert spawn == [
        Spawn(AssignmentType.FIND_HOMEPAGE, town.id),
        Spawn(AssignmentType.FIND_HOMEPAGE, librarys.institution_id),
    ]


def test_rejecting_the_verified_homepage_clears_the_link_and_looks_again(
    db: Database, world: World, build: type[Build]
):
    async def scenario() -> tuple[Homepage, Institution, list[Spawn]]:
        async with db.session() as session:
            town = await session.get_one(Institution, world.town.id)
            homepage = await build.claim(session, town, "https://www.elmcounty.ca/oakville/")
            await status_changes.verify_homepage(session, homepage, entered_by=AGENT)
            assert town.homepage_id == homepage.id
            spawn = await status_changes.reject_homepage(
                session, homepage, entered_by=MANUAL, reason="the county's page, not the town's"
            )
            await session.commit()
            return homepage, town, spawn

    homepage, town, spawn = db.run(scenario)
    assert (homepage.status, homepage.entered_by, homepage.rejected_reason) == (
        EntityStatus.REJECTED,
        MANUAL,
        "the county's page, not the town's",
    )
    assert town.homepage_id is None
    assert spawn == [Spawn(AssignmentType.FIND_HOMEPAGE, town.id)]


def test_sending_to_review_is_recorded_like_any_change(
    db: Database, world: World, build: type[Build], caplog: pytest.LogCaptureFixture
):
    """The move to `needs_review` goes through the one door: it is logged with the rest, a
    preview of a decision collects it, and nobody is recorded as having decided anything."""

    async def scenario() -> tuple[Institution, Institution, list[status_changes.StatusChange]]:
        async with db.session() as session:
            library = await build.candidate_institution(session, world.oakville, "Oakville Library")
            await status_changes.send_to_review(session, library)
            archive = await build.candidate_institution(session, world.oakville, "Oakville Archive")
            with status_changes.previewing() as recorded:
                await status_changes.send_to_review(session, archive)
            await session.commit()
            return library, archive, recorded

    with caplog.at_level(logging.INFO, logger="public_atlas.modules.graph.status_changes"):
        library, archive, recorded = db.run(scenario)
    assert (library.status, library.entered_by) == (EntityStatus.NEEDS_REVIEW, AGENT)
    assert [record.getMessage() for record in caplog.records] == [
        f"institution {library.id}: candidate -> needs_review by agent"
    ]
    # Previewed, the change is collected and not logged.
    assert recorded == [
        status_changes.StatusChange(archive, EntityStatus.CANDIDATE, EntityStatus.NEEDS_REVIEW)
    ]
    assert archive.status is EntityStatus.NEEDS_REVIEW


def test_a_reviewer_or_a_list_may_verify_an_entity_with_no_evidence(
    db: Database, world: World, build: type[Build]
):
    """The door asks for no evidence: a reviewer's approval and an official list's line are
    each their own warrant. The agent's verifications pass the quote check before they reach
    the door, which the findings tests pin."""

    async def scenario() -> tuple[Institution, Place, int, int]:
        async with db.session() as session:
            library = await build.candidate_institution(session, world.oakville, "Oakville Library")
            library_rows = len(await evidence.evidence_for(session, library.id))
            await status_changes.verify_institution(session, library, entered_by=MANUAL)
            place = await graph.create_place(
                session,
                name="Birch",
                country_code="CA",
                administrative_level="municipality",
                parent=world.elm,
                entered_by=EnteredBy.SCRIPT,
            )
            place_rows = len(await evidence.evidence_for(session, place.id))
            await status_changes.verify_place(session, place, entered_by=EnteredBy.SCRIPT)
            await session.commit()
            return library, place, library_rows, place_rows

    library, place, library_rows, place_rows = db.run(scenario)
    assert (library_rows, place_rows) == (0, 0)
    assert (library.status, library.entered_by) == (EntityStatus.VERIFIED, MANUAL)
    assert (place.status, place.entered_by) == (EntityStatus.VERIFIED, EnteredBy.SCRIPT)


def test_merging_a_parent_into_its_child_reparents_the_child(
    db: Database, world: World, build: type[Build]
):
    async def scenario() -> tuple[Institution, Institution, Institution]:
        async with db.session() as session:
            board = await build.candidate_institution(session, world.oakville, "Library Board")
            library = await graph.create_institution(
                session,
                name="Oakville Library",
                institution_type="library",
                place=world.oakville,
                entered_by=AGENT,
                parent=board,
            )
            branch = await graph.create_institution(
                session,
                name="Oakville Library Branch",
                institution_type="library",
                place=world.oakville,
                entered_by=AGENT,
                parent=board,
            )
            await status_changes.merge_entities(session, board, library, entered_by=MANUAL)
            await session.commit()
            return (
                await session.get_one(Institution, board.id),
                await session.get_one(Institution, library.id),
                await session.get_one(Institution, branch.id),
            )

    board, library, branch = db.run(scenario)
    # The survivor takes the duplicate's parent, the town, rather than hanging under itself.
    assert library.parent_institution_id == world.town.id
    assert branch.parent_institution_id == library.id
    assert board.status is EntityStatus.REJECTED


def test_merge_keeps_the_survivors_code_in_a_scheme(db: Database, world: World, build: type[Build]):
    async def scenario() -> dict[str, tuple[str, IdentifierScheme]]:
        async with db.session() as session:
            kept = await build.candidate_institution(
                session, world.oakville, "Oakville Public Library"
            )
            duplicate = await build.candidate_institution(
                session, world.oakville, "Oakville Library"
            )
            session.add_all(
                [
                    Identifier(
                        institution_id=kept.id, scheme=IdentifierScheme.STATCAN_SGC, value="1"
                    ),
                    Identifier(
                        institution_id=duplicate.id, scheme=IdentifierScheme.STATCAN_SGC, value="2"
                    ),
                    Identifier(
                        institution_id=duplicate.id, scheme=IdentifierScheme.FIPS, value="3"
                    ),
                ]
            )
            await session.flush()
            await status_changes.merge_entities(session, duplicate, kept, entered_by=MANUAL)
            await session.commit()
            rows = await session.scalars(select(Identifier).order_by(Identifier.value))
            return {
                row.value: ("kept" if row.institution_id == kept.id else "duplicate", row.scheme)
                for row in rows
            }

    assert db.run(scenario) == {
        "1": ("kept", IdentifierScheme.STATCAN_SGC),
        "2": ("duplicate", IdentifierScheme.STATCAN_SGC),
        "3": ("kept", IdentifierScheme.FIPS),
    }


def test_rejecting_a_place_is_refused_while_anything_sits_under_it(
    db: Database, world: World, build: type[Build]
):
    async def scenario() -> tuple[list[str], Place, Place, Place]:
        async with db.session() as session:
            with_child = await build.verified_place(session, "Pine", "municipality", world.elm)
            await build.verified_place(session, "Pine Hamlet", "municipality", with_child)
            with_body = await build.verified_place(session, "Birch", "municipality", world.elm)
            await build.candidate_institution(session, with_body, "Birch Library")
            empty = await build.verified_place(session, "Cedar", "municipality", world.elm)
            messages = []
            for place in (with_child, with_body):
                with pytest.raises(ConflictError) as raised:
                    await status_changes.reject_place(session, place, entered_by=MANUAL)
                messages.append(str(raised.value))
            assert await status_changes.reject_place(session, empty, entered_by=MANUAL) == []
            await session.commit()
            return messages, with_child, with_body, empty

    messages, with_child, with_body, empty = db.run(scenario)
    assert messages == ["places sit under 'Pine'", "institutions sit under 'Birch'"]
    assert (with_child.status, with_body.status) == (EntityStatus.VERIFIED, EntityStatus.VERIFIED)
    assert (empty.status, empty.entered_by) == (EntityStatus.REJECTED, MANUAL)


def test_verifying_and_rejecting_a_source_records_who_did_it(
    db: Database, world: World, build: type[Build]
):
    async def scenario() -> tuple[Source, Source]:
        async with db.session() as session:
            budget = await graph.ensure_webpage(session, "https://www.elmcounty.ca/budget")
            tenders = await graph.ensure_webpage(session, "https://www.elmcounty.ca/tenders")
            verified = await graph.create_source(
                session, world.county, budget, source_type="budget", entered_by=AGENT
            )
            rejected = await graph.create_source(
                session, world.county, tenders, source_type="tender", entered_by=AGENT
            )
            assert await status_changes.verify_source(session, verified, entered_by=AGENT) == []
            assert await status_changes.reject_source(session, rejected, entered_by=MANUAL) == []
            await session.commit()
            return verified, rejected

    verified, rejected = db.run(scenario)
    assert (verified.status, verified.entered_by) == (EntityStatus.VERIFIED, AGENT)
    assert (rejected.status, rejected.entered_by) == (EntityStatus.REJECTED, MANUAL)
