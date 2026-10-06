"""Fixtures for the findings tests: a session context on an assignment of the world, pages
captured as the browser would store them, and `call`, which runs one finding on a session of
its own as the tool adapter does."""

import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.agent import findings
from public_atlas.modules.agent.context import SessionContext, build_context
from public_atlas.modules.assignments.models import Assignment, AssignmentType
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.evidence.models import EvidenceKind, Snapshot
from public_atlas.modules.graph.models import EnteredBy, Homepage, Institution, Webpage

if TYPE_CHECKING:
    from tests.integration.conftest import Database, InlineConnector
    from tests.integration.modules.conftest import Build, World

    from public_atlas.integrations.storage.memory import MemoryObjectStore

# The region's trusted site, where its towns are listed with their sites.
TOWNS_URL = "https://www.elmcounty.ca/towns"
TOWNS_HTML = """<html><body><h1>Towns of Elm County</h1>
<table><tr><td><a href="https://www.oakville.ca/">Town of Oakville</a></td><td>Lower tier</td></tr>
<tr><td>Town of Milton Lower tier</td></tr></table>
<p>The County of Elm publishes this list.</p>
<p><a href="https://www.elmcounty.ca/library">Elm County Library</a> serves every town.</p>
<p><a href="https://www.elmcounty.ca/conservation">Elm Conservation Authority</a>, ECA,
protects the watershed. Elm Transit is operated by the County of Elm.</p>
<p>Elm Reading Room: the county's reference library.</p>
<p>Elm County Public Library is another name for it; Bibliothèque du comté d'Elm en français.</p>
</body></html>"""
TOWNS_TEXT = (
    "Towns of Elm County\nTown of Oakville Lower tier\nTown of Milton Lower tier\n"
    "The County of Elm publishes this list.\n"
    "Elm County Library serves every town.\n"
    "Elm Conservation Authority, ECA, protects the watershed. Elm Transit is operated by the "
    "County of Elm.\n"
    "Elm Reading Room: the county's reference library.\n"
    "Elm County Public Library is another name for it; Bibliothèque du comté d'Elm en français."
)
# The library's own page on the trusted domain, which the towns page links to.
LIBRARY_URL = "https://www.elmcounty.ca/library"
LIBRARY_HTML = """<html><body><h1>Elm County Library</h1>
<p>The library serves every town of the county.</p></body></html>"""
LIBRARY_TEXT = "Elm County Library\nThe library serves every town of the county."
# A page on a platform: fetchable, never trusted.
PLATFORM_URL = "https://elm.bidsandtenders.ca/list"
PLATFORM_HTML = """<html><body><h1>Public bodies on this portal</h1>
<p><a href="https://www.milton.ca/">Town of Milton</a> bids</p>
<p>Elm County Library procurement portal</p></body></html>"""
PLATFORM_TEXT = (
    "Public bodies on this portal\nTown of Milton bids\nElm County Library procurement portal"
)


type Call = Callable[..., Any]


@pytest.fixture
def resources(queue: InlineConnector):
    assert queue.resources is not None
    return queue.resources


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
def make_assignment(db: Database, world: World, build: type[Build]) -> Callable[..., Assignment]:
    """A running assignment in the world's step-mode run."""

    def factory(assignment_type: AssignmentType, subject_id: uuid.UUID) -> Assignment:
        async def create() -> Assignment:
            async with db.session() as session:
                row = await build.open_assignment(session, world.run, assignment_type, subject_id)
                row.budget_requests = 50
                row.budget_tokens = 1_000_000
                await session.commit()
                return row

        return db.run(create)

    return factory


@pytest.fixture
def context(db: Database, queue: InlineConnector) -> Callable[[Assignment], SessionContext]:
    """The session context of an assignment, as a session would build it."""

    def build(assignment: Assignment) -> SessionContext:
        async def make() -> SessionContext:
            assert queue.resources is not None
            async with db.session() as session:
                return await build_context(session, queue.resources, assignment)

        return db.run(make)

    return build


class Capture:
    """Pages stored as the capture hook stores them: any page by its URL, HTML and text, and
    the three pages of the fixture site by name."""

    TOWNS_URL = TOWNS_URL
    TOWNS_TEXT = TOWNS_TEXT
    LIBRARY_URL = LIBRARY_URL
    PLATFORM_URL = PLATFORM_URL

    def __init__(self, db: Database, build: type[Build], store: MemoryObjectStore) -> None:
        self._db = db
        self._build = build
        self._store = store

    def __call__(
        self, url: str, html: str, text: str, *, assignment_id: uuid.UUID | None = None
    ) -> tuple[Webpage, Snapshot]:
        async def make() -> tuple[Webpage, Snapshot]:
            async with self._db.session() as session:
                found = await self._build.capture(
                    session, self._store, url, html, text, assignment_id=assignment_id
                )
                await session.commit()
                return found

        return self._db.run(make)

    def page(
        self, url: str, text: str, assignment_id: uuid.UUID | None = None
    ) -> tuple[Webpage, Snapshot]:
        """A page whose stored HTML is its text: identical bytes share one text, so two pages
        with different words need different HTML."""
        return self(url, f"<html><body>{text}</body></html>", text, assignment_id=assignment_id)

    def towns(self, assignment_id: uuid.UUID | None = None) -> tuple[Webpage, Snapshot]:
        return self(TOWNS_URL, TOWNS_HTML, TOWNS_TEXT, assignment_id=assignment_id)

    def library(self, assignment_id: uuid.UUID | None = None) -> tuple[Webpage, Snapshot]:
        return self(LIBRARY_URL, LIBRARY_HTML, LIBRARY_TEXT, assignment_id=assignment_id)

    def platform(self, assignment_id: uuid.UUID | None = None) -> tuple[Webpage, Snapshot]:
        return self(PLATFORM_URL, PLATFORM_HTML, PLATFORM_TEXT, assignment_id=assignment_id)


@pytest.fixture
def capture(db: Database, build: type[Build], object_store: MemoryObjectStore) -> Capture:
    return Capture(db, build, object_store)


@pytest.fixture
def call(db: Database) -> Callable[..., Any]:
    """Run one finding on a session of its own, as the adapter does: committed when it
    returns, rolled back when it refuses."""

    def run(ctx: SessionContext, finding: Call, **kwargs: object) -> Any:
        async def inner() -> Any:
            async with db.session() as session:
                try:
                    result = await finding(ctx, session, **kwargs)
                except findings.FindingError:
                    await session.rollback()
                    raise
                await session.commit()
                return result

        return db.run(inner)

    return run


@pytest.fixture
def claimed(
    db: Database, world: World, build: type[Build], capture: Capture
) -> Callable[..., Homepage]:
    """A candidate homepage claim on a new domain, as `save_homepage` leaves one: the towns page
    captured, the claim with the trusted page it was found on, and the link quote as evidence."""

    def make(
        institution: Institution,
        url: str = "https://www.oakville.ca/",
        *,
        quote: str = "Town of Oakville",
        found_on: bool = True,
    ) -> Homepage:
        _, snapshot = capture.towns()

        async def inner() -> Homepage:
            async with db.session() as session:
                towns = await session.get_one(Webpage, snapshot.webpage_id)
                row = await session.get_one(Institution, institution.id)
                claim = await build.claim(session, row, url, found_on=towns if found_on else None)
                if found_on:
                    await evidence.add_evidence(
                        session,
                        entity_id=claim.id,
                        snapshot=snapshot,
                        kind=EvidenceKind.LINKS_TO,
                        quote=quote,
                        entered_by=EnteredBy.AGENT,
                        link_url=url,
                    )
                await session.commit()
                return claim

        return db.run(inner)

    return make
