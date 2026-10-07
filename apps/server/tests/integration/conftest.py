"""Fixtures for the app client, the test transaction, the inline job queue, an assignment to
work in, and the local site the browser and `read_file` tests fetch from."""

import threading
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, ClassVar, Self

import pytest
from fastapi.testclient import TestClient
from procrastinate.testing import InMemoryConnector
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from public_atlas.config import Settings
from public_atlas.db import migrations
from public_atlas.db.models import Base
from public_atlas.dependencies import get_session
from public_atlas.integrations.parse import MemoryParser
from public_atlas.integrations.storage.memory import MemoryObjectStore
from public_atlas.main import create_app
from public_atlas.modules.assignments.models import (
    Assignment,
    AssignmentStatus,
    AssignmentType,
    Run,
    RunMode,
)
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import canada
from public_atlas.modules.graph.models import Place
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
            if job["status"] == "todo" and job["scheduled_at"]:
                # Put back for later (a paused run's assignment): not run now.
                continue
            assert job["status"] == "succeeded", job
        return rows


@pytest.fixture
def queue() -> InlineConnector:
    """The in-memory job queue the app is built on."""
    return InlineConnector()


@pytest.fixture
def app(settings: Settings, object_store: MemoryObjectStore, queue: InlineConnector) -> FastAPI:
    """The API over the test database, with an in-memory store, job queue and parser."""
    return create_app(
        settings, object_store=object_store, jobs_connector=queue, parser=MemoryParser()
    )


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
        """Run `func` on the app's event loop. A `pytest.raises` that does not raise fails with
        a `BaseException`, which would stop the portal and leave the transaction open for every
        test after it; it is turned into an ordinary failure here."""

        async def guarded() -> T:
            try:
                return await func(*args)
            except pytest.fail.Exception as exc:
                raise AssertionError(str(exc)) from None

        return self.portal.call(guarded)

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
    # Stamped at head, as a migrated database is: the eval service checks before it starts.
    await connection.run_sync(migrations.stamp_head)
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


# --- An assignment to work in ---


async def _make_assignment(db: Database) -> Assignment:
    """Canada seeded, a step-mode run on it, and one running `find_sources` assignment whose
    subject is the Ontario place: what the capture hook and `read_file` record against."""
    async with db.session() as session:
        await countries.seed(session, canada.SEED)
        ontario = (
            await session.scalars(select(Place).where(Place.name == "Ontario").limit(1))
        ).one()
        run = Run(name="test", country_code="CA", mode=RunMode.STEP)
        session.add(run)
        await session.flush()
        assignment = Assignment(
            run_id=run.id,
            type=AssignmentType.FIND_SOURCES,
            subject_id=ontario.id,
            status=AssignmentStatus.RUNNING,
            budget_requests=100,
            budget_tokens=1_000_000,
        )
        session.add(assignment)
        await session.commit()
        return assignment


@pytest.fixture
def assignment(db: Database) -> Assignment:
    return db.run(_make_assignment, db)


@pytest.fixture
def another_assignment(db: Database, assignment: Assignment) -> Assignment:
    """A second assignment on the same subject, so a file one fetched can be read by another."""

    async def make() -> Assignment:
        async with db.session() as session:
            other = Assignment(
                run_id=assignment.run_id,
                type=AssignmentType.FIND_HOMEPAGE,
                subject_id=assignment.subject_id,
                status=AssignmentStatus.RUNNING,
                budget_requests=100,
                budget_tokens=1_000_000,
            )
            session.add(other)
            await session.commit()
            return other

    return db.run(make)


# --- A local site for the browser and read_file ---

# Content types with a meaning of their own: the page's "body" is the URL it redirects to, or
# the body of a 429 answer, as a host that throttles sends.
REDIRECT = "redirect"
THROTTLED = "throttled"


class _Handler(BaseHTTPRequestHandler):
    pages: ClassVar[dict[str, tuple[str, bytes]]] = {}
    # Every path asked for, so a test can check what the browser did not fetch.
    requested: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        self.requested.append(path)
        if path not in self.pages:
            self.send_response(404)
            self.end_headers()
            return
        content_type, body = self.pages[path]
        if content_type == REDIRECT:
            self.send_response(302)
            self.send_header("Location", body.decode())
            self.end_headers()
            return
        if content_type == THROTTLED:
            self.send_response(429)
            self.send_header("Retry-After", "7")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002, ARG002 - the base signature
        return


class FixtureSite:
    """Pages served on 127.0.0.1, the host the tests allow, and reachable as `localhost` too, a
    host the allowlist does not name."""

    def __init__(self, pages: dict[str, tuple[str, bytes]]) -> None:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        _Handler.pages = pages
        _Handler.requested = []
        self.requested = _Handler.requested
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def allowed(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def outside(self) -> str:
        return f"http://localhost:{self.port}"

    def __enter__(self) -> Self:
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


INDEX_HTML = b"""<!doctype html><html><head><title>Fixture Region</title></head>
<body><h1>Regional Municipality of Fixture</h1>
<p>Agencies: <a id="agency" href="/agency">Fixture Transit Commission</a></p>
<p>Hospital: <a id="outside" href="http://localhost:{port}/hospital">Fixture Hospital</a></p>
<p><a href="/budget.pdf">Budget 2026 (PDF)</a> <a href="/notes.txt">Notes</a></p>
<img src="/logo.png" alt="crest">
</body></html>"""
THROTTLE_HTML = b"""<html><body><p>We are receiving a higher volume of requests from your
network than normal and have temporarily limited it.</p></body></html>"""
CHALLENGE_HTML = b"""<!doctype html><html><head><title>Pardon Our Interruption</title></head>
<body><h1>Pardon Our Interruption</h1><p>As you were browsing something about your browser
made us think you were a bot.</p></body></html>"""
AGENCY_HTML = b"""<!doctype html><html><head><title>Fixture Transit Commission</title></head>
<body><h1>Fixture Transit Commission</h1><p>Board meetings and procurement.</p></body></html>"""
# A meetings page that adds its portal link by script after load and embeds the portal in a
# frame, as ottawa.ca and oakville.ca do with eSCRIBE.
MEETINGS_HTML = b"""<!doctype html><html><head><title>Fixture Meetings</title></head>
<body><h1>Council meetings</h1><iframe src="/portal"></iframe>
<script>setTimeout(() => { const a = document.createElement("a"); a.href = "/late";
a.textContent = "Meetings portal"; document.body.appendChild(a); }, 300);</script>
</body></html>"""
PORTAL_HTML = b"""<!doctype html><html><body>
<a href="meeting?id=7">Council 2026-09-30</a></body></html>"""
HOSPITAL_HTML = b"""<!doctype html><html><head><title>Fixture Hospital</title></head>
<body><h1>Fixture Hospital</h1><p>SECRET: this text must never reach the agent.</p></body></html>"""


@pytest.fixture
def site() -> Iterator[FixtureSite]:
    pages = {
        "/": ("text/html; charset=utf-8", INDEX_HTML),
        "/agency": ("text/html; charset=utf-8", AGENCY_HTML),
        "/hospital": ("text/html; charset=utf-8", HOSPITAL_HTML),
        "/meetings": ("text/html; charset=utf-8", MEETINGS_HTML),
        "/portal": ("text/html; charset=utf-8", PORTAL_HTML),
        "/budget.pdf": ("application/pdf", b"%PDF-1.4 Operating budget 2026\fCapital plan page"),
        "/notes.txt": ("text/plain", b"Council notes: tenders close Friday."),
        "/legacy.doc": ("application/msword", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 old"),
        "/robots.txt": ("text/plain", b"User-agent: PublicAtlas\nDisallow: /private\n"),
        "/private": ("text/html; charset=utf-8", b"<html><body>private</body></html>"),
        # A moved file and a moved page, and one of each that redirects off the allowlist.
        "/old-budget.pdf": (REDIRECT, b"/budget.pdf"),
        "/leak.pdf": (REDIRECT, b"http://localhost:{port}/hospital"),
        "/moved": (REDIRECT, b"/agency"),
        "/gone": (REDIRECT, b"http://localhost:{port}/hospital"),
        "/logo.png": ("image/png", b"\x89PNG not really"),
        "/busy": (THROTTLED, THROTTLE_HTML),
        # A file whose site answers a bot check with status 200 instead of the bytes.
        "/guarded.pdf": ("text/html; charset=utf-8", CHALLENGE_HTML),
    }
    with FixtureSite(pages) as running:
        port = str(running.port).encode()
        _Handler.pages["/"] = ("text/html; charset=utf-8", INDEX_HTML.replace(b"{port}", port))
        _Handler.pages["/leak.pdf"] = (REDIRECT, b"http://localhost:" + port + b"/hospital")
        _Handler.pages["/gone"] = (REDIRECT, b"http://localhost:" + port + b"/hospital")
        yield running
