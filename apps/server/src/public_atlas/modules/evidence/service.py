"""The evidence module's door: storing a copy of a page or file with its text, the quotes taken
from it, and the checks a quote or link must pass against a stored copy (spec section 6.2).

Bytes and text are keyed by content hash in the object store, so identical bytes fetched twice,
by whoever and from whatever URL, share one copy of each; a snapshot row is one fetch. A
snapshot's text is `ready` at once for a page or a plain-text file, `parsing` until the parse
queue has done a document, and `failed` with the reason when it cannot be made.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.integrations.parse import PAGE_SEPARATOR
from public_atlas.integrations.storage import ObjectStore
from public_atlas.modules.evidence.capture import (
    PageCapture,
    delete_objects,
    prune_unreferenced,
    record_blocked,
    record_redirect,
)
from public_atlas.modules.evidence.files import (
    FileParsing,
    FileRefusal,
    FileResult,
    FileText,
    read_file,
)
from public_atlas.modules.evidence.models import Evidence, EvidenceKind, Snapshot
from public_atlas.modules.evidence.quote_checks import (
    HTML,
    MIN_QUOTE_CHARS,
    closest_passage,
    find_quote,
    html_text,
    link_in_html,
    link_in_text,
    link_text,
    mentions_any,
)
from public_atlas.modules.evidence.snapshots import (
    bytes_key,
    content_hash,
    latest_snapshot,
    mark_text_failed,
    mark_text_ready,
    share_text,
    snapshot_bytes,
    snapshot_text,
    store_snapshot,
    text_key,
)
from public_atlas.modules.graph.models import EnteredBy, Webpage
from public_atlas.modules.graph.service import normalize_url
from public_atlas.shared.exceptions import NotFoundError
from public_atlas.shared.text import normalize_text

__all__ = [
    "HTML",
    "MIN_QUOTE_CHARS",
    "PAGE_SEPARATOR",
    "EvidenceDetail",
    "FileParsing",
    "FileRefusal",
    "FileResult",
    "FileText",
    "PageCapture",
    "QuoteContext",
    "QuoteMatch",
    "add_evidence",
    "bytes_key",
    "check_link",
    "check_quote",
    "content_hash",
    "delete_objects",
    "evidence_context",
    "evidence_details",
    "evidence_for",
    "findings_of",
    "latest_snapshot",
    "mark_text_failed",
    "mark_text_ready",
    "mentions_any",
    "nearest_text",
    "prune_unreferenced",
    "quote_context",
    "read_file",
    "record_blocked",
    "record_redirect",
    "share_text",
    "snapshot_bytes",
    "snapshot_text",
    "store_snapshot",
    "text_key",
]

# --- The quote and link checks ---


@dataclass(frozen=True, slots=True)
class QuoteMatch:
    """Where a quote was found: the snapshot, and the page of a file."""

    snapshot: Snapshot
    locator: int | None


async def check_quote(
    session: AsyncSession, store: ObjectStore, webpage: Webpage, quote: str
) -> QuoteMatch | None:
    """Where `quote` appears in the newest stored copy of `webpage`, or None. A page never
    opened cannot vouch for anything. For a page the text of its stored HTML is tried after
    the rendered text: it has what the rendered text missed, such as a footer hidden until
    scrolled to."""
    snapshot = await latest_snapshot(session, webpage.id)
    if snapshot is None:
        return None
    found = find_quote(await snapshot_text(store, snapshot), quote)
    if found is None and snapshot.media_type == HTML:
        page_html = await snapshot_bytes(store, snapshot)
        if page_html is not None:
            found = find_quote(html_text(page_html.decode(errors="replace")), quote)
    if found is None:
        return None
    return QuoteMatch(snapshot=snapshot, locator=found.page)


async def nearest_text(
    session: AsyncSession, store: ObjectStore, webpage: Webpage, quote: str
) -> str | None:
    """The passage of `webpage`'s newest stored copy most like `quote`, for the agent to copy
    the page's own words from."""
    snapshot = await latest_snapshot(session, webpage.id)
    if snapshot is None:
        return None
    text = await snapshot_text(store, snapshot)
    if snapshot.media_type == HTML:
        page_html = await snapshot_bytes(store, snapshot)
        if page_html is not None:
            text = f"{text}\n{html_text(page_html.decode(errors='replace'))}"
    return closest_passage(text, quote)


async def check_link(
    store: ObjectStore, snapshot: Snapshot, page_url: str, target: str, *, quote: str | None = None
) -> str | None:
    """The link's text when the stored copy `snapshot` links to `target`, `target` itself when
    the link has no text, None when it does not link there. A page is checked in its stored
    HTML, a file in its text, where a URL in a cell is the link. An address written out in the
    finding's `quote` ("Township of Elmwood www.elmwood.ca") counts too: the quote was found on
    the page, beside the body it names."""
    if quote is not None and link_in_text(quote, page_url, target):
        return normalize_url(target)
    if snapshot.media_type == HTML:
        page_html = await snapshot_bytes(store, snapshot)
        if page_html is None:
            return None
        html = page_html.decode(errors="replace")
        if not link_in_html(html, page_url, target):
            return None
        return link_text(html, page_url, target) or normalize_url(target)
    if not link_in_text(await snapshot_text(store, snapshot), page_url, target):
        return None
    return normalize_url(target)


# --- Evidence ---


async def add_evidence(  # noqa: PLR0913
    session: AsyncSession,
    *,
    entity_id: uuid.UUID,
    snapshot: Snapshot,
    kind: EvidenceKind,
    quote: str,
    entered_by: EnteredBy,
    locator: int | None = None,
    link_url: str | None = None,
    assignment_id: uuid.UUID | None = None,
) -> bool:
    """Record the quote for the entity, once per snapshot and quote. Whether a row was added.
    The quote check runs before this for the agent's saves; a list's own line needs none."""
    quote = quote.strip()
    found = await session.scalar(
        select(Evidence.id)
        .where(
            Evidence.entity_id == entity_id,
            Evidence.snapshot_id == snapshot.id,
            Evidence.kind == kind,
            Evidence.quote == quote,
        )
        .limit(1)
    )
    if found is not None:
        return False
    session.add(
        Evidence(
            entity_id=entity_id,
            snapshot_id=snapshot.id,
            kind=kind,
            quote=quote,
            locator=locator,
            link_url=normalize_url(link_url) if link_url else None,
            assignment_id=assignment_id,
            entered_by=entered_by,
        )
    )
    await session.flush()
    return True


async def evidence_for(session: AsyncSession, entity_id: uuid.UUID) -> list[Evidence]:
    rows = await session.scalars(
        select(Evidence).where(Evidence.entity_id == entity_id).order_by(Evidence.id)
    )
    return list(rows)


async def findings_of(session: AsyncSession, assignment_id: uuid.UUID) -> list[Evidence]:
    """Every quote the assignment recorded, oldest first: what it saved."""
    rows = await session.scalars(
        select(Evidence).where(Evidence.assignment_id == assignment_id).order_by(Evidence.id)
    )
    return list(rows)


# How much of the page is shown around a quote.
CONTEXT_CHARS = 600


@dataclass(frozen=True, slots=True)
class QuoteContext:
    """A quote as it sits on the stored page: the text before it and after it, so a reader can
    see it where the rules found it. `found` is False when the stored text no longer has it
    (the copy was pruned, or the quote matched the page's HTML and not its rendered text), and
    then only the quote is given."""

    found: bool
    before: str
    quote: str
    after: str
    page: int | None


def quote_context(text: str, quote: str, *, chars: int = CONTEXT_CHARS) -> QuoteContext:
    """`quote` with up to `chars` of the text before and after it. The text is searched
    case-folded with its whitespace collapsed, as the quote check searches it."""
    pages = text.split(PAGE_SEPARATOR)
    for number, page in enumerate(pages, start=1):
        collapsed = " ".join(page.split())
        folded = normalize_text(collapsed)
        needle = normalize_text(quote)
        # Normalizing does not change the length of what `split` and `casefold` keep, except
        # for the rare character whose case folding grows; the slice is then off by a little.
        at = folded.find(needle) if needle else -1
        if at < 0 or len(folded) != len(collapsed):
            continue
        end = at + len(needle)
        return QuoteContext(
            found=True,
            before=collapsed[max(0, at - chars) : at],
            quote=collapsed[at:end],
            after=collapsed[end : end + chars],
            page=number if len(pages) > 1 else None,
        )
    return QuoteContext(found=False, before="", quote=quote, after="", page=None)


async def evidence_context(
    session: AsyncSession, store: ObjectStore, evidence_id: uuid.UUID
) -> tuple[Evidence, QuoteContext]:
    """The quote of `evidence_id` in the text of the stored copy it was taken from."""
    row = await session.get(Evidence, evidence_id)
    if row is None:
        raise NotFoundError("no such evidence")
    snapshot = await session.get_one(Snapshot, row.snapshot_id)
    text = await snapshot_text(store, snapshot)
    if snapshot.media_type == HTML and find_quote(text, row.quote) is None:
        page_html = await snapshot_bytes(store, snapshot)
        if page_html is not None:
            text = html_text(page_html.decode(errors="replace"))
    return row, quote_context(text, row.quote)


@dataclass(frozen=True, slots=True)
class EvidenceDetail:
    """A quote as the console shows it: with the page it was found on and a link to the stored
    copy, so a reader can check it as the rules did."""

    id: uuid.UUID
    entity_id: uuid.UUID
    quote: str
    kind: str
    locator: int | None
    link_url: str | None
    entered_by: str
    assignment_id: uuid.UUID | None
    page_url: str
    snapshot_id: uuid.UUID
    # A short-lived link to the stored copy; None once the copy was pruned.
    snapshot_url: str | None


async def evidence_details(
    session: AsyncSession,
    store: ObjectStore,
    entity_ids: Iterable[uuid.UUID],
    *,
    url_ttl: timedelta,
) -> list[EvidenceDetail]:
    """Every quote for any of `entity_ids`, oldest first, each with its page and a link to the
    stored copy it was found on."""
    ids = list(entity_ids)
    if not ids:
        return []
    rows = await session.execute(
        select(Evidence, Snapshot, Webpage)
        .join(Snapshot, Snapshot.id == Evidence.snapshot_id)
        .join(Webpage, Webpage.id == Snapshot.webpage_id)
        .where(Evidence.entity_id.in_(ids))
        .order_by(Evidence.id)
    )
    details: list[EvidenceDetail] = []
    for row, snapshot, webpage in rows.tuples():
        url = None
        if snapshot.pruned_at is None:
            url = await store.download_url(
                snapshot.bytes_key, snapshot.filename or "snapshot", url_ttl
            )
        details.append(
            EvidenceDetail(
                id=row.id,
                entity_id=row.entity_id,
                quote=row.quote,
                kind=row.kind.value,
                locator=row.locator,
                link_url=row.link_url,
                entered_by=row.entered_by.value,
                assignment_id=row.assignment_id,
                page_url=webpage.url,
                snapshot_id=snapshot.id,
                snapshot_url=url,
            )
        )
    return details
