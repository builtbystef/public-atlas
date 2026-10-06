"""Runs (spec section 7.1) and spawning (section 7.3): a run seeds itself with the work due for
its filter, held in step mode and queued in auto mode; releasing queues held work a few at a
time; a paused run's job is put back and its assignment stays queued; stop cancels what is held
or queued; a spawn obeys the run's mode and filter and never doubles open work; and a reviewer's
decision spawns into the run it belongs to."""

import uuid
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
    institutions are due. The town and the province's government have none: their homepages
    are due. Nothing is queued in step mode, and a second run finds the work open already."""
    run, rows = db.run(create, db, queue)
    assert work(rows) == {
        (FIND_SOURCES, world.county.id),
        (FIND_INSTITUTIONS, world.elm.id),
        (FIND_HOMEPAGE, world.town.id),
        (FIND_HOMEPAGE, world.ontario.government_institution_id),
    }
    assert {row.status for row in rows} == {AssignmentStatus.HELD}
    assert all(row.run_id == run.id and row.budget_requests > 0 for row in rows)
    assert not any(job["task_name"] == service.RUN_ASSIGNMENT_TASK for job in queue.jobs.values())
    _, again = db.run(create, db, queue)
    assert again == []


def test_the_filter_bounds_what_a_run_seeds(db: Database, world: World, queue: InlineConnector):
    _, by_level = db.run(create, db, queue, RunFilter(administrative_levels=["municipality"]))
    assert work(by_level) == {(FIND_HOMEPAGE, world.town.id)}

    async def stop_it() -> None:
        async with db.session() as session:
            for run in await service.list_runs(session):
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
    assert by_status == {AssignmentStatus.HELD: 3, AssignmentStatus.FINISHED: 1}


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
    run, rows = db.run(create, db, queue)

    async def stop() -> tuple[list[Assignment], list[Assignment], list[Assignment]]:
        assert queue.resources is not None
        async with db.session() as session:
            run_row = await service.get_run(session, run.id)
            cancelled = await service.stop_run(session, run_row)
            with pytest.raises(ConflictError, match="stopped"):
                await service.stop_run(session, run_row)
            with pytest.raises(ConflictError, match="stopped"):
                await service.release(session, queue.resources.jobs, run_row)
            spawned = await service.spawn(
                session, queue.resources.jobs, run_row, [Spawn(FIND_HOMEPAGE, world.town.id)]
            )
            await session.commit()
            return cancelled, spawned, await service.list_assignments(session, run_id=run.id)

    cancelled, spawned, after = db.run(stop)
    assert len(cancelled) == len(rows) == 4
    assert spawned == []
    assert {row.status for row in after} == {AssignmentStatus.CANCELLED}


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
    assert run["progress"] == {"by_status": {"held": 3}, "by_result": {}, "cost": "0"}

    listed = client.get("/assignments", params={"run_id": run["id"], "status": "held"}).json()
    assert len(listed) == 3
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
    assert [event["kind"] for event in events] == [
        "prompt",
        "prompt",
        "tool_call",
        "tool_result",
    ]
    assert events[2]["tool"] == "finish"

    progress = client.get(f"/runs/{run['id']}").json()["progress"]
    assert progress["by_status"] == {"held": 2, "finished": 1}
    assert progress["by_result"] == {"complete": 1}
    assert client.post(f"/runs/{run['id']}/pause").json()["status"] == "paused"
    assert client.post(f"/runs/{run['id']}/pause").status_code == 409
    assert client.post(f"/runs/{run['id']}/resume").json()["status"] == "active"
    assert client.post(f"/runs/{run['id']}/stop").json()["progress"]["by_status"] == {
        "cancelled": 2,
        "finished": 1,
    }
    assert next(row["id"] for row in client.get("/runs").json()) == run["id"]
    assert client.get(f"/runs/{uuid.uuid7()}").status_code == 404


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


def test_a_decision_with_no_run_going_spawns_nothing(
    client: TestClient, db: Database, world: World, build: type[Build]
):
    async def raise_it() -> uuid.UUID:
        async with db.session() as session:
            await service.stop_run(session, await session.get_one(Run, world.run.id))
            archive = await build.candidate_institution(session, world.oakville, "Oakville Archive")
            item = await review.raise_review(
                session, archive, rule=review.Rule.AGENT, reason="unsure"
            )
            await session.commit()
            return item.id

    item_id = db.run(raise_it)
    body = client.post(f"/review-items/{item_id}/approve", json={}).json()
    assert len(body["spawn"]) == 1
    assert body["assignment_ids"] == []
