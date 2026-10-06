"""The parse job's paths: a parse that raises, a retry one page at a time, a worker that died,
and bytes another job parsed while this one waited."""

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from public_atlas.integrations.browser import BrowserPolicy
from public_atlas.integrations.parse import ParsedDocument
from public_atlas.jobs.context import Attempt, current_attempt
from public_atlas.modules.evidence import jobs as parse_jobs
from public_atlas.modules.evidence import service
from public_atlas.modules.evidence.models import Snapshot, TextStatus
from public_atlas.modules.graph import service as graph

if TYPE_CHECKING:
    from tests.integration.conftest import Database, FixtureSite, InlineConnector

    from public_atlas.integrations.storage.memory import MemoryObjectStore
    from public_atlas.modules.assignments.models import Assignment
    from public_atlas.resources import Resources


class Crashing:
    """A parser that raises something other than `ParseFailed`, as running out of memory does."""

    name = "crashing"
    version = "1"

    def warm_up(self) -> None:
        return

    def parse(self, data: bytes, filename: str, *, page_batch: int | None = None) -> ParsedDocument:  # noqa: ARG002
        raise MemoryError("the file was too large")


class Recording:
    """A parser that records the `page_batch` each call asked for."""

    name = "recording"
    version = "1"

    def __init__(self) -> None:
        self.batches: list[int | None] = []

    def warm_up(self) -> None:
        return

    def parse(self, data: bytes, filename: str, *, page_batch: int | None = None) -> ParsedDocument:  # noqa: ARG002
        self.batches.append(page_batch)
        return ParsedDocument(pages=(data.decode(),), parser=self.name, version=self.version)


@pytest.fixture
def stored(
    db: Database, object_store: MemoryObjectStore, assignment: Assignment, site: FixtureSite
) -> Snapshot:
    """A file the assignment downloaded but has not parsed yet."""

    async def store() -> Snapshot:
        async with db.session() as session:
            webpage = await graph.ensure_webpage(session, f"{site.allowed}/budget.pdf")
            snapshot, _ = await service.store_snapshot(
                session,
                object_store,
                webpage,
                b"%PDF-1.4 Operating budget 2026",
                text=None,
                media_type="application/pdf",
                filename="budget.pdf",
                assignment_id=assignment.id,
            )
            await session.commit()
            return snapshot

    return db.run(store)


def parse_as(db: Database, res: Resources, snapshot: Snapshot, attempt: Attempt) -> str:
    async def run() -> str:
        token = current_attempt.set(attempt)
        try:
            return await parse_jobs.parse(res, snapshot.id)
        finally:
            current_attempt.reset(token)

    return db.run(run)


def state(
    db: Database, snapshot: Snapshot
) -> tuple[TextStatus, str | None, int | None, str | None]:
    async def check() -> tuple[TextStatus, str | None, int | None, str | None]:
        async with db.session() as session:
            row = await session.get_one(Snapshot, snapshot.id)
            return row.text_status, row.text_error, row.page_count, row.text_key

    return db.run(check)


def resources(queue: InlineConnector) -> Resources:
    assert queue.resources is not None
    return queue.resources


def test_a_parse_that_raises_is_recorded_failed_on_the_last_attempt(
    db: Database, queue: InlineConnector, stored: Snapshot
):
    res = replace(resources(queue), parser=Crashing())
    # A retry follows, so nothing is written yet.
    with pytest.raises(MemoryError):
        parse_as(db, res, stored, Attempt(1, last=False))
    assert state(db, stored)[0] is TextStatus.PARSING
    # On the last attempt the same error is recorded on the file.
    with pytest.raises(MemoryError):
        parse_as(db, res, stored, Attempt(2, last=True))
    assert state(db, stored)[:2] == (TextStatus.FAILED, "MemoryError: the file was too large")


def test_a_retry_parses_one_page_at_a_time(db: Database, queue: InlineConnector, stored: Snapshot):
    recording = Recording()
    res = replace(resources(queue), parser=recording)
    assert parse_as(db, res, stored, Attempt(2, last=True)) == "ok"
    assert recording.batches == [1]
    assert state(db, stored)[::2] == (TextStatus.READY, 1)


def test_a_parse_the_parser_refuses_is_recorded_failed_at_once(
    db: Database, queue: InlineConnector, assignment: Assignment, object_store: MemoryObjectStore
):
    async def store() -> Snapshot:
        async with db.session() as session:
            webpage = await graph.ensure_webpage(session, "https://x.example/scan.pdf")
            snapshot, _ = await service.store_snapshot(
                session,
                object_store,
                webpage,
                b"\xff\xfe",
                text=None,
                media_type="application/pdf",
                filename="scan.pdf",
                assignment_id=assignment.id,
            )
            await session.commit()
            return snapshot

    snapshot = db.run(store)
    assert parse_as(db, resources(queue), snapshot, Attempt(1, last=False)) == "failed"
    assert state(db, snapshot)[:2] == (TextStatus.FAILED, "scan.pdf: not text (invalid start byte)")


def test_a_parse_whose_worker_died_is_recorded_failed_without_loading_the_parser(
    db: Database, queue: InlineConnector, stored: Snapshot
):
    """`abandoned` is what the stalled-job sweep calls once the job has had its retries."""
    res = replace(resources(queue), parser=Crashing())

    async def abandon() -> None:
        await parse_jobs.abandoned(res, snapshot_id=str(stored.id))

    db.run(abandon)
    assert state(db, stored)[:2] == (TextStatus.FAILED, parse_jobs.WORKER_DIED)
    # A file that has its answer already is left alone.
    db.run(abandon)
    assert state(db, stored)[:2] == (TextStatus.FAILED, parse_jobs.WORKER_DIED)


def test_bytes_parsed_while_the_job_waited_are_shared_not_parsed_again(
    db: Database,
    queue: InlineConnector,
    stored: Snapshot,
    another_assignment: Assignment,
    site: FixtureSite,
):
    """The first assignment's parse is still queued when a second reads the same URL: it gets a
    snapshot of the stored bytes, nothing is downloaded, and its parse runs. By the time the
    first job runs, the text exists and is shared."""
    res = resources(queue)
    policy = BrowserPolicy(["127.0.0.1"], block_private_addresses=False, min_interval=0)

    async def read() -> str:
        return str(
            await service.read_file(
                res, policy, url=f"{site.allowed}/budget.pdf", assignment_id=another_assignment.id
            )
        )

    assert "Operating budget 2026" in db.run(read)
    assert "/budget.pdf" not in site.requested
    assert state(db, stored)[0] is TextStatus.PARSING
    crashing = replace(res, parser=Crashing())
    # No MemoryError: the parser is not called.
    assert parse_as(db, crashing, stored, Attempt(1, last=False)) == "shared"
    status, _, pages, key = state(db, stored)
    assert (status, pages) == (TextStatus.READY, 1)
    assert key == service.text_key(stored.content_hash)
