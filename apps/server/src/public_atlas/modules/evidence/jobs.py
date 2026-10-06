"""The `parse` queue: one job per stored file, turning its bytes into text with the worker's
parser. Ranges of pages and the memory trim are the parser's; the retry with one page per
range and the retire threshold are here."""

import asyncio
import logging
import os
import signal
import uuid

from procrastinate import RetryStrategy

from public_atlas.integrations.parse import ParseFailed
from public_atlas.jobs.context import Attempt, current_attempt
from public_atlas.jobs.tasks import task
from public_atlas.modules.evidence import snapshots
from public_atlas.modules.evidence.models import Snapshot, TextStatus
from public_atlas.resources import Resources
from public_atlas.shared import diagnostics

logger = logging.getLogger(__name__)

# One retry, parsing one page at a time (`pages_per_range`). After it the file is recorded
# `failed`, so `read_file` and `status` stop reporting it as still parsing.
PARSE_RETRY = RetryStrategy(max_attempts=2, wait=5)
WORKER_DIED = "The parse worker stopped while parsing this file"


async def abandoned(res: Resources, *, snapshot_id: str) -> None:
    """Runs on whichever worker finds a job whose own worker died on its last attempt. No
    parser is loaded; the file is just recorded `failed`."""
    await record_failed(res, uuid.UUID(snapshot_id), error=WORKER_DIED)


@task("evidence.parse_snapshot", queue="parse", retry=PARSE_RETRY, abandoned=abandoned)
async def parse_snapshot(res: Resources, *, snapshot_id: str) -> str:
    try:
        return await parse(res, uuid.UUID(snapshot_id))
    finally:
        retire_if_grown(res.settings.parse_retire_rss_mb)


def retire_if_grown(limit_mb: int, *, rss_mb: int | None = None) -> bool:
    """Ask this worker to stop once it holds more than `limit_mb`. Docling and the OCR runtime
    never give back what a heavy page cost, so a fresh process is the only way to free it."""
    held = diagnostics.rss_mb() if rss_mb is None else rss_mb
    if held is None or held <= limit_mb:
        return False
    logger.warning("Parse worker holds %d MB, over %d MB: retiring after this job", held, limit_mb)
    # The worker loop handles SIGTERM: it stops fetching and lets this job finish. The unit that
    # runs the worker starts a new one.
    os.kill(os.getpid(), signal.SIGTERM)
    return True


def pages_per_range(attempt: Attempt) -> int | None:
    """The parser's own range size on the first attempt, one page on a retry. A retry means the
    first attempt raised or took the worker down (ten-page ranges did, on several budget books),
    and one page at a time is the smallest peak."""
    return None if attempt.number == 1 else 1


async def parse(res: Resources, snapshot_id: uuid.UUID) -> str:
    """A parse the parser refuses outright is recorded `failed` at once: the same bytes would
    fail again. Any other error is retried by the queue and recorded `failed` on the last
    attempt."""
    try:
        return await _parse(res, snapshot_id)
    except Exception as exc:
        if current_attempt.get().last:
            await record_failed(res, snapshot_id, error=f"{type(exc).__name__}: {exc}")
        raise


async def _parse(res: Resources, snapshot_id: uuid.UUID) -> str:
    async with res.session() as session:
        snapshot = await session.get(Snapshot, snapshot_id)
        if snapshot is None:
            return "gone"
        if snapshot.text_status is not TextStatus.PARSING:
            return "already done"
        if await snapshots.share_text(session, snapshot):
            # The same bytes were parsed while this job waited its turn: a city's departments
            # fetch the city's budget book minutes apart.
            await session.commit()
            logger.info(
                "Parse of %s shared with an earlier parse of the same bytes", snapshot.filename
            )
            return "shared"
        data = await snapshots.snapshot_bytes(res.object_store, snapshot)
        if data is None:
            # Its assignment finished and nothing cited the file before it was parsed.
            return "pruned"
        attempt = current_attempt.get()
        page_batch = pages_per_range(attempt)
        if page_batch is not None:
            logger.info(
                "Parse of %s, attempt %d: %d page(s) per range",
                snapshot.filename,
                attempt.number,
                page_batch,
            )
        try:
            document = await asyncio.to_thread(
                res.parser.parse, data, snapshot.filename or "file", page_batch=page_batch
            )
        except ParseFailed as exc:
            await snapshots.mark_text_failed(session, snapshot, str(exc))
            await session.commit()
            logger.info("Parse of %s failed: %s", snapshot.filename, exc)
            return "failed"
        await snapshots.mark_text_ready(session, res.object_store, snapshot, document.text)
        await session.commit()
        return "ok"


async def record_failed(res: Resources, snapshot_id: uuid.UUID, *, error: str) -> None:
    """Write the failure on a session of its own, since the run's session is rolled back with
    the failure. Nothing is written for a file that is gone or has its text already."""
    async with res.session() as session:
        snapshot = await session.get(Snapshot, snapshot_id)
        if snapshot is None or snapshot.text_status is not TextStatus.PARSING:
            return
        await snapshots.mark_text_failed(session, snapshot, error)
        await session.commit()
    logger.warning("Parse of snapshot %s given up: %s", snapshot_id, error)
