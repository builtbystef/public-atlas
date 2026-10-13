"""Runs and spawning: a run seeds itself with the work due for its filter, held in step mode and
queued in auto mode; releasing queues held work a few at a time; a paused run's job is put back and
its assignment stays queued; stop cancels what is held or queued; a spawn obeys the run's mode and
filter and never doubles open work; and a reviewer's decision spawns into the run it belongs to."""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from public_atlas.modules.assignments import service
from public_atlas.modules.assignments.models import (
    Assignment,
    AssignmentResult,
    AssignmentStatus,
    AssignmentType,
    Run,
    RunMode,
    RunStatus,
    UsageKind,
)
from public_atlas.modules.assignments.schemas import RunFilter
from public_atlas.modules.assignments.service import Spawn
from public_atlas.modules.review import service as review
from public_atlas.shared.exceptions import ConflictError

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    from tests.integration.conftest import Database, InlineConnector
    from tests.integration.modules.conftest import Build, Script, World

    from public_atlas.resources import Resources

FIND_HOMEPAGE = AssignmentType.FIND_HOMEPAGE
FIND_INSTITUTIONS = AssignmentType.FIND_INSTITUTIONS
FIND_SOURCES = AssignmentType.FIND_SOURCES


def work(rows: list[Assignment]) -> set[tuple[AssignmentType, uuid.UUID]]:
    """The (type, subject) pairs of the rows."""
    return {(row.type, row.subject_id) for row in rows}


async def create(
    db: Database, queue: InlineConnector, run_filter: RunFilter | None = None
) -> tuple[Run, list[Assignment]]:
    """A step-mode run on Canada, seeded."""
    assert queue.resources is not None
    async with db.session() as session:
        run = await service.create_run(
            session,
            queue.resources.jobs,
            name="test",
            country_code="CA",
            mode=RunMode.STEP,
            filter=run_filter,
        )
        await session.commit()
        return run, await service.list_assignments(session, run_id=run.id)


def test_a_step_run_seeds_itself_with_the_work_due_and_holds_it(
    db: Database, world: World, queue: InlineConnector
):
    """The county has a verified homepage: its sources and, as Elm's government, Elm's
    institutions are due. The town and the seed's fourteen anchor governments have none: their
    homepages are due. Nothing is queued in step mode, and a second run finds the work open
    already."""
    run, rows = db.run(create, db, queue)
    assert len(world.anchors) == 14
    assert work(rows) == {
        (FIND_SOURCES, world.county.id),
        (FIND_INSTITUTIONS, world.elm.id),
        (FIND_HOMEPAGE, world.town.id),
        *((FIND_HOMEPAGE, government) for government in world.anchor_government_ids),
    }
    assert {row.status for row in rows} == {AssignmentStatus.HELD}
    assert {row.run_id for row in rows} == {run.id}
    # Each row carries its type's budget (descriptors.py).
    budgets = {
        FIND_HOMEPAGE: (60, 4_000_000),
        FIND_INSTITUTIONS: (250, 20_000_000),
        FIND_SOURCES: (120, 10_000_000),
    }
    assert [(row.budget_requests, row.budget_tokens) for row in rows] == [
        budgets[row.type] for row in rows
    ]
    assert not any(job["task_name"] == service.RUN_ASSIGNMENT_TASK for job in queue.jobs.values())
    _, again = db.run(create, db, queue)
    assert again == []


def test_the_filter_bounds_what_a_run_seeds(db: Database, world: World, queue: InlineConnector):
    _, by_level = db.run(create, db, queue, RunFilter(administrative_levels=["municipality"]))
    assert work(by_level) == {(FIND_HOMEPAGE, world.town.id)}

    async def stop_it() -> None:
        async with db.session() as session:
            runs, _ = await service.list_runs(session)
            for run in runs:
                if run.status is not RunStatus.STOPPED:
                    await service.stop_run(session, run)
            await session.commit()

    db.run(stop_it)
    _, by_type = db.run(create, db, queue, RunFilter(assignment_types=[FIND_SOURCES]))
    assert work(by_type) == {(FIND_SOURCES, world.county.id)}
    db.run(stop_it)
    _, by_subject = db.run(create, db, queue, RunFilter(subject_ids=[world.elm.id]))
    assert work(by_subject) == {(FIND_INSTITUTIONS, world.elm.id)}
    db.run(stop_it)
    _, by_institution_type = db.run(
        create, db, queue, RunFilter(institution_types=["municipal_government"])
    )
    # Places are not of an institution type; the type filter bounds the institutions only.
    assert work(by_institution_type) == {
        (FIND_INSTITUTIONS, world.elm.id),
        (FIND_HOMEPAGE, world.town.id),
    }


def test_settled_work_is_not_seeded_again_but_unsettled_work_is(
    db: Database, world: World, queue: InlineConnector, build: type[Build]
):
    async def scenario() -> tuple[set[tuple[AssignmentType, uuid.UUID]], set[AssignmentStatus]]:
        assert queue.resources is not None
        async with db.session() as session:
            done = await build.open_assignment(
                session, world.run, FIND_SOURCES, world.county.id, status=AssignmentStatus.RUNNING
            )
            service.lifecycle.finish(done, AssignmentResult.COMPLETE, summary="done")
            spent = await build.open_assignment(
                session, world.run, FIND_HOMEPAGE, world.town.id, status=AssignmentStatus.RUNNING
            )
            service.lifecycle.finish(spent, AssignmentResult.OUT_OF_BUDGET, summary="spent")
            await session.commit()
            run = await service.create_run(
                session, queue.resources.jobs, name="again", country_code="CA", mode=RunMode.STEP
            )
            await session.commit()
            rows = await service.list_assignments(session, run_id=run.id)
            return work(rows), {row.status for row in rows}

    found, statuses = db.run(scenario)
    assert (FIND_SOURCES, world.county.id) not in found
    assert (FIND_HOMEPAGE, world.town.id) in found
    assert statuses == {AssignmentStatus.HELD}


def test_release_queues_held_work_a_few_at_a_time_and_the_worker_runs_it(
    db: Database,
    world: World,
    queue: InlineConnector,
    scripted: Callable[[Script], Resources],
    finish_script: Callable[..., Script],
):
    """A step-mode run released one assignment at a time: the released one is queued, its job
    runs (inline here) and finishes it; the rest stay held."""
    scripted(finish_script("Looked everywhere."))
    run, _rows = db.run(create, db, queue)

    async def release_one() -> list[Assignment]:
        assert queue.resources is not None
        async with db.session() as session:
            released = await service.release(
                session,
                queue.resources.jobs,
                await service.get_run(session, run.id),
                limit=1,
                assignment_type=FIND_SOURCES,
            )
            await session.commit()
            return released

    released = db.run(release_one)
    assert [(row.type, row.subject_id) for row in released] == [(FIND_SOURCES, world.county.id)]

    async def check() -> tuple[Assignment, dict[AssignmentStatus, int]]:
        async with db.session() as session:
            row = await session.get_one(Assignment, released[0].id)
            progress = await service.progress(session, await service.get_run(session, run.id))
            return row, progress.by_status

    row, by_status = db.run(check)
    assert (row.status, row.result, row.summary) == (
        AssignmentStatus.FINISHED,
        AssignmentResult.COMPLETE,
        "Looked everywhere.",
    )
    assert by_status == {AssignmentStatus.HELD: 2 + 14, AssignmentStatus.FINISHED: 1}


def test_a_paused_run_puts_the_job_back_and_the_assignment_stays_queued(
    db: Database,
    world: World,
    queue: InlineConnector,
    scripted: Callable[[Script], Resources],
    finish_script: Callable[..., Script],
):
    scripted(finish_script())
    run, _ = db.run(create, db, queue)

    async def pause_then_release() -> Assignment:
        assert queue.resources is not None
        async with db.session() as session:
            run_row = await service.get_run(session, run.id)
            await service.pause_run(session, run_row)
            released = await service.release(
                session, queue.resources.jobs, run_row, limit=1, assignment_type=FIND_SOURCES
            )
            await session.commit()
            return released[0]

    released = db.run(pause_then_release)

    async def check() -> Assignment:
        async with db.session() as session:
            return await session.get_one(Assignment, released.id)

    row = db.run(check)
    assert (row.status, row.sessions) == (AssignmentStatus.QUEUED, 0)
    jobs = [
        job
        for job in queue.jobs.values()
        if job["task_name"] == service.RUN_ASSIGNMENT_TASK
        and job["args"]["assignment_id"] == str(released.id)
    ]
    # The first job ran and returned at once; the one it put back waits for the delay.
    assert [job["status"] for job in jobs] == ["succeeded", "todo"]
    assert jobs[1]["scheduled_at"] is not None
    assert jobs[1]["lock"] == f"assignment:{released.id}"

    async def resume() -> RunStatus:
        async with db.session() as session:
            run_row = await service.get_run(session, run.id)
            await service.resume_run(session, run_row)
            with pytest.raises(ConflictError, match="active run cannot be resumed"):
                await service.resume_run(session, run_row)
            await session.commit()
            return run_row.status

    assert db.run(resume) is RunStatus.ACTIVE


def test_stop_cancels_held_and_queued_work_and_refuses_more(
    db: Database, world: World, queue: InlineConnector
):
    """Of the seeded work one row is queued (as a release leaves it) and one is running (as a
    worker leaves it): stop cancels the held and the queued rows, the running one is the
    runner's to cancel after its session, and nothing more is released or spawned."""
    run, rows = db.run(create, db, queue)
    by_work = {(row.type, row.subject_id): row for row in rows}
    queued = by_work[(FIND_SOURCES, world.county.id)]
    running = by_work[(FIND_INSTITUTIONS, world.elm.id)]

    async def stop() -> tuple[list[Assignment], list[Assignment], list[Assignment]]:
        assert queue.resources is not None
        async with db.session() as session:
            service.lifecycle.queue(await session.get_one(Assignment, queued.id))
            started = await session.get_one(Assignment, running.id)
            service.lifecycle.queue(started)
            service.lifecycle.start(started)
            await session.commit()
            run_row = await service.get_run(session, run.id)
            cancelled = await service.stop_run(session, run_row)
            with pytest.raises(ConflictError, match="the run is stopped already"):
                await service.stop_run(session, run_row)
            with pytest.raises(ConflictError, match="the run is stopped"):
                await service.release(session, queue.resources.jobs, run_row)
            spawned = await service.spawn(
                session, queue.resources.jobs, run_row, [Spawn(FIND_HOMEPAGE, world.town.id)]
            )
            await session.commit()
            return cancelled, spawned, await service.list_assignments(session, run_id=run.id)

    cancelled, spawned, after = db.run(stop)
    assert len(rows) == 3 + 14
    assert {row.id for row in cancelled} == {row.id for row in rows} - {running.id}
    assert spawned == []
    assert {row.id: row.status for row in after} == {
        **{row.id: AssignmentStatus.CANCELLED for row in rows},
        running.id: AssignmentStatus.RUNNING,
    }


def test_a_spawn_obeys_the_mode_and_the_filter_and_never_doubles_open_work(
    db: Database,
    world: World,
    queue: InlineConnector,
    build: type[Build],
    scripted: Callable[[Script], Resources],
    finish_script: Callable[..., Script],
):
    scripted(finish_script())

    async def scenario() -> tuple[list[Assignment], list[Assignment], list[Assignment], Assignment]:
        assert queue.resources is not None
        jobs = queue.resources.jobs
        async with db.session() as session:
            library = await build.candidate_institution(session, world.oakville, "Oakville Library")
            step = await service.create_run(
                session,
                jobs,
                name="step",
                country_code="CA",
                mode=RunMode.STEP,
                filter=RunFilter(administrative_levels=["municipality"]),
                seed=False,
            )
            held = await service.spawn(
                session,
                jobs,
                step,
                [
                    Spawn(FIND_HOMEPAGE, library.id),
                    Spawn(FIND_HOMEPAGE, library.id),
                    # A region: outside the filter's levels.
                    Spawn(FIND_INSTITUTIONS, world.elm.id),
                    # Gone: no such institution.
                    Spawn(FIND_HOMEPAGE, uuid.uuid7()),
                ],
            )
            again = await service.spawn(session, jobs, step, [Spawn(FIND_HOMEPAGE, library.id)])
            auto = await service.create_run(
                session, jobs, name="auto", country_code="CA", mode=RunMode.AUTO, seed=False
            )
            # Open on the library already (held in the step run): not doubled across runs.
            doubled = await service.spawn(session, jobs, auto, [Spawn(FIND_HOMEPAGE, library.id)])
            queued = await service.spawn(
                session, jobs, auto, [Spawn(FIND_SOURCES, world.county.id)], parent=held[0]
            )
            await session.commit()
        # The job ran in a session of its own: read the row afresh.
        async with db.session() as session:
            return held, again, doubled, await session.get_one(Assignment, queued[0].id)

    held, again, doubled, ran = db.run(scenario)
    assert [(row.type, row.status) for row in held] == [(FIND_HOMEPAGE, AssignmentStatus.HELD)]
    assert again == []
    assert doubled == []
    # Auto mode queued it with a job, which ran (inline) and finished it.
    assert (ran.status, ran.result, ran.parent_assignment_id) == (
        AssignmentStatus.FINISHED,
        AssignmentResult.COMPLETE,
        held[0].id,
    )


def test_the_runs_api_creates_controls_and_reads_runs(
    client: TestClient,
    world: World,
    scripted: Callable[[Script], Resources],
    finish_script: Callable[..., Script],
):
    scripted(finish_script("Done through the API."))
    created = client.post(
        "/runs",
        json={
            "name": "pilot",
            "country_code": "CA",
            "mode": "step",
            "filter": {"assignment_types": ["find_sources", "find_homepage"]},
        },
    )
    assert created.status_code == 201, created.text
    run = created.json()
    assert (run["mode"], run["status"], run["record_video"]) == ("step", "active", False)
    # The county's sources, and the homepages of the town and the fourteen anchor governments.
    assert run["progress"] == {"by_status": {"held": 16}, "by_result": {}, "cost": "0"}

    listed = client.get("/assignments", params={"run_id": run["id"], "status": "held"}).json()
    assert listed["total"] == 16
    assert len(listed["items"]) == 16
    assert {row["subject"]["kind"] for row in listed["items"]} == {"institution"}
    released = client.post(
        f"/runs/{run['id']}/release", json={"limit": 1, "assignment_type": "find_sources"}
    ).json()
    assert [row["type"] for row in released] == ["find_sources"]
    detail = client.get(f"/assignments/{released[0]['id']}").json()
    assert (detail["status"], detail["result"], detail["summary"]) == (
        "finished",
        "complete",
        "Done through the API.",
    )
    assert detail["sessions"] == 1
    assert detail["finished_at"] is not None
    events = client.get(f"/assignments/{released[0]['id']}/events").json()
    # The first finish left the source types unaccounted for and was refused once.
    assert [event["kind"] for event in events] == [
        "prompt",
        "prompt",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
    ]
    assert events[2]["tool"] == "finish"

    progress = client.get(f"/runs/{run['id']}").json()["progress"]
    assert progress["by_status"] == {"held": 15, "finished": 1}
    assert progress["by_result"] == {"complete": 1}
    assert client.post(f"/runs/{run['id']}/pause").json()["status"] == "paused"
    assert client.post(f"/runs/{run['id']}/pause").status_code == 409
    assert client.post(f"/runs/{run['id']}/resume").json()["status"] == "active"
    assert client.post(f"/runs/{run['id']}/stop").json()["progress"]["by_status"] == {
        "cancelled": 15,
        "finished": 1,
    }
    runs = client.get("/runs").json()
    assert runs["items"][0]["id"] == run["id"]
    assert runs["items"][0]["progress"]["by_status"] == {"cancelled": 15, "finished": 1}
    assert client.get(f"/runs/{uuid.uuid7()}").status_code == 404


def test_the_main_database_lists_no_eval_runs(
    client: TestClient, db: Database, world: World, queue: InlineConnector
):
    """An eval run's row in the main database is the record its scores hang from; its
    assignments are in the eval database, so listed here it would only look empty."""
    assert queue.resources is not None
    jobs = queue.resources.jobs

    async def record_an_eval_run() -> None:
        async with db.session() as session:
            await service.create_run(
                session,
                jobs,
                name="eval",
                country_code="CA",
                mode=RunMode.AUTO,
                is_eval=True,
                seed=False,
            )
            await session.commit()

    db.run(record_an_eval_run)
    runs = client.get("/runs").json()
    assert [row["id"] for row in runs["items"]] == [str(world.run.id)]
    assert runs["total"] == 1


def test_a_reviewers_decision_spawns_into_the_run_it_belongs_to(
    client: TestClient, db: Database, world: World, build: type[Build], queue: InlineConnector
):
    """Approving a candidate institution asks for `find_homepage`; it is created in the run of
    the assignment that raised the question, held because that run is in step mode."""

    async def raise_it() -> tuple[uuid.UUID, uuid.UUID]:
        async with db.session() as session:
            library = await build.candidate_institution(session, world.oakville, "Oakville Library")
            raised_by = await build.open_assignment(
                session, world.run, FIND_INSTITUTIONS, world.oakville.id
            )
            item = await review.raise_review(
                session,
                library,
                rule=review.Rule.AGENT,
                reason="is this a public body?",
                assignment_id=raised_by.id,
            )
            await session.commit()
            return item.id, library.id

    item_id, library_id = db.run(raise_it)
    approved = client.post(f"/review-items/{item_id}/approve", json={})
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["spawn"] == [{"type": "find_homepage", "subject_id": str(library_id)}]
    assert len(body["assignment_ids"]) == 1

    async def check() -> Assignment:
        async with db.session() as session:
            return (
                await session.scalars(
                    select(Assignment).where(Assignment.id == uuid.UUID(body["assignment_ids"][0]))
                )
            ).one()

    spawned = db.run(check)
    assert (spawned.type, spawned.subject_id, spawned.status, spawned.run_id) == (
        FIND_HOMEPAGE,
        library_id,
        AssignmentStatus.HELD,
        world.run.id,
    )


def test_a_decision_whose_run_is_stopped_spawns_into_the_newest_live_run_or_nowhere(
    client: TestClient, db: Database, world: World, build: type[Build], queue: InlineConnector
):
    """The item was raised by an assignment of the world's run, which is stopped since: the
    work goes into the newest run of the country still going; with that one stopped too the
    decision spawns nothing and the work waits for the next run to seed itself."""
    assert queue.resources is not None
    jobs = queue.resources.jobs

    async def raise_in_a_stopped_run(name: str) -> uuid.UUID:
        async with db.session() as session:
            raised_by = await build.open_assignment(
                session, world.run, FIND_INSTITUTIONS, world.oakville.id
            )
            body = await build.candidate_institution(session, world.oakville, name)
            item = await review.raise_review(
                session,
                body,
                rule=review.Rule.AGENT,
                reason="is this a public body?",
                assignment_id=raised_by.id,
            )
            run_row = await session.get_one(Run, world.run.id)
            if run_row.status is not RunStatus.STOPPED:
                await service.stop_run(session, run_row)
            await session.commit()
            return item.id

    async def a_newer_run() -> Run:
        async with db.session() as session:
            newer = await service.create_run(
                session, jobs, name="newer", country_code="CA", mode=RunMode.STEP, seed=False
            )
            await session.commit()
            return newer

    item_id = db.run(raise_in_a_stopped_run, "Oakville Archive")
    newer = db.run(a_newer_run)
    body = client.post(f"/review-items/{item_id}/approve", json={}).json()
    assert [row["type"] for row in body["spawn"]] == ["find_homepage"]
    assert len(body["assignment_ids"]) == 1

    async def read(assignment_id: str) -> Assignment:
        async with db.session() as session:
            return await session.get_one(Assignment, uuid.UUID(assignment_id))

    spawned = db.run(read, body["assignment_ids"][0])
    assert (spawned.run_id, spawned.status) == (newer.id, AssignmentStatus.HELD)

    async def stop_the_newer_run() -> None:
        async with db.session() as session:
            await service.stop_run(session, await session.get_one(Run, newer.id))
            await session.commit()

    db.run(stop_the_newer_run)
    item_id = db.run(raise_in_a_stopped_run, "Oakville Museum")
    body = client.post(f"/review-items/{item_id}/approve", json={}).json()
    assert [row["type"] for row in body["spawn"]] == ["find_homepage"]
    assert body["assignment_ids"] == []


# --- Money ---


def spend(
    db: Database, assignment: Assignment, *, searches: int = 0, output_tokens: int = 0
) -> None:
    """Priced usage on the assignment: `searches` Brave requests at $0.005 each and one Luna
    call of a million uncached input tokens ($0.10) plus `output_tokens` at $0.50 per million."""

    async def record() -> None:
        async with db.session() as session:
            for _ in range(searches):
                await service.record_usage(
                    session,
                    assignment_id=assignment.id,
                    kind=UsageKind.SEARCH,
                    provider="brave",
                    purpose="find_homepage",
                    units=1,
                )
            await service.record_usage(
                session,
                assignment_id=assignment.id,
                kind=UsageKind.MODEL,
                provider="gpt-6-luna",
                purpose=assignment.type.value,
                units=1_000_000 + output_tokens,
                output_units=output_tokens,
            )
            await session.commit()

    db.run(record)


def test_progress_sums_each_runs_cost_alone(
    db: Database, world: World, build: type[Build], queue: InlineConnector
):
    """Two runs with usage keep their costs apart, a run with nothing spent reads zero, and
    `by_result` has an entry only for assignments that have ended."""
    assert queue.resources is not None
    jobs = queue.resources.jobs

    async def scenario() -> tuple[Run, Run, Assignment, Assignment]:
        async with db.session() as session:
            second = await service.create_run(
                session, jobs, name="second", country_code="CA", mode=RunMode.STEP, seed=False
            )
            empty = await service.create_run(
                session, jobs, name="empty", country_code="CA", mode=RunMode.STEP, seed=False
            )
            first_work = await build.open_assignment(
                session, world.run, FIND_SOURCES, world.county.id, status=AssignmentStatus.RUNNING
            )
            second_work = await build.open_assignment(
                session, second, FIND_HOMEPAGE, world.town.id, status=AssignmentStatus.RUNNING
            )
            service.lifecycle.finish(second_work, AssignmentResult.COMPLETE, summary="done")
            await session.commit()
            return second, empty, first_work, second_work

    second, empty, first_work, second_work = db.run(scenario)
    # $0.10 of Luna in the first run; two searches and $0.10 plus $0.05 of output in the second.
    spend(db, first_work)
    spend(db, second_work, searches=2, output_tokens=100_000)

    async def read() -> dict[uuid.UUID, service.Progress]:
        async with db.session() as session:
            return await service.progress_many(session, [world.run.id, second.id, empty.id])

    found = db.run(read)
    assert found[world.run.id] == service.Progress(
        by_status={AssignmentStatus.RUNNING: 1}, by_result={}, cost=Decimal("0.100000")
    )
    assert found[second.id] == service.Progress(
        by_status={AssignmentStatus.FINISHED: 1},
        by_result={AssignmentResult.COMPLETE: 1},
        cost=Decimal("0.160000"),
    )
    assert found[empty.id] == service.Progress(by_status={}, by_result={}, cost=Decimal(0))


def test_an_assignments_detail_carries_its_cost(
    client: TestClient, db: Database, world: World, build: type[Build]
):
    """The detail's `cost` is the sum of the assignment's own usage rows, and the run's
    progress sums every assignment of the run: the one priced here and a sibling with a search
    of its own."""

    async def scenario() -> tuple[Assignment, Assignment]:
        async with db.session() as session:
            priced = await build.open_assignment(
                session, world.run, FIND_HOMEPAGE, world.town.id, status=AssignmentStatus.RUNNING
            )
            sibling = await build.open_assignment(
                session, world.run, FIND_SOURCES, world.county.id, status=AssignmentStatus.RUNNING
            )
            await session.commit()
            return priced, sibling

    priced, sibling = db.run(scenario)
    spend(db, priced, searches=1, output_tokens=100_000)
    spend(db, sibling, searches=3)
    detail = client.get(f"/assignments/{priced.id}").json()
    # One search ($0.005), a million uncached input ($0.10) and 100k output ($0.05).
    assert detail["cost"] == "0.155000"
    assert client.get(f"/assignments/{sibling.id}").json()["cost"] == "0.115000"
    progress = client.get(f"/runs/{world.run.id}").json()["progress"]
    assert progress["cost"] == "0.270000"
    listed = client.get("/runs").json()["items"]
    assert [row["progress"]["cost"] for row in listed] == ["0.270000"]
