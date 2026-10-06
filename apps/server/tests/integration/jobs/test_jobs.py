import logging
import pkgutil
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from procrastinate import PsycopgConnector, RetryStrategy
from procrastinate.schema import SchemaManager
from sqlalchemy import text

import public_atlas
from public_atlas.config import Settings
from public_atlas.db.base import utcnow
from public_atlas.jobs import TASK_MODULES, conninfo, create_app
from public_atlas.jobs.purge import purge_old_jobs
from public_atlas.jobs.stalled import retry_stalled
from public_atlas.jobs.tasks import ABANDONED, RETRY_ON_ERROR, AnyTask, defer

if TYPE_CHECKING:
    from tests.integration.conftest import Database, InlineConnector

    from public_atlas.resources import Resources


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


def test_the_platform_tasks_carry_their_retry_and_queue():
    assert isinstance(RETRY_ON_ERROR, RetryStrategy)
    assert RETRY_ON_ERROR.max_attempts == 5
    assert purge_old_jobs.queue == "default"
    assert retry_stalled.queue == "default"


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


def stalled_job(job_id: int, task_name: str, worker_id: int, attempts: int) -> dict[str, object]:
    return {
        "id": job_id,
        "status": "doing",
        "task_name": task_name,
        "priority": 0,
        "lock": None,
        "queueing_lock": None,
        "args": {},
        "scheduled_at": None,
        "queue_name": "default",
        "attempts": attempts,
        "worker_id": worker_id,
        "abort_requested": False,
    }


def test_retry_stalled_requeues_the_jobs_of_a_dead_worker_and_fails_those_out_of_retries(
    db: Database, queue: InlineConnector, monkeypatch: pytest.MonkeyPatch
):
    """A job left running by a worker whose heartbeat stopped goes back to the queue when its
    task has retries left (and, here, is run at once by the same worker); one out of retries
    is failed and its task's `abandoned` hook settles what it left; one held by a live worker
    is left alone."""
    settled: list[dict[str, object]] = []

    async def settle(res: Resources, **kwargs: object) -> None:
        settled.append(kwargs)

    monkeypatch.setitem(ABANDONED, "tests.abandoned", settle)
    dead, live = 1, 2
    long_ago = utcnow() - timedelta(minutes=5)
    queue.workers = {dead: long_ago, live: utcnow()}
    queue.jobs[10] = stalled_job(10, "jobs.retry_stalled", dead, attempts=0)
    queue.jobs[11] = stalled_job(11, "jobs.retry_stalled", live, attempts=0)
    queue.jobs[12] = stalled_job(12, "tests.abandoned", dead, attempts=3)
    queue.jobs[12]["args"] = {"snapshot_id": "abc", "trace": {}}
    for job_id in (10, 11, 12):
        queue.events[job_id] = [{"type": "started", "at": long_ago}]
    # `retry_stalled` itself retries on error, so the dead worker's run of it is requeued.
    monkeypatch.setattr(retry_stalled, "retry_strategy", RETRY_ON_ERROR)

    assert db.run(run_now, db, queue, retry_stalled) > 0
    assert [e["type"] for e in queue.events[10]] == [
        "started",
        "scheduled",
        "deferred_for_retry",
        "started",
        "succeeded",
    ]
    assert queue.jobs[10]["status"] == "succeeded"
    assert queue.jobs[11]["status"] == "doing"
    assert queue.jobs[12]["status"] == "failed"
    assert settled == [{"snapshot_id": "abc"}]


def test_the_purge_task_runs_with_the_worker_resources_and_drops_old_failed_jobs(
    db: Database, queue: InlineConnector, caplog: pytest.LogCaptureFixture
):
    failed_long_ago = {
        "id": 10,
        "status": "failed",
        "task_name": "jobs.retry_stalled",
        "priority": 0,
        "lock": None,
        "queueing_lock": None,
        "args": {},
        "scheduled_at": None,
        "queue_name": "default",
        "attempts": 5,
        "worker_id": None,
        "abort_requested": False,
    }
    queue.jobs[10] = failed_long_ago
    queue.events[10] = [{"type": "failed", "at": utcnow() - timedelta(days=30)}]
    with caplog.at_level(logging.INFO, logger="public_atlas.jobs.purge"):
        db.run(run_now, db, queue, purge_old_jobs)
    assert "Purged failed jobs older than 7 days" in caplog.text
    assert 10 not in queue.jobs
