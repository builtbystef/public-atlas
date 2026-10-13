import importlib
import logging
import pkgutil
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from procrastinate import PsycopgConnector, RetryStrategy
from procrastinate.schema import SchemaManager
from sqlalchemy import text

import public_atlas
from public_atlas.config import Settings
from public_atlas.db.base import utcnow
from public_atlas.jobs import TASK_MODULES, conninfo, create_app, registry
from public_atlas.jobs.purge import purge_old_jobs
from public_atlas.jobs.stalled import retry_stalled
from public_atlas.jobs.tasks import RETRY_ON_ERROR, AnyTask, defer, retries_left, task
from public_atlas.resources import Resources

if TYPE_CHECKING:
    from tests.integration.conftest import Database, InlineConnector

# What the abandoned hook of `flaky` was handed, per test.
SETTLED: list[dict[str, object]] = []


async def settle(res: Resources, **kwargs: object) -> None:
    SETTLED.append(kwargs)


@task("tests.flaky", retry=RETRY_ON_ERROR, abandoned=settle)
async def flaky(res: Resources, snapshot_id: str | None = None) -> None:
    """A job that fails on a flaky peer, as the assignment runner does: five tries, and a
    hook to settle what it left when a worker dies on the last."""


@task("tests.forever", retry=RetryStrategy())
async def forever(res: Resources) -> None:
    """A job retried for good."""


async def run_now(db: Database, queue: InlineConnector, task: AnyTask) -> int:
    """Defer `task` from a session on the test transaction; the inline worker runs it."""
    assert queue.resources is not None
    async with db.session() as session:
        return await defer(queue.resources.jobs, session, task)


def test_the_app_queues_through_the_database():
    settings = Settings(database_url="postgresql+psycopg://u:p@db:5432/public_atlas")
    assert conninfo(settings) == "postgresql://u:p@db:5432/public_atlas"
    created = create_app(settings)
    assert isinstance(created.connector, PsycopgConnector)
    assert created.import_paths == TASK_MODULES
    assert created.worker_defaults == {"delete_jobs": "successful"}


def test_every_jobs_module_in_the_tree_is_registered():
    """A task in a `jobs.py` the worker does not import is never run."""
    found = {
        module.name
        for module in pkgutil.walk_packages(public_atlas.__path__, "public_atlas.")
        if module.name.endswith(".jobs") and not module.ispkg
    }
    listed = {module for module in TASK_MODULES if module.endswith(".jobs")}
    assert found == listed
    assert set(TASK_MODULES) - listed == {"public_atlas.jobs.purge", "public_atlas.jobs.stalled"}
    assert "public_atlas.modules.evidence.jobs" in listed


def test_every_task_is_on_its_queue():
    """The assignment runner on the `assignment` queue, the parser on `parse`, everything else
    on `default`: a worker serving one queue gets those jobs and no other."""
    for module in TASK_MODULES:
        importlib.import_module(module)
    ours = {
        name: registered.queue
        for name, registered in registry.tasks.items()
        if not name.startswith(("builtin:", "tests."))
    }
    assert ours == {
        "agent.purge_events": "default",
        "agent.purge_videos": "default",
        "assignments.run_assignment": "assignment",
        "evidence.parse_snapshot": "parse",
        "jobs.purge_old_jobs": "default",
        "jobs.retry_stalled": "default",
    }


def test_a_job_knows_whether_a_failure_would_be_retried():
    """Five tries for a job that fails on a flaky peer: after four, one more; after five, none.
    A strategy with no cap retries for good; a task with no strategy, or none registered,
    is never retried."""
    assert retries_left(flaky, 0)
    assert retries_left(flaky, 4)
    assert not retries_left(flaky, 5)
    assert retries_left(forever, 100)
    assert not retries_left(purge_old_jobs, 0)
    assert not retries_left(None, 0)


def test_a_job_is_queued_in_the_transaction_of_the_rows_it_is_about(
    db: Database, settings: Settings
):
    """Through the real connector (the in-memory one ignores the connection): the job row goes
    on the session's own connection, so it is rolled back, or committed, with the rest. The
    queue's tables are created in the test transaction and go with it."""
    real = create_app(settings)

    @real.task(name="tests.transactional")
    async def noop() -> None:
        pass

    async def scenario() -> tuple[int, int, list[int]]:
        if await db.connection.scalar(text("SELECT to_regclass('procrastinate_jobs')")) is None:
            await db.connection.exec_driver_sql(SchemaManager.get_schema().replace("%", "%%"))
        async with db.session() as session:
            rolled_back = await defer(real, session, noop)
            await session.rollback()
        async with db.session() as session:
            committed = await defer(real, session, noop)
            await session.commit()
        rows = await db.connection.scalars(
            text("SELECT id FROM procrastinate_jobs WHERE task_name = 'tests.transactional'")
        )
        return rolled_back, committed, list(rows)

    rolled_back, committed, rows = db.run(scenario)
    assert rolled_back != committed
    assert rows == [committed]


def job_row(
    queue: InlineConnector,
    job_id: int,
    *,
    status: str,
    worker_id: int | None,
    attempts: int,
    at: datetime,
    args: dict[str, object] | None = None,
) -> None:
    """A job as the queue's table holds one, with the event that put it in `status` at `at`."""
    queue.jobs[job_id] = {
        "id": job_id,
        "status": status,
        "task_name": "tests.flaky",
        "priority": 0,
        "lock": None,
        "queueing_lock": None,
        "args": args or {},
        "scheduled_at": None,
        "queue_name": "default",
        "attempts": attempts,
        "worker_id": worker_id,
        "abort_requested": False,
    }
    queue.events[job_id] = [{"type": "started" if status == "doing" else status, "at": at}]


def test_retry_stalled_requeues_the_jobs_of_a_dead_worker_and_fails_those_out_of_retries(
    db: Database, queue: InlineConnector
):
    """A worker is dead when its heartbeat is over 30 seconds old. A job it left running goes
    back to the queue when its task has retries left (four of five attempts made; here, run at
    once by the same worker); one out of retries (five of five) is failed and its task's
    `abandoned` hook settles what it left; one held by a worker heard from 29 seconds ago is
    left alone."""
    SETTLED.clear()
    dead, live = 1, 2
    now = utcnow()
    queue.workers = {dead: now - timedelta(seconds=31), live: now - timedelta(seconds=29)}
    started = now - timedelta(minutes=5)
    job_row(queue, 10, status="doing", worker_id=dead, attempts=4, at=started)
    job_row(queue, 11, status="doing", worker_id=live, attempts=4, at=started)
    job_row(
        queue,
        12,
        status="doing",
        worker_id=dead,
        attempts=5,
        at=started,
        args={"snapshot_id": "abc", "trace": {}},
    )

    db.run(run_now, db, queue, retry_stalled)
    assert [e["type"] for e in queue.events[10]] == [
        "started",
        "scheduled",
        "deferred_for_retry",
        "started",
        "succeeded",
    ]
    assert queue.jobs[10]["status"] == "succeeded"
    assert (queue.jobs[11]["status"], [e["type"] for e in queue.events[11]]) == (
        "doing",
        ["started"],
    )
    assert (queue.jobs[12]["status"], [e["type"] for e in queue.events[12]]) == (
        "failed",
        ["started", "failed"],
    )
    assert SETTLED == [{"snapshot_id": "abc"}]


def test_the_purge_task_runs_with_the_worker_resources_and_drops_old_failed_jobs(
    db: Database, queue: InlineConnector, caplog: pytest.LogCaptureFixture
):
    """A job that failed for good is kept seven days for inspection: one that failed eight
    days ago goes, one that failed six days ago stays."""
    now = utcnow()
    job_row(queue, 10, status="failed", worker_id=None, attempts=5, at=now - timedelta(days=8))
    job_row(queue, 11, status="failed", worker_id=None, attempts=5, at=now - timedelta(days=6))
    with caplog.at_level(logging.INFO, logger="public_atlas.jobs.purge"):
        db.run(run_now, db, queue, purge_old_jobs)
    assert "Purged failed jobs older than 7 days" in caplog.text
    assert 10 not in queue.jobs
    assert queue.jobs[11]["status"] == "failed"
