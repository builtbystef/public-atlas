"""The fetch behind `read_file`: download a document on an allowed domain under the browser's
policy, store it as a snapshot, have it parsed on the `parse` queue, and return one chunk of
its text. A long file is parsed as far as the agent reads: the first pages at once, the next
range when a chunk past them is asked for. A recent snapshot of the same URL is read instead
of fetched again."""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.db.base import utcnow
from public_atlas.integrations.browser import (
    USER_AGENT,
    BrowserPolicy,
    RedirectRefused,
    Request,
    get_within_policy,
)
from public_atlas.integrations.parse import PAGE_SEPARATOR
from public_atlas.jobs.tasks import defer
from public_atlas.modules.evidence import snapshots
from public_atlas.modules.evidence.capture import record_blocked, record_redirect
from public_atlas.modules.evidence.jobs import parse_snapshot
from public_atlas.modules.evidence.media import UNSUPPORTED_NOTE, Detected, challenge_marker, detect
from public_atlas.modules.evidence.models import Snapshot, TextStatus
from public_atlas.modules.evidence.quote_checks import HTML
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph.models import Webpage

if TYPE_CHECKING:
    from public_atlas.resources import Resources

logger = logging.getLogger(__name__)

DOWNLOAD_TIMEOUT = 60.0
POLL_INTERVAL = 2.0


@dataclass(frozen=True, slots=True)
class Progress:
    """How far a file's parse has come: `parsed` of its `total` pages are text, and `error` is
    why the rest never will be."""

    parsed: int
    total: int
    error: str | None = None

    @property
    def complete(self) -> bool:
        return self.parsed >= self.total

    @classmethod
    def of(cls, snapshot: Snapshot) -> Progress | None:
        """The snapshot's progress, or None for a text that is whole."""
        if snapshot.text_status is TextStatus.READY or snapshot.page_count is None:
            return None
        parsed = snapshot.parsed_pages or 0
        if parsed >= snapshot.page_count:
            return None
        error = snapshot.text_error if snapshot.text_status is TextStatus.FAILED else None
        return cls(parsed=parsed, total=snapshot.page_count, error=error)


@dataclass(frozen=True, slots=True)
class FileText:
    """One chunk of a file's text, each page labelled. `progress` is set while the file is not
    parsed to its end."""

    url: str
    # The URL the caller asked for, when the site redirected it elsewhere.
    requested_url: str | None
    media_type: str
    page_count: int
    chunk: int
    chunks: int
    body: str
    progress: Progress | None = None

    def __str__(self) -> str:
        if self.progress is None:
            header = (
                f"File: {self.url} ({self.media_type}, {self.page_count} page(s), "
                f"chunk {self.chunk} of {self.chunks})"
            )
            if self.chunk < self.chunks:
                header += f". Call read_file(url, chunk={self.chunk + 1}) for the next chunk"
        else:
            header = (
                f"File: {self.url} ({self.media_type}, {self.progress.total} page(s), "
                f"{self.progress.parsed} parsed so far, chunk {self.chunk} of {self.chunks} "
                "so far)"
            )
            if self.chunk < self.chunks:
                header += f". Call read_file(url, chunk={self.chunk + 1}) for the next chunk"
            elif self.progress.error is not None:
                header += (
                    f". Pages {self.progress.parsed + 1}-{self.progress.total} could not be "
                    f"parsed: {self.progress.error}"
                )
            else:
                header += (
                    f". Call read_file(url, chunk={self.chunk + 1}) to have the next pages "
                    "parsed and read them"
                )
        if self.requested_url is not None:
            header = (
                f"{self.requested_url} redirected to {self.url}; quote it by that URL.\n{header}"
            )
        return f"{header}\n\n{self.body}"


@dataclass(frozen=True, slots=True)
class FileParsing:
    """The file is stored and queued; the text asked for is not ready yet."""

    url: str
    # The pages being parsed, when the first ones are readable already.
    pages: tuple[int, int] | None = None

    def __str__(self) -> str:
        what = (
            f"{self.url} is still being parsed"
            if self.pages is None
            else f"Pages {self.pages[0]}-{self.pages[1]} of {self.url} are still being parsed"
        )
        return (
            f"{what}. Carry on with something else and call read_file again in a while; "
            "status() lists the file as parsing, partial, ready or failed."
        )


@dataclass(frozen=True, slots=True)
class FileRefusal:
    """Why there is no text: a refused URL, a failed download, a failed parse."""

    reason: str

    def __str__(self) -> str:
        return f"Error: {self.reason}"


type FileResult = FileText | FileParsing | FileRefusal


async def read_file(  # noqa: PLR0911 - each return is an answer for the model
    res: Resources,
    policy: BrowserPolicy,
    *,
    url: str,
    chunk: int = 1,
    assignment_id: uuid.UUID | None,
) -> FileResult:
    """One chunk of the file's text, or why there is none. Returns rather than raises: a refused
    or unreadable file is an answer for the model, not a mistake."""
    if chunk < 1:
        return FileRefusal("chunk numbers start at 1.")
    try:
        normalized = graph.normalize_url(url)
    except ValueError:
        return FileRefusal(f"not a URL: {url!r}")
    host = graph.host_of(normalized)
    if not host or any(char.isspace() for char in host):
        return FileRefusal(f"not a URL: {url!r}")
    async with res.session() as session:
        if (reason := await policy.decide(Request(url=normalized, kind="navigation"))) is not None:
            await record_blocked(
                session, url=normalized, reason=reason, assignment_id=assignment_id
            )
            await session.commit()
            return FileRefusal(f"{reason}: {normalized}. Only the allowed domains can be fetched.")
        webpage = await graph.ensure_webpage(session, normalized, assignment_id=assignment_id)
        snapshot = await _own_or_recent(res, session, webpage, assignment_id=assignment_id)
        final_url = normalized
        if snapshot is None:
            outcome = await _download_and_store(
                res, session, policy, normalized, assignment_id=assignment_id
            )
            if isinstance(outcome, FileRefusal):
                await session.commit()
                return outcome
            snapshot, final_url = outcome
        await session.commit()
        snapshot_id = snapshot.id

    parsed = await _text_for_chunk(res, snapshot_id, url=final_url, chunk=chunk)
    if not isinstance(parsed, tuple):
        return parsed
    ready, text = parsed
    return chunk_of(
        final_url,
        ready.media_type,
        text,
        chunk=chunk,
        size=res.settings.read_file_chunk_chars,
        requested_url=normalized if final_url != normalized else None,
        progress=Progress.of(ready),
    )


async def _text_for_chunk(
    res: Resources, snapshot_id: uuid.UUID, *, url: str, chunk: int
) -> tuple[Snapshot, str] | FileParsing | FileRefusal:
    """The snapshot and its text once it reaches chunk `chunk`, or its end: the first pages
    are waited for, and each next range is queued and waited for while the chunk is past the
    pages parsed, within `read_file_wait` altogether."""
    deadline = asyncio.get_running_loop().time() + res.settings.read_file_wait.total_seconds()
    ready = await _wait_for_text(res, snapshot_id, deadline=deadline, beyond=None)
    if ready is None:
        return FileParsing(url)
    size = res.settings.read_file_chunk_chars
    text = await snapshots.snapshot_text(res.object_store, ready)
    while ready.text_status is TextStatus.PARTIAL and chunk > chunk_count(text, size=size):
        parsed = ready.parsed_pages or 0
        through = min(parsed + res.settings.parse_page_batch, ready.page_count or parsed)
        await _parse_through(res, ready, through)
        ready = await _wait_for_text(res, snapshot_id, deadline=deadline, beyond=parsed)
        if ready is None:
            return FileParsing(url, pages=(parsed + 1, through))
        text = await snapshots.snapshot_text(res.object_store, ready)
    if ready.text_status is TextStatus.FAILED and not text:
        return FileRefusal(f"{url} could not be parsed: {ready.text_error}")
    return ready, text


async def _download_and_store(  # noqa: PLR0911 - each return is an answer for the model
    res: Resources,
    session: AsyncSession,
    policy: BrowserPolicy,
    url: str,
    *,
    assignment_id: uuid.UUID | None,
) -> tuple[Snapshot, str] | FileRefusal:
    """The snapshot and the URL that answered, or the refusal. A redirect is followed one
    checked hop at a time, and the bytes are stored against the URL that served them, never
    the one the agent passed."""
    cap = res.settings.read_file_max_bytes
    try:
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT) as client:
            request = client.build_request("GET", url, headers={"User-Agent": USER_AGENT})
            response = await get_within_policy(client, policy, request, stream=True)
            try:
                final_url = graph.normalize_url(str(response.url))
                if final_url != url:
                    await record_redirect(
                        session, requested=url, landed=final_url, assignment_id=assignment_id
                    )
                if response.status_code != httpx.codes.OK:
                    return FileRefusal(f"{final_url} answered HTTP {response.status_code}.")
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > cap:
                    return FileRefusal(
                        f"{final_url} is {declared} bytes, over the {cap}-byte cap; not fetched."
                    )
                chunks: list[bytes] = []
                received = 0
                async for part in response.aiter_bytes():
                    received += len(part)
                    if received > cap:
                        return FileRefusal(f"{final_url} is over the {cap}-byte cap; not fetched.")
                    chunks.append(part)
                content_type = response.headers.get("content-type")
            finally:
                await response.aclose()
    except RedirectRefused as exc:
        await record_blocked(session, url=exc.url, reason=exc.reason, assignment_id=assignment_id)
        await record_redirect(session, requested=url, landed=exc.url, assignment_id=assignment_id)
        return FileRefusal(
            f"{url} redirects to {exc.url}, which was refused: {exc.reason}. Only the allowed "
            "domains can be fetched."
        )
    except httpx.HTTPError as exc:
        return FileRefusal(f"could not download {url}: {exc}")
    data = b"".join(chunks)
    detected = detect(data, content_type, final_url)
    if detected.media_type == HTML and (marker := challenge_marker(data)) is not None:
        await record_blocked(
            session, url=final_url, reason=f"bot check page ({marker})", assignment_id=assignment_id
        )
        return FileRefusal(
            f"{final_url} answered with a bot check page ({marker!r}) instead of the document. "
            "The site's protection challenged the fetcher; retrying now will not help. Leave the "
            "file, or cite the page that links to it."
        )
    webpage = await graph.ensure_webpage(session, final_url, assignment_id=assignment_id)
    text = data.decode(errors="replace") if detected.handling == "text" else None
    snapshot, _ = await snapshots.store_snapshot(
        session,
        res.object_store,
        webpage,
        data,
        text=text,
        media_type=detected.media_type,
        filename=detected.filename,
        assignment_id=assignment_id,
    )
    await _attach_text(res, session, snapshot, detected)
    return snapshot, final_url


async def _attach_text(
    res: Resources, session: AsyncSession, snapshot: Snapshot, detected: Detected
) -> None:
    """A parsed type still `parsing` is queued; an unsupported type is recorded as failed, so
    the agent gets a definitive answer. Direct text and shared text are ready already."""
    if snapshot.text_status is not TextStatus.PARSING:
        return
    if detected.handling == "unsupported":
        note = UNSUPPORTED_NOTE.get(
            detected.media_type, f"{detected.media_type} files are not parsed"
        )
        await snapshots.mark_text_failed(session, snapshot, note)
        return
    try:
        await defer(
            res.jobs,
            session,
            parse_snapshot,
            queueing_lock=f"parse:{snapshot.id}",
            snapshot_id=str(snapshot.id),
        )
    except AlreadyEnqueued:
        logger.info("Parse of %s already queued", snapshot.id)


async def _own_or_recent(
    res: Resources, session: AsyncSession, webpage: Webpage, *, assignment_id: uuid.UUID | None
) -> Snapshot | None:
    """This assignment's own snapshot of the file, else one of its own made from a snapshot
    another assignment fetched within `read_file_reuse`: the bytes and the text are keyed by
    hash, so nothing is downloaded or stored again. A site that serves a city's budget book
    once per department takes the crawl for a bot. A failed parse, pruned bytes and a browser
    capture of a page are never reused."""
    own = await session.scalar(
        select(Snapshot)
        .where(
            Snapshot.webpage_id == webpage.id,
            Snapshot.assignment_id == assignment_id,
            Snapshot.pruned_at.is_(None),
        )
        .order_by(Snapshot.fetched_at.desc())
        .limit(1)
    )
    if own is not None:
        return own
    since = utcnow() - res.settings.read_file_reuse
    recent = await session.scalar(
        select(Snapshot)
        .where(
            Snapshot.webpage_id == webpage.id,
            Snapshot.fetched_at >= since,
            Snapshot.media_type != HTML,
            Snapshot.pruned_at.is_(None),
            Snapshot.text_status != TextStatus.FAILED,
        )
        .order_by(Snapshot.fetched_at.desc())
        .limit(1)
    )
    if recent is None:
        return None
    snapshot = Snapshot(
        webpage_id=webpage.id,
        assignment_id=assignment_id,
        fetched_at=recent.fetched_at,
        content_hash=recent.content_hash,
        media_type=recent.media_type,
        size=recent.size,
        filename=recent.filename,
        bytes_key=recent.bytes_key,
        text_key=recent.text_key,
        text_status=recent.text_status,
        page_count=recent.page_count,
        parsed_pages=recent.parsed_pages,
    )
    session.add(snapshot)
    await session.flush()
    if snapshot.text_status is TextStatus.PARSING and not await snapshots.share_text(
        session, snapshot
    ):
        detected = Detected(recent.media_type, recent.filename or "file", "parse")
        await _attach_text(res, session, snapshot, detected)
    logger.info("Reused %s from a snapshot of %s", webpage.url, recent.fetched_at)
    return snapshot


async def _parse_through(res: Resources, snapshot: Snapshot, through: int) -> None:
    """Queue the parse of the snapshot's pages up to `through`. A parse of the file already
    waiting its turn will do."""
    async with res.session() as session:
        try:
            await defer(
                res.jobs,
                session,
                parse_snapshot,
                queueing_lock=f"parse:{snapshot.id}",
                snapshot_id=str(snapshot.id),
                through=through,
            )
        except AlreadyEnqueued:
            logger.info("Parse of %s already queued", snapshot.id)
        await session.commit()


async def _wait_for_text(
    res: Resources, snapshot_id: uuid.UUID, *, deadline: float, beyond: int | None
) -> Snapshot | None:
    """The snapshot once it has text, or failed, or None when `deadline` (the loop's clock)
    passes first. With `beyond`, the pages parsed so far, it waits for more of them."""
    while True:
        async with res.session() as session:
            snapshot = await session.get(Snapshot, snapshot_id)
        if snapshot is not None and (
            snapshot.text_status is TextStatus.FAILED
            or (snapshot.text_status is not TextStatus.PARSING and beyond is None)
            or (beyond is not None and (snapshot.parsed_pages or 0) > beyond)
        ):
            return snapshot
        if asyncio.get_running_loop().time() >= deadline:
            return None
        await asyncio.sleep(POLL_INTERVAL)


def _flat(text: str) -> str:
    """The text with each page labelled."""
    pages = text.split(PAGE_SEPARATOR)
    if len(pages) == 1:
        return text
    return "\n\n".join(f"[page {n}]\n{page}" for n, page in enumerate(pages, start=1))


def chunk_count(text: str, *, size: int) -> int:
    """How many chunks of `size` characters the labelled text makes."""
    return max(1, -(-len(_flat(text)) // size))


def chunk_of(  # noqa: PLR0913
    url: str,
    media_type: str,
    text: str,
    *,
    chunk: int,
    size: int,
    requested_url: str | None = None,
    progress: Progress | None = None,
) -> FileText | FileRefusal:
    """Chunk `chunk`, counted from 1, of `text` with each page labelled."""
    flat = _flat(text)
    chunks = max(1, -(-len(flat) // size))
    if chunk > chunks:
        if progress is not None and progress.error is not None:
            return FileRefusal(
                f"{url} has {chunks} chunk(s), pages 1-{progress.parsed} of {progress.total}; "
                f"the rest could not be parsed: {progress.error}"
            )
        return FileRefusal(f"{url} has {chunks} chunk(s); there is no chunk {chunk}.")
    return FileText(
        url=url,
        requested_url=requested_url,
        media_type=media_type,
        page_count=text.count(PAGE_SEPARATOR) + 1,
        chunk=chunk,
        chunks=chunks,
        body=flat[(chunk - 1) * size : chunk * size],
        progress=progress,
    )
