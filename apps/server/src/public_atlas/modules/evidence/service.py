"""The evidence module's door: storing a copy of a page or file with its text, the quotes taken
from it, and the checks a quote or link must pass against a stored copy (spec section 6.2).

Bytes and text are keyed by content hash in the object store, so identical bytes fetched twice,
by whoever and from whatever URL, share one copy of each; a snapshot row is one fetch. A
snapshot's text is `ready` at once for a page or a plain-text file, `parsing` until the parse
queue has done a document, and `failed` with the reason when it cannot be made.
"""

import uuid
from dataclasses import dataclass

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

__all__ = [
    "HTML",
    "MIN_QUOTE_CHARS",
    "PAGE_SEPARATOR",
    "FileParsing",
    "FileRefusal",
    "FileResult",
    "FileText",
    "PageCapture",
    "QuoteMatch",
    "add_evidence",
    "bytes_key",
    "check_link",
    "check_quote",
    "content_hash",
    "delete_objects",
    "evidence_for",
    "latest_snapshot",
    "mark_text_failed",
    "mark_text_ready",
    "mentions_any",
    "nearest_text",
    "prune_unreferenced",
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
