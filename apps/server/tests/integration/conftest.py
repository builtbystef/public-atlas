"""Fixtures for the app client, the test transaction and the inline job queue."""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from procrastinate.testing import InMemoryConnector
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from public_atlas.config import Settings
from public_atlas.db.models import Base
from public_atlas.dependencies import get_session
from public_atlas.integrations.storage.memory import MemoryObjectStore
from public_atlas.main import create_app
from public_atlas.resources import Resources, worker_context

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterator

    from anyio.from_thread import BlockingPortal
    from fastapi import FastAPI
    from procrastinate.testing import JobRow
    from procrastinate.types import JobToDefer
    from sqlalchemy.engine import URL


@pytest.fixture(scope="session", autouse=True)
def test_database(configured_url: URL, test_database_name: str) -> None:
    """Create the test database on the configured server if it is not there yet."""
    # CREATE DATABASE cannot run inside a transaction, hence autocommit.
    engine = create_engine(configured_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        with engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": test_database_name},
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{test_database_name}"'))
    except OperationalError as exc:
        pytest.fail(f"PostgreSQL is not reachable at {engine.url}. Run `vp run infra:up`. ({exc})")
    finally:
        engine.dispose()


@pytest.fixture
def engine(settings: Settings) -> AsyncEngine:
    # NullPool: each test runs its own event loop, and a pooled connection must not cross one.
    return create_async_engine(str(settings.database_url), poolclass=NullPool)


@pytest.fixture
def object_store() -> MemoryObjectStore:
    return MemoryObjectStore()


class InlineConnector(InMemoryConnector):
    """Runs a job as soon as it is deferred, in the deferring request, by a worker started with
    `resources`. A job that does not succeed fails the request."""

    def __init__(self) -> None:
        super().__init__()
        self.resources: Resources | None = None

    async def defer_jobs_all(self, jobs: list[JobToDefer]) -> list[JobRow]:
        rows = await super().defer_jobs_all(jobs)
        assert self.resources is not None, "deferred before the app client was set up"
        await self.resources.jobs.run_worker_async(
            wait=False,
            install_signal_handlers=False,
            listen_notify=False,
            delete_jobs="never",
            additional_context=worker_context(self.resources),
        )
        for row in rows:
            job = self.jobs[row["id"]]
            assert job["status"] == "succeeded", job
        return rows


@pytest.fixture
def queue() -> InlineConnector:
    """The in-memory job queue the app is built on."""
    return InlineConnector()


@pytest.fixture
def app(settings: Settings, object_store: MemoryObjectStore, queue: InlineConnector) -> FastAPI:
    """The API over the test database, with an in-memory store and job queue."""
    return create_app(settings, object_store=object_store, jobs_connector=queue)


@pytest.fixture
def app_client(app: FastAPI, queue: InlineConnector) -> Iterator[TestClient]:
    """The started app: its resources are built and the inline jobs run with them."""
    with TestClient(app) as client:
        resources: Resources = client.app_state["resources"]
        queue.resources = resources
        # A worker fires a periodic task on start when its last tick was less than this many
        # seconds ago (ten minutes by default). The tests start a worker per deferred job, so
        # never.
        resources.jobs.periodic_defaults["max_delay"] = 0
        yield client


@dataclass
class Database:
    """The test transaction. It lives on the app's event loop, so use `run` to reach it."""

    portal: BlockingPortal
    connection: AsyncConnection

    def run[T](self, func: Callable[..., Awaitable[T]], *args: object) -> T:
        return self.portal.call(func, *args)

    def session(self) -> AsyncSession:
        # commit() releases a savepoint; the fixture rolls back the outer transaction.
        return AsyncSession(
            bind=self.connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )

    async def get_session(self) -> AsyncIterator[AsyncSession]:
        """Drop-in for `public_atlas.dependencies.get_session`."""
        async with self.session() as session:
            yield session


async def _begin(engine: AsyncEngine) -> AsyncConnection:
    try:
        connection = await engine.connect()
    except OperationalError as exc:
        pytest.fail(f"PostgreSQL is not reachable at {engine.url}. Run `vp run infra:up`. ({exc})")
    await connection.begin()
    await connection.run_sync(Base.metadata.create_all)
    return connection


async def _end(connection: AsyncConnection, engine: AsyncEngine) -> None:
    await connection.rollback()
    await connection.close()
    await engine.dispose()


@pytest.fixture
def db(
    app: FastAPI, app_client: TestClient, engine: AsyncEngine, queue: InlineConnector
) -> Iterator[Database]:
    """The app's sessions and the jobs' join this transaction."""
    assert app_client.portal is not None
    connection = app_client.portal.call(_begin, engine)
    database = Database(app_client.portal, connection)
    app.dependency_overrides[get_session] = database.get_session
    assert queue.resources is not None
    queue.resources = replace(queue.resources, session_factory=database.session)
    try:
        yield database
    finally:
        database.run(_end, connection, engine)


@pytest.fixture
def client(app_client: TestClient, db: Database) -> TestClient:
    """`app_client` with the `db` transaction."""
    return app_client
