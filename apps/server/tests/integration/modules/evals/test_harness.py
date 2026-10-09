"""The eval harness: a subject seeded as the loader would have, its discovery queued and run
under the scripted model, the scorer reading it all back, the results recorded in the main
database, and one eval run end to end on an eval database of its own, twice."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from public_atlas.db import migrations
from public_atlas.modules.assignments import service as assignments
from public_atlas.modules.assignments.models import (
    Assignment,
    AssignmentResult,
    AssignmentStatus,
    AssignmentType,
    Run,
    RunStatus,
)
from public_atlas.modules.evals import dataset, harness, scorer
from public_atlas.modules.evals import service as evals
from public_atlas.modules.evals.dataset import PlaceList, SubjectFile
from public_atlas.modules.evals.models import EvalRun, EvalScore
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph.models import (
    Domain,
    EnteredBy,
    EntityStatus,
    Homepage,
    Institution,
    Place,
    Webpage,
)

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from tests.integration.conftest import Database
    from tests.integration.modules.conftest import Build, Script, World

    from public_atlas.config import Settings
    from public_atlas.resources import Resources

FIND_HOMEPAGE = AssignmentType.FIND_HOMEPAGE
FIND_INSTITUTIONS = AssignmentType.FIND_INSTITUTIONS
FIND_SOURCES = AssignmentType.FIND_SOURCES
EVAL_TEST_DATABASE = "public_atlas_evals_test"


def town_data() -> dict[str, Any]:
    """A lower-tier town under a region nothing loaded: the harness makes both."""
    return {
        "subject": {
            "kind": "place",
            "name": "Town of Fixture",
            "level": "municipality",
            "place": "Town of Fixture",
            "parent": "Regional Municipality of Fixture",
            "tier": "lower",
            "official_code": "3599001",
            "institution": "town-of-fixture",
        },
        "status": "draft",
        "labelled_at": "2026-09-29",
        "trusted_at_start": ["ontario.ca", "fixture.ca"],
        "institutions": [
            {
                "key": "town-of-fixture",
                "type": "municipal_government",
                "names": [
                    {"text": "Town of Fixture", "lang": "en"},
                    {"text": "Ville de Fixture", "lang": "fr"},
                    {"text": "TOF", "lang": "en", "is_acronym": True},
                ],
                "homepage": "https://www.fixture.ca/en/",
                "homepage_host": "trusted_domain",
                "evidence": {"url": "https://www.fixture.ca/en/", "quote": "Town of Fixture"},
            },
            {
                "key": "fixture-fire",
                "type": "fire_service",
                "names": [{"text": "Fixture Fire Services", "lang": "en"}],
                "homepage": "https://www.fixture.ca/en/fire",
                "homepage_host": "trusted_domain",
                "evidence": {"url": "https://www.fixture.ca/en/", "quote": "Fixture Fire"},
                "parent": {
                    "institution": "town-of-fixture",
                    "label": "a division of",
                    "evidence": {"url": "https://www.fixture.ca/en/fire", "quote": "division"},
                },
            },
        ],
        "sources": [
            {
                "institution": "town-of-fixture",
                "source_type": "budget",
                "url": "https://www.fixture.ca/en/budget",
                "evidence": {"url": "https://www.fixture.ca/en/budget", "quote": "Budget"},
            },
        ],
        "absent_sources": [
            {
                "institution": "fixture-fire",
                "source_type": "budget",
                "note": "through the town",
                "covered_by": "town-of-fixture",
            },
            {"institution": "fixture-fire", "source_type": "procurement", "note": "none"},
        ],
    }


def town_file() -> SubjectFile:
    return SubjectFile.model_validate(town_data())


def ministry_file() -> SubjectFile:
    return SubjectFile.model_validate(
        {
            "subject": {
                "kind": "institution",
                "name": "Ministry of Fixtures",
                "level": "province_territory",
                "place": "Ontario",
                "institution": "ministry-of-fixtures",
                "government_homepage": "https://www.ontario.ca/",
            },
            "status": "draft",
            "labelled_at": "2026-09-29",
            "trusted_at_start": ["ontario.ca"],
            "institutions": [
                {
                    "key": "ministry-of-fixtures",
                    "type": "ministry",
                    "names": [{"text": "Ministry of Fixtures", "lang": "en"}],
                    "homepage": "https://www.ontario.ca/page/ministry-fixtures",
                    "homepage_host": "trusted_domain",
                    "evidence": {
                        "url": "https://www.ontario.ca/page/ministry-fixtures",
                        "quote": "Ministry of Fixtures",
                    },
                },
            ],
            "sources": [
                {
                    "institution": "ministry-of-fixtures",
                    "source_type": "procurement",
                    "url": "https://www.ontario.ca/page/doing-business",
                    "evidence": {
                        "url": "https://www.ontario.ca/page/doing-business",
                        "quote": "Buy",
                    },
                },
            ],
        }
    )


def municipal_list() -> PlaceList:
    """The world's town, as an official list names it."""
    return PlaceList.model_validate(
        {
            "place": "Ontario",
            "source": {"url": "https://example.test/list"},
            "expected_counts": {"total": 1},
            "municipalities": [
                {
                    "name": "Oakville, Town of",
                    "tier": "lower",
                    "level": "municipality",
                    "parent": "Elm",
                    "homepage": "https://www.oakville.ca/",
                    "homepage_host": "own_domain",
                },
            ],
        }
    )


@pytest.fixture
def in_session(db: Database) -> Callable[[Callable[[AsyncSession], Awaitable[Any]]], Any]:
    """Run `work` on a session of the test transaction and commit."""

    def run(work: Callable[[AsyncSession], Awaitable[Any]]) -> Any:
        async def inner() -> Any:
            async with db.session() as session:
                result = await work(session)
                await session.commit()
                return result

        return db.run(inner)

    return run


@pytest.fixture
def finishing(scripted: Callable[[Script], Resources], finish_script: Callable[..., Script]):
    """The scripted model that finishes every assignment at once, installed for the inline
    jobs; the resources to run with."""
    return scripted(finish_script())


def seed_town(in_session: Callable[..., Any], resources: Resources, world: World) -> harness.Seeded:
    return in_session(
        lambda session: harness.seed_subject(
            session, resources, world.run, world.rules, town_file(), slug="fixture"
        )
    )


def test_a_town_is_seeded_as_the_loader_would_and_its_work_queued(
    db: Database, world: World, finishing: Resources, in_session: Callable[..., Any]
):
    seeded = seed_town(in_session, finishing, world)

    async def check(session: AsyncSession) -> None:
        town = await session.get_one(Place, seeded.place_id)
        assert town.administrative_level == "municipality"
        assert town.status is EntityStatus.VERIFIED
        assert town.entered_by is EnteredBy.MANUAL
        region = await session.get_one(Place, town.parent_place_id)
        assert region.administrative_level == "region"
        assert region.name == "Regional Municipality of Fixture"
        assert region.parent_place_id == world.ontario.id
        assert region.government_institution_id is not None, "the region got a government too"

        government = await session.get_one(Institution, seeded.institution_id)
        assert town.government_institution_id == government.id
        assert government.institution_type == "municipal_government"
        names = await graph.names_of(session, government)
        assert {(n.text, n.language, n.is_acronym) for n in names} == {
            ("Town of Fixture", "en", False),
            ("Ville de Fixture", "fr", False),
            ("TOF", "en", True),
        }
        domain = await graph.domain_by_name(session, "fixture.ca")
        assert domain is not None
        assert graph.is_trusted(domain)
        assert domain.entered_by is EnteredBy.MANUAL
        homepage = await session.get_one(Homepage, government.homepage_id)
        assert homepage.status is EntityStatus.VERIFIED
        webpage = await session.get_one(Webpage, homepage.webpage_id)
        assert webpage.url == "https://www.fixture.ca/en/"
        assert webpage.domain_id == domain.id

        # The discovery it queued, run to finished by the scripted model.
        rows = {(a.type, a.subject_id): a for a in await session.scalars(select(Assignment))}
        for type_, subject_id in [(FIND_INSTITUTIONS, town.id), (FIND_SOURCES, government.id)]:
            assert rows[(type_, subject_id)].status is AssignmentStatus.FINISHED
            assert rows[(type_, subject_id)].run_id == world.run.id

    in_session(check)
    assert {a.type for a in seeded.queued} == {FIND_INSTITUTIONS, FIND_SOURCES}


def test_seeding_again_changes_nothing(
    db: Database, world: World, finishing: Resources, in_session: Callable[..., Any]
):
    first = seed_town(in_session, finishing, world)
    second = seed_town(in_session, finishing, world)
    assert (first.place_id, first.institution_id) == (second.place_id, second.institution_id)
    assert {a.id for a in first.queued} == {a.id for a in second.queued}

    async def count(session: AsyncSession) -> int:
        return len(list(await session.scalars(select(Assignment))))

    assert in_session(count) == 2


def test_a_ministry_is_seeded_in_the_province(
    db: Database, world: World, finishing: Resources, in_session: Callable[..., Any]
):
    seeded = in_session(
        lambda session: harness.seed_subject(
            session, finishing, world.run, world.rules, ministry_file(), slug="ministry"
        )
    )
    assert seeded.place_id == world.ontario.id

    async def check(session: AsyncSession) -> None:
        ministry = await session.get_one(Institution, seeded.institution_id)
        assert ministry.institution_type == "ministry"
        assert ministry.place_id == world.ontario.id
        assert ministry.status is EntityStatus.VERIFIED
        homepage = await session.get_one(Homepage, ministry.homepage_id)
        webpage = await session.get_one(Webpage, homepage.webpage_id)
        assert webpage.url == "https://www.ontario.ca/page/ministry-fixtures"
        # The province's government got the homepage the file names, so the ministry's page
        # sits under a verified government.
        ontario = await session.get_one(Place, world.ontario.id)
        head = await session.get_one(Institution, ontario.government_institution_id)
        head_page = await session.get_one(Homepage, head.homepage_id)
        assert (
            await session.get_one(Webpage, head_page.webpage_id)
        ).url == "https://www.ontario.ca/"
        # Only the ministry's sources are the agent's to find: its agencies come from an
        # official list, so no province-wide discovery is queued for it.
        assert [(a.type, a.subject_id) for a in seeded.queued] == [(FIND_SOURCES, ministry.id)]
        for assignment in seeded.queued:
            row = await session.get_one(Assignment, assignment.id)
            assert row.status is AssignmentStatus.FINISHED

    in_session(check)


def test_a_held_search_is_released_and_a_stale_one_cancelled(
    db: Database,
    world: World,
    build: type[Build],
    finishing: Resources,
    in_session: Callable[..., Any],
):
    """A run seeded held holds a `find_homepage` for every government: a places file releases
    its governments', and a subject whose homepage the file gives cancels its own."""

    async def hold(session: AsyncSession) -> Assignment:
        return await build.open_assignment(
            session, world.run, FIND_HOMEPAGE, world.town.id, status=AssignmentStatus.HELD
        )

    held = in_session(hold)
    seeded = in_session(
        lambda session: harness.seed_places(
            session, finishing, world.run, world.rules, municipal_list(), slug="list"
        )
    )
    assert [a.id for a in seeded.queued] == [held.id]

    async def status(session: AsyncSession) -> tuple[AssignmentStatus, AssignmentResult | None]:
        row = await session.get_one(Assignment, held.id)
        return row.status, row.result

    # Released, run by the scripted model, which finished at once without a homepage.
    assert in_session(status) == (AssignmentStatus.FINISHED, AssignmentResult.NO_HOMEPAGE)

    stale = in_session(hold)

    async def seed(session: AsyncSession) -> harness.Seeded:
        data = town_data()
        data["subject"].update({"name": "Oakville", "parent": "Elm", "official_code": None})
        data["institutions"][0]["names"] = [{"text": "Town of Oakville", "lang": "en"}]
        data["institutions"][0]["homepage"] = "https://www.oakville.ca/"
        data["trusted_at_start"] = ["ontario.ca", "oakville.ca"]
        return await harness.seed_subject(
            session, finishing, world.run, world.rules, SubjectFile.model_validate(data), slug="o"
        )

    seeded = in_session(seed)
    assert seeded.place_id == world.oakville.id
    assert seeded.institution_id == world.town.id

    async def stale_status(session: AsyncSession) -> AssignmentStatus:
        return (await session.get_one(Assignment, stale.id)).status

    assert in_session(stale_status) is AssignmentStatus.CANCELLED


def test_the_scorer_reads_the_seeded_graph_back(
    db: Database, world: World, finishing: Resources, in_session: Callable[..., Any]
):
    seed_town(in_session, finishing, world)
    file = town_file()
    graph_read = in_session(scorer.load_graph)
    (card,) = scorer.score_files(graph_read, world.rules, {"fixture": file}, {})
    assert card.notes == []
    institutions = card.tallies[FIND_INSTITUTIONS]
    # The fire service, which no agent looked for, and so its parent link.
    assert institutions.buckets["not found"] == 1
    assert institutions.buckets["institution not found"] == 1
    sources = card.tallies[FIND_SOURCES]
    lines = "\n".join(sources.lines)
    assert "- town-of-fixture/budget: not found" in lines
    assert "- fixture-fire/budget (absent): institution not found" in lines
    # The scripted model's summary names no source type.
    assert sources.hits == 0


def test_the_real_dataset_scores_against_a_bare_database(
    db: Database, world: World, in_session: Callable[..., Any]
):
    subjects, lists = evals.load_dataset(dataset.all_files())
    graph_read = in_session(scorer.load_graph)
    cards = scorer.score_files(graph_read, world.rules, subjects, lists)
    assert len(cards) == len(subjects) + len(lists)
    by_slug = {card.slug: card for card in cards}
    # The municipalities are not there; the places file's province is.
    assert "not in the database" in by_slug["toronto"].notes[0]
    assert by_slug["ontario-municipalities"].notes == []
    assert scorer.totals(cards)[FIND_INSTITUTIONS].hits == 0
    assert "institutions: find_institutions recall" in scorer.render(cards)


def test_results_are_recorded_and_read_back(
    db: Database,
    world: World,
    finishing: Resources,
    in_session: Callable[..., Any],
    client: TestClient,
):
    seed_town(in_session, finishing, world)
    file = town_file()
    graph_read = in_session(scorer.load_graph)
    cards = scorer.score_files(graph_read, world.rules, {"fixture": file}, {})

    async def record(session: AsyncSession) -> uuid.UUID:
        eval_run = EvalRun(
            run_id=world.run.id,
            dataset_version=dataset.version(),
            model="scripted",
            settings={"subjects": ["fixture"]},
            cost=Decimal(0),
            started_at=datetime.now(UTC),
        )
        session.add(eval_run)
        await session.flush()
        costs = await harness.cost_lines(session, world.run.id)
        rows = await evals.record_results(session, eval_run, cards, costs)
        # The fire service was not found: an institution, a parent link, a homepage and a
        # source are missed, so every measure has something to record.
        assert {row.assignment_type for row in rows} == set(AssignmentType)
        return eval_run.id

    eval_run_id = in_session(record)
    detail = in_session(lambda session: evals.read_eval_run(session, eval_run_id))
    assert detail.finished_at is not None
    by_type = {score.assignment_type: score for score in detail.scores}
    assert by_type[FIND_INSTITUTIONS].recall == 0
    assert {entry.bucket for entry in by_type[FIND_INSTITUTIONS].misses} == {
        "not found",
        "institution not found",
    }
    assert by_type[FIND_SOURCES].precision is None  # nothing saved, nothing wrong
    # Hits are kept beside the misses, every entry with its kind.
    institutions = by_type[FIND_INSTITUTIONS]
    assert institutions.hits is not None
    assert {entry.kind for entry in institutions.hits} <= {"hit"}
    assert {entry.kind for entry in institutions.misses} <= {"miss", "wrong"}
    # The gates the run was judged on: a subject file only, so no list file for homepages.
    assert [(gate.name, gate.verdict) for gate in detail.gates] == [
        ("homepages", None),
        ("institutions", "fail"),
        ("sources", "fail"),
    ]
    assert detail.gates[1].hits == 0
    assert detail.previous_id is None
    listed = client.get("/eval-runs").json()
    assert [row["id"] for row in listed["items"]] == [str(eval_run_id)]
    assert [entry.bucket for entry in by_type[FIND_HOMEPAGE].misses] == ["institution not found"]
    page = client.get(f"/eval-runs/{eval_run_id}").json()
    assert len(page["scores"]) == 3
    # The per-type means the console shows, on the list and the detail alike.
    assert page["summary"]["find_institutions"] == {
        "subjects": 1,
        "mean_recall": 0.0,
        "mean_precision": None,
        "hits": len(institutions.hits),
        "misses": len(institutions.misses),
        "false_positives": len(institutions.false_positives),
    }
    assert listed["items"][0]["summary"] == page["summary"]
    assert listed["items"][0]["gates"] == page["gates"]
    assert client.get(f"/eval-runs/{uuid.uuid4()}").status_code == 404

    async def record_later(session: AsyncSession) -> uuid.UUID:
        # A run from before hits and gates were kept, started after the first.
        eval_run = EvalRun(
            run_id=world.run.id,
            dataset_version="older",
            model="scripted",
            settings={},
            cost=Decimal(0),
            started_at=datetime.now(UTC),
        )
        session.add(eval_run)
        await session.flush()
        session.add(
            EvalScore(
                eval_run_id=eval_run.id,
                subject="fixture",
                assignment_type=FIND_SOURCES,
                recall=0.5,
                precision=None,
                hits=None,
                misses=[{"kind": "miss", "line": "a", "bucket": "not found", "group": None}],
                false_positives=[],
            )
        )
        return eval_run.id

    later_id = in_session(record_later)
    later = client.get(f"/eval-runs/{later_id}").json()
    # Unfinished runs are not compared against; the first, finished, is.
    assert later["previous_id"] == str(eval_run_id)
    assert later["summary"]["find_sources"]["hits"] is None
    # No gates were recorded: today's floors, unjudged.
    assert [(gate["floor"], gate["verdict"], gate["hits"]) for gate in later["gates"]] == [
        (0.99, None, None),
        (0.95, None, None),
        (0.9, None, None),
    ]


def test_progress_and_cost_lines(
    db: Database, world: World, finishing: Resources, in_session: Callable[..., Any]
):
    seed_town(in_session, finishing, world)
    line = db.run(harness.progress, finishing)
    assert line.startswith("assignments: finished 2; open: none")

    async def record(session: AsyncSession) -> None:
        rows = list(await session.scalars(select(Assignment)))
        await assignments.record_usage(
            session,
            assignment_id=rows[0].id,
            kind=assignments.UsageKind.MODEL,
            provider="gpt-6-luna",
            purpose=rows[0].type.value,
            units=1_100_000,
            cached_units=500_000,
            output_units=100_000,
        )

    in_session(record)
    costs = in_session(lambda session: harness.cost_lines(session, world.run.id))
    by_provider = {line.provider: line for line in costs}
    # 500k uncached at $0.10/M, 500k cached at $0.01/M, 100k out at $0.50/M.
    assert by_provider["gpt-6-luna"].cost == Decimal("0.105")
    by_subject = in_session(
        lambda session: harness.cost_by_subject(
            session, world.run.id, {"fixture": [a.id for a in []]}
        )
    )
    assert by_subject == {"fixture": Decimal(0)}
    rendered = harness.render_costs(costs, by_subject)
    assert "$  0.1050" in rendered
    assert "total" in rendered


# --- End to end, on an eval database of its own ---


@pytest.fixture
def eval_resources(finishing: Resources, settings: Settings) -> Resources:
    """The main resources (the test transaction, the scripted model) pointed at an eval database
    of the tests' own."""
    eval_settings = settings.model_copy(update={"eval_database_name": EVAL_TEST_DATABASE})
    return replace(finishing, settings=eval_settings)


@pytest.fixture
def subject_file(tmp_path: Path) -> Path:
    path = tmp_path / "fixture.yaml"
    path.write_text(yaml.safe_dump(town_data(), sort_keys=False))
    return path


def test_an_eval_run_end_to_end_records_its_scores_and_cost(
    db: Database,
    world: World,
    eval_resources: Resources,
    subject_file: Path,
    in_session: Callable[..., Any],
):
    """The eval database is reset and migrated, the country seeded with every assignment held,
    the subject seeded and its discovery queued and served in process, the graph scored, and
    the run and its scores recorded in the main database. A second run appears beside the
    first."""
    lines: list[str] = []

    async def run() -> evals.EvalReport:
        return await evals.run_eval(
            eval_resources,
            [subject_file],
            lists=(),
            queues=("assignment", "default"),
            report=lines.append,
            poll_seconds=0.5,
        )

    first = db.run(run)
    assert first.served
    assert first.database == EVAL_TEST_DATABASE
    assert [item.slug for item in first.seeded] == ["fixture"]
    assert {a.type for a in first.seeded[0].queued} == {FIND_INSTITUTIONS, FIND_SOURCES}
    assert any("seeded the country" in line for line in lines)
    (card,) = first.cards
    assert card.slug == "fixture"
    assert card.tallies[FIND_INSTITUTIONS].buckets["not found"] == 1
    assert first.cost == Decimal(0)  # the scripted model has no price
    assert "== gates" in first.render()
    assert first.as_json()["eval_run_id"] == str(first.eval_run_id)

    async def recorded(session: AsyncSession) -> tuple[EvalRun, list[EvalScore], Run]:
        eval_run = await session.get_one(EvalRun, first.eval_run_id)
        scores = list(
            await session.scalars(select(EvalScore).where(EvalScore.eval_run_id == eval_run.id))
        )
        return eval_run, scores, await session.get_one(Run, first.run_id)

    eval_run, scores, run_row = in_session(recorded)
    assert eval_run.finished_at is not None
    assert eval_run.dataset_version == dataset.version()
    assert eval_run.settings["subjects"] == ["fixture"]
    assert eval_run.settings["official_lists"] == []
    assert {score.assignment_type for score in scores} == set(AssignmentType)
    assert run_row.is_eval
    assert run_row.status is RunStatus.STOPPED

    async def in_eval_database() -> tuple[Run, dict[AssignmentType, set[AssignmentStatus]], int]:
        settings = harness.eval_settings(eval_resources.settings)
        async with (
            evals._eval_resources(eval_resources, settings) as res,  # noqa: SLF001
            res.session() as session,
        ):
            mirrored = await session.get_one(Run, first.run_id)
            found: dict[AssignmentType, set[AssignmentStatus]] = {}
            for row in await session.scalars(select(Assignment)):
                found.setdefault(row.type, set()).add(row.status)
            domains = len(list(await session.scalars(select(Domain))))
            return mirrored, found, domains

    mirrored, statuses, domains = db.run(in_eval_database)
    assert mirrored.is_eval
    assert mirrored.status is RunStatus.STOPPED
    # The province's own search was seeded held and cancelled when the run stopped at the end;
    # the subject's discovery ran to the end.
    assert statuses[FIND_HOMEPAGE] == {AssignmentStatus.CANCELLED}
    assert statuses[FIND_INSTITUTIONS] == {AssignmentStatus.FINISHED}
    assert statuses[FIND_SOURCES] == {AssignmentStatus.FINISHED}
    assert domains > 0, "the seed's platforms and anchor are there"

    second = db.run(run)
    assert second.eval_run_id != first.eval_run_id

    async def listed(session: AsyncSession) -> list[uuid.UUID]:
        rows, _ = await evals.list_eval_runs(session)
        return [row.id for row in rows]

    assert in_session(listed) == [second.eval_run_id, first.eval_run_id]


def test_the_eval_database_is_never_the_main_one(settings: Settings):
    main = make_url(str(settings.database_url)).database or ""
    shared = settings.model_copy(update={"eval_database_name": main})
    with pytest.raises(ValueError, match="is the main database"):
        harness.refuse_shared_database(shared, shared.eval_database_name)
    pointed = make_url(str(harness.eval_settings(settings).database_url))
    assert pointed.database == settings.eval_database_name


def test_an_eval_needs_the_main_database_at_the_latest_migration(
    db: Database, finishing: Resources
):
    """The run and its scores are rows in the main database. A database behind the migrations
    is refused before the eval database is touched, not at the insert hours later."""

    async def behind(connection: AsyncConnection) -> None:
        await connection.run_sync(migrations.check_head)
        # Any revision but the head reads as behind: the check compares, it does not look it up.
        await connection.execute(text("UPDATE alembic_version SET version_num = '000000000000'"))
        with pytest.raises(migrations.NotMigratedError, match="alembic upgrade head"):
            await connection.run_sync(migrations.check_head)

    db.run(behind, db.connection)
    files = dataset.files_named(["mcgarry"], lists_by_default=False)
    with pytest.raises(migrations.NotMigratedError):
        db.run(lambda: evals.run_eval(finishing, files, serve=False))
    with pytest.raises(migrations.NotMigratedError):
        db.run(lambda: evals.score_database(finishing, files, eval_database=True))
