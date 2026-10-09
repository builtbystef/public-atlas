"""`read_file` against a local site: downloads, parsing, chunks, redirects, reuse between
assignments, a long file parsed as far as it is read, and refusals."""

from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from public_atlas.integrations.browser import BrowserPolicy
from public_atlas.modules.evidence import service
from public_atlas.modules.evidence.models import BlockedAttempt, Snapshot, TextStatus
from public_atlas.modules.graph.models import Webpage

if TYPE_CHECKING:
    from tests.integration.conftest import Database, FixtureSite, InlineConnector

    from public_atlas.modules.assignments.models import Assignment
    from public_atlas.resources import Resources

PARSE_JOB = "evidence.parse_snapshot"


def policy_for_site() -> BrowserPolicy:
    return BrowserPolicy(["127.0.0.1"], block_private_addresses=False, min_interval=0)


def read(db: Database, res: Resources, assignment: Assignment, url: str, chunk: int = 1) -> str:
    async def run() -> str:
        return str(
            await service.read_file(
                res, policy_for_site(), url=url, chunk=chunk, assignment_id=assignment.id
            )
        )

    return db.run(run)


def parses(queue: InlineConnector) -> int:
    return [job["task_name"] for job in queue.jobs.values()].count(PARSE_JOB)


def resources(queue: InlineConnector, **settings: object) -> Resources:
    assert queue.resources is not None
    res = queue.resources
    if settings:
        res = replace(res, settings=res.settings.model_copy(update=settings))
    return res


def test_read_file_downloads_parses_and_chunks_within_the_allowlist(
    db: Database, site: FixtureSite, assignment: Assignment, queue: InlineConnector
):
    res = resources(queue, read_file_chunk_chars=1000)

    # The PDF is parsed on the queue, which runs inline here with the memory parser.
    text = read(db, res, assignment, f"{site.allowed}/budget.pdf")
    assert text.startswith(
        f"File: {site.allowed}/budget.pdf (application/pdf, 2 page(s), chunk 1 of 1)"
    )
    assert "Operating budget 2026" in text
    assert "[page 2]\nCapital plan page" in text
    # The second read is served from storage: still one snapshot and one parse.
    assert read(db, res, assignment, f"{site.allowed}/budget.pdf") == text
    # Plain text needs no parser.
    assert "Council notes: tenders close Friday." in read(
        db, res, assignment, f"{site.allowed}/notes.txt"
    )
    # An unsupported type fails for good.
    assert read(db, res, assignment, f"{site.allowed}/legacy.doc") == (
        f"Error: {site.allowed}/legacy.doc could not be parsed: legacy .doc files are not parsed"
    )
    # Off the allowlist: refused before any request goes out, and recorded as blocked.
    refused = read(db, res, assignment, f"{site.outside}/notes.txt")
    assert refused.startswith("Error: domain not in allowed_domains")
    assert read(db, res, assignment, f"{site.allowed}/missing.pdf") == (
        f"Error: {site.allowed}/missing.pdf answered HTTP 404."
    )
    assert read(db, res, assignment, "not a url").startswith("Error:")
    assert (
        read(db, res, assignment, f"{site.allowed}/notes.txt", chunk=0)
        == "Error: chunk numbers start at 1."
    )

    async def check() -> tuple[list[str], list[str], list[TextStatus]]:
        async with db.session() as session:
            urls = list(await session.scalars(select(Webpage.url).order_by(Webpage.url)))
            blocked = list(await session.scalars(select(BlockedAttempt.url)))
            statuses = list(
                await session.scalars(
                    select(Snapshot.text_status).where(Snapshot.assignment_id == assignment.id)
                )
            )
            return urls, blocked, statuses

    urls, blocked, statuses = db.run(check)
    assert blocked == [f"{site.outside}/notes.txt"]
    assert f"{site.allowed}/budget.pdf" in urls
    assert f"{site.allowed}/missing.pdf" in urls  # the URL was opened, if to no end
    assert f"{site.outside}/notes.txt" not in urls
    assert sorted(statuses) == [TextStatus.FAILED, TextStatus.READY, TextStatus.READY]
    assert parses(queue) == 1


def test_a_long_file_is_parsed_as_far_as_the_agent_reads(
    db: Database,
    site: FixtureSite,
    assignment: Assignment,
    another_assignment: Assignment,
    queue: InlineConnector,
):
    """One page per range: the fetch parses page 1 and the file is partial. A chunk past the
    parsed text has the next range parsed and waited for; the text is then whole."""
    res = resources(queue, read_file_chunk_chars=1000, parse_page_batch=1)
    queue.resources = res  # the inline parse jobs read the range size from these settings
    url = f"{site.allowed}/budget.pdf"
    first = read(db, res, assignment, url)
    assert first.startswith(
        f"File: {url} (application/pdf, 2 page(s), 1 parsed so far, chunk 1 of 1 so far). "
        "Call read_file(url, chunk=2) to have the next pages parsed"
    )
    assert "Operating budget 2026" in first
    assert "Capital plan page" not in first
    assert parses(queue) == 1

    async def rows() -> list[tuple[TextStatus, int | None, int | None]]:
        async with db.session() as session:
            found = await session.execute(
                select(Snapshot.text_status, Snapshot.parsed_pages, Snapshot.page_count)
                .where(Snapshot.media_type == "application/pdf")
                .order_by(Snapshot.fetched_at)
            )
            return [tuple(row) for row in found.all()]

    assert db.run(rows) == [(TextStatus.PARTIAL, 1, 2)]
    # Another assignment's snapshot of the same bytes shares the partial text.
    assert read(db, res, another_assignment, url) == first
    assert db.run(rows) == [(TextStatus.PARTIAL, 1, 2), (TextStatus.PARTIAL, 1, 2)]
    # Reading past it: chunk 2 does not exist until page 2 is parsed, which it now is. The
    # whole text makes one chunk of 1000 characters, so chunk 2 is past the end after all.
    assert read(db, res, assignment, url, chunk=2) == (
        f"Error: {url} has 1 chunk(s); there is no chunk 2."
    )
    assert parses(queue) == 2
    assert db.run(rows) == [(TextStatus.READY, 2, 2), (TextStatus.READY, 2, 2)]
    whole = read(db, res, assignment, url)
    assert whole.startswith(f"File: {url} (application/pdf, 2 page(s), chunk 1 of 1)")
    assert "[page 2]\nCapital plan page" in whole
    assert read(db, res, another_assignment, url) == whole
    assert parses(queue) == 2


def test_a_redirect_is_checked_hop_by_hop_and_stored_under_the_url_that_answered(
    db: Database, site: FixtureSite, assignment: Assignment, queue: InlineConnector
):
    res = resources(queue)
    # A redirect within the allowlist is followed; the file belongs to the URL that answered.
    moved = read(db, res, assignment, f"{site.allowed}/old-budget.pdf")
    assert moved.startswith(
        f"{site.allowed}/old-budget.pdf redirected to {site.allowed}/budget.pdf; quote it by "
        f"that URL.\nFile: {site.allowed}/budget.pdf (application/pdf"
    )
    assert "Operating budget 2026" in moved
    # A redirect off the allowlist is refused at the hop; the target is never fetched.
    leak = read(db, res, assignment, f"{site.allowed}/leak.pdf")
    assert leak.startswith(
        f"Error: {site.allowed}/leak.pdf redirects to {site.outside}/hospital, which was "
        "refused: domain not in allowed_domains"
    )
    assert "SECRET" not in leak
    assert "/hospital" not in site.requested

    async def check() -> tuple[dict[str, str | None], list[str], list[str]]:
        async with db.session() as session:
            pages = await session.execute(select(Webpage.url, Webpage.redirects_to_url))
            blocked = list(await session.scalars(select(BlockedAttempt.url)))
            snapshots = list(
                await session.scalars(
                    select(Webpage.url)
                    .join(Snapshot, Snapshot.webpage_id == Webpage.id)
                    .where(Snapshot.assignment_id == assignment.id)
                )
            )
            return dict(pages.tuples().all()), blocked, snapshots

    pages, blocked, snapshots = db.run(check)
    assert pages[f"{site.allowed}/old-budget.pdf"] == f"{site.allowed}/budget.pdf"
    assert pages[f"{site.allowed}/budget.pdf"] is None
    assert pages[f"{site.allowed}/leak.pdf"] == f"{site.outside}/hospital"
    assert blocked == [f"{site.outside}/hospital"]
    assert snapshots == [f"{site.allowed}/budget.pdf"]


def test_a_pruned_snapshot_is_not_reused_as_the_text(
    db: Database,
    site: FixtureSite,
    assignment: Assignment,
    another_assignment: Assignment,
    queue: InlineConnector,
):
    res = resources(queue)
    text = read(db, res, assignment, f"{site.allowed}/budget.pdf")
    assert "Operating budget 2026" in text

    async def prune() -> list[str]:
        async with db.session() as session:
            keys = await service.prune_unreferenced(session, assignment.id)
            await service.delete_objects(res.object_store, keys)
            await session.commit()
            return keys

    # Pruning deletes the objects and keeps the rows: a row with no object must not be shared
    # with the next assignment, or its file would read as empty.
    assert len(db.run(prune)) == 2  # the bytes and the text
    assert read(db, res, another_assignment, f"{site.allowed}/budget.pdf") == text
    assert parses(queue) == 2


def test_a_file_another_assignment_fetched_lately_is_read_from_its_snapshot_not_downloaded(
    db: Database,
    site: FixtureSite,
    assignment: Assignment,
    another_assignment: Assignment,
    queue: InlineConnector,
):
    url = f"{site.allowed}/budget.pdf"
    res = resources(queue)
    text = read(db, res, assignment, url)
    assert "Operating budget 2026" in text
    fetched = site.requested.count("/budget.pdf")

    assert read(db, res, another_assignment, url) == text
    assert site.requested.count("/budget.pdf") == fetched
    assert parses(queue) == 1

    async def rows() -> list[Snapshot]:
        async with db.session() as session:
            return list(await session.scalars(select(Snapshot).order_by(Snapshot.id)))

    # The second assignment still gets a row of its own: its evidence cites it and its pruning
    # is judged by it; the bytes and the text are the first's, by hash.
    own, copy = db.run(rows)
    assert (own.assignment_id, copy.assignment_id) == (assignment.id, another_assignment.id)
    assert (copy.content_hash, copy.fetched_at) == (own.content_hash, own.fetched_at)
    assert (copy.bytes_key, copy.text_key, copy.page_count) == (own.bytes_key, own.text_key, 2)
    assert copy.text_status is TextStatus.READY

    # A snapshot older than the reuse window is not read; the file is fetched again, and its
    # bytes, already stored and parsed, are shared rather than parsed again.
    aged = resources(queue, read_file_reuse=timedelta(0))

    async def read_aged() -> str:
        return str(
            await service.read_file(
                aged, policy_for_site(), url=url, assignment_id=another_assignment.id
            )
        )

    async def forget_own() -> None:
        async with db.session() as session:
            mine = await session.get_one(Snapshot, copy.id)
            await session.delete(mine)
            await session.commit()

    db.run(forget_own)
    assert db.run(read_aged) == text
    assert site.requested.count("/budget.pdf") == fetched + 1
    assert parses(queue) == 1


def test_a_bot_check_page_is_an_error_not_a_file(
    db: Database, site: FixtureSite, assignment: Assignment, queue: InlineConnector
):
    url = f"{site.allowed}/guarded.pdf"
    answer = read(db, resources(queue), assignment, url)
    assert answer.startswith(
        f"Error: {url} answered with a bot check page ('pardon our interruption') instead of"
    )

    async def check() -> tuple[list[tuple[str, str]], int]:
        async with db.session() as session:
            attempts = await session.execute(select(BlockedAttempt.url, BlockedAttempt.reason))
            snapshots = len((await session.scalars(select(Snapshot))).all())
            return [tuple(row) for row in attempts.all()], snapshots

    assert db.run(check) == ([(url, "bot check page (pardon our interruption)")], 0)
    assert parses(queue) == 0
