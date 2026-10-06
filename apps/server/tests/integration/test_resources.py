"""`build_resources` is the one door to the database, the store and the queue, and it takes its
settings as an argument."""

import asyncio
import os
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from procrastinate.testing import InMemoryConnector
from sqlalchemy import text

from public_atlas.config import Settings
from public_atlas.integrations.parse import MemoryParser
from public_atlas.integrations.storage.memory import MemoryObjectStore
from public_atlas.jobs.purge import purge_old_jobs
from public_atlas.jobs.stalled import retry_stalled
from public_atlas.resources import build_resources, resources_of, worker_context

if TYPE_CHECKING:
    from procrastinate import JobContext


def test_resources_are_built_from_the_settings_alone(settings: Settings, test_database_name: str):
    """The settings name the test database; no environment variable is read or written."""
    environment_before = dict(os.environ)
    store = MemoryObjectStore()

    async def scenario() -> tuple[str | None, str]:
        async with build_resources(
            settings, object_store=store, jobs_connector=InMemoryConnector()
        ) as resources:
            assert resources.settings is settings
            assert resources.object_store is store
            # No search engine and no model key are configured for the tests, and the parser
            # is the settings'.
            assert resources.searcher is None
            assert resources.models is None
            assert isinstance(resources.parser, MemoryParser)
            async with resources.session() as session:
                database = (await session.execute(text("SELECT current_database()"))).scalar()
            return database, str(resources.engine.url.database)

    database, engine_database = asyncio.run(scenario())
    assert database == test_database_name
    assert engine_database == test_database_name
    assert dict(os.environ) == environment_before


def test_the_job_queue_is_built_with_every_task_registered(settings: Settings):
    async def scenario() -> tuple[set[str], dict[str, str]]:
        async with build_resources(
            settings, object_store=MemoryObjectStore(), jobs_connector=InMemoryConnector()
        ) as resources:
            jobs = resources.jobs
            periodic = {
                name: task.cron for (name, _), task in jobs.periodic_registry.periodic_tasks.items()
            }
            return {name for name in jobs.tasks if not name.startswith("builtin:")}, periodic

    names, periodic = asyncio.run(scenario())
    # Other test modules register tasks of their own on the same registry.
    assert {
        "jobs.purge_old_jobs",
        "jobs.retry_stalled",
        "assignments.run_assignment",
        "evidence.parse_snapshot",
    } <= names
    assert periodic == {
        "jobs.purge_old_jobs": "0 * * * *",
        "jobs.retry_stalled": "*/10 * * * *",
        "agent.purge_videos": "0 3 * * *",
        "agent.purge_events": "30 3 * * *",
    }
    assert purge_old_jobs.name == "jobs.purge_old_jobs"
    assert retry_stalled.queue == "default"


def test_a_worker_context_carries_the_resources(settings: Settings):
    async def scenario() -> bool:
        async with build_resources(
            settings, object_store=MemoryObjectStore(), jobs_connector=InMemoryConnector()
        ) as resources:
            # What a worker started with `worker_context` hands each job.
            context = cast(
                "JobContext", SimpleNamespace(additional_context=worker_context(resources))
            )
            return resources_of(context) is resources

    assert asyncio.run(scenario())
