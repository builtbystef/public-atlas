"""`save_source`: the trust rules for a page that carries procurement signals (spec sections
6.1 and 6.4). A page on a trusted domain is verified from its quote; a page under a platform
homepage's trusted path likewise; a page elsewhere on a platform needs a trusted page linking
to it and must name the institution, or a human decides."""

import uuid
from dataclasses import dataclass

from pydantic_ai import RunContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.agent.context import SessionContext
from public_atlas.modules.agent.findings.shared import (
    FindingError,
    Page,
    add_quote,
    in_session,
    matched_quote,
    name_texts,
    subject_institution,
    visited_page,
)
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.evidence.models import EvidenceKind, Snapshot
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import (
    EnteredBy,
    EntityStatus,
    Homepage,
    Institution,
    Source,
    SourceAccess,
)
from public_atlas.modules.review import service as review


@dataclass(frozen=True, slots=True)
class Trust:
    """What the rules make of a source page: verified, or why a human is needed; for a page
    on a platform, the trusted page that links to it with the stored copy the link was found
    in and the link's own wording."""

    verified: bool
    note: str | None = None
    platform: str | None = None
    linking: Page | None = None
    link_snapshot: Snapshot | None = None
    link_text: str | None = None


@dataclass(frozen=True, slots=True)
class SavedSource:
    source_id: uuid.UUID
    source_type: str
    url: str
    status: EntityStatus
    # "Saved", "Verified" (a candidate advanced), "Already recorded".
    verb: str
    note: str | None

    def __str__(self) -> str:
        if self.status is EntityStatus.VERIFIED and self.note:
            return (
                f"Source {self.source_type} id={self.source_id} is already verified; evidence "
                f"added. ({self.note})"
            )
        if self.note:
            return f"Saved source {self.source_type} id={self.source_id} for review: {self.note}"
        return (
            f"{self.verb} source {self.source_type} id={self.source_id} at {self.url}, status "
            f"{self.status.value}."
        )


async def save_source(  # noqa: PLR0913
    ctx: RunContext[SessionContext],
    *,
    url: str,
    source_type: str,
    quote: str,
    institution_id: str | None = None,
    access: str = "public",
    linked_from_url: str | None = None,
) -> SavedSource:
    """Save a page that carries procurement signals: the procurement page, the open
    tenders, the budget, the council minutes, and so on. The page itself is the
    finding; quote from its own text. Open it first.

    Args:
        url: The page's URL (one you opened).
        source_type: One of the country's source types, e.g. "procurement".
        quote: A verbatim phrase from the page showing what it is.
        institution_id: The institution it belongs to. Defaults to this assignment's
            subject.
        access: "public", or "login" when suppliers must sign in to see it.
        linked_from_url: For a page on a platform (a bids portal, a meetings host): the
            trusted page that links to it.
    """
    return await in_session(
        ctx,
        lambda session: record_source(
            ctx.deps,
            session,
            url=url,
            source_type=source_type,
            quote=quote,
            institution_id=institution_id,
            access=access,
            linked_from_url=linked_from_url,
        ),
    )


async def record_source(  # noqa: PLR0913
    ctx: SessionContext,
    session: AsyncSession,
    *,
    url: str,
    source_type: str,
    quote: str,
    institution_id: str | None = None,
    access: str = "public",
    linked_from_url: str | None = None,
) -> SavedSource:
    rules = ctx.rules
    if source_type not in rules.source_types:
        raise FindingError(
            f"Unknown source type {source_type!r}. Types: {', '.join(sorted(rules.source_types))}."
        )
    try:
        access_value = SourceAccess(access)
    except ValueError:
        raise FindingError("access must be 'public' or 'login'.") from None
    institution = await subject_institution(ctx, session, institution_id)
    page = await visited_page(session, url)
    match = await matched_quote(ctx, session, page, quote)
    trust = await _trust(ctx, session, page, institution, linked_from_url)

    source = await session.scalar(
        select(Source).where(
            Source.webpage_id == page.webpage.id,
            Source.institution_id == institution.id,
            Source.source_type == source_type,
        )
    )
    verb = "Already recorded"
    if source is None:
        verb = "Saved"
        source = await graph.create_source(
            session,
            institution,
            page.webpage,
            source_type=source_type,
            entered_by=EnteredBy.AGENT,
            access=access_value,
        )
    await add_quote(ctx, session, source.id, match, quote)
    if trust.verified:
        if trust.link_snapshot is not None and trust.linking is not None:
            # The trusted half of a platform source's chain. Recording it against the trusted
            # page's copy keeps that copy from being pruned.
            await evidence.add_evidence(
                session,
                entity_id=source.id,
                snapshot=trust.link_snapshot,
                kind=EvidenceKind.LINKS_TO,
                quote=trust.link_text or page.webpage.url,
                entered_by=EnteredBy.AGENT,
                link_url=page.webpage.url,
                assignment_id=ctx.assignment_id,
            )
        if source.status is not EntityStatus.VERIFIED:
            if verb == "Already recorded":
                verb = "Verified"
            # Stronger evidence advances a row: the access is what this call established.
            source.access = access_value
            await status_changes.verify_source(session, source, entered_by=EnteredBy.AGENT)
        return SavedSource(source.id, source_type, page.webpage.url, source.status, verb, None)
    if source.status is EntityStatus.VERIFIED:
        # Weaker evidence does not undo what the rules verified.
        return SavedSource(
            source.id, source_type, page.webpage.url, source.status, verb, trust.note
        )
    await review.raise_review(
        session,
        source,
        rule=review.Rule.PLATFORM_SOURCE,
        reason=trust.note or "the page is on a platform",
        question={
            "page_url": page.webpage.url,
            "source_type": source_type,
            "platform": trust.platform,
            "linking_url": trust.linking.webpage.url if trust.linking else None,
            "link_text": trust.link_text,
        },
        assignment_id=ctx.assignment_id,
    )
    return SavedSource(source.id, source_type, page.webpage.url, source.status, verb, trust.note)


async def _trust(  # noqa: PLR0911 - one return per rule
    ctx: SessionContext,
    session: AsyncSession,
    page: Page,
    institution: Institution,
    linked_from_url: str | None,
) -> Trust:
    """A source on a trusted domain is verified; so is one under the institution's own
    platform homepage (its trusted path); one elsewhere on a platform is verified when a
    trusted page links to it and it names the institution (spec section 6.4)."""
    if page.trusted:
        return Trust(verified=True)
    if not page.platform:
        raise FindingError(
            f"{page.webpage.url} is on a domain that is not trusted and is not a platform. A "
            "source is saved on a trusted domain, or on a platform a trusted page links to."
        )
    assert page.domain is not None  # noqa: S101 - `platform` implies a domain
    platform = page.domain.name
    if await _under_trusted_path(session, institution, page.webpage.url):
        return Trust(verified=True, platform=platform)
    if linked_from_url is None:
        return Trust(
            verified=False,
            note=(
                f"The page is on the platform {platform}; pass linked_from_url, the trusted page "
                "that links to it."
            ),
            platform=platform,
        )
    linking = await visited_page(session, linked_from_url)
    if not linking.trusted:
        return Trust(
            verified=False,
            note=f"{linking.webpage.url} is not on a trusted domain.",
            platform=platform,
            linking=linking,
        )
    # `visited_page` proved a stored copy exists; the link is checked in that one.
    snapshot = await evidence.latest_snapshot(session, linking.webpage.id)
    assert snapshot is not None  # noqa: S101 - `visited_page` requires it
    link = await _link_to(ctx, session, snapshot, linking.webpage.url, page.webpage.url)
    if link is None:
        return Trust(
            verified=False,
            note=f"The stored copy of {linking.webpage.url} has no link to {page.webpage.url}.",
            platform=platform,
            linking=linking,
        )
    own = await evidence.latest_snapshot(session, page.webpage.id)
    text = await evidence.snapshot_text(ctx.store, own) if own is not None else ""
    names = await name_texts(session, institution)
    if not evidence.mentions_any(text, names, key=ctx.rules.naming.key):
        return Trust(
            verified=False,
            note=f"The page does not name the institution ({', '.join(names)}).",
            platform=platform,
            linking=linking,
            link_text=link,
        )
    return Trust(
        verified=True, platform=platform, linking=linking, link_snapshot=snapshot, link_text=link
    )


async def _under_trusted_path(session: AsyncSession, institution: Institution, url: str) -> bool:
    """Whether `url` sits under the institution's verified platform homepage (spec section
    6.4): those pages vouch for this one institution as a trusted domain's would."""
    if institution.homepage_id is None:
        return False
    homepage = await session.get_one(Homepage, institution.homepage_id)
    return homepage.trusted_path is not None and graph.under_trusted_path(
        url, homepage.trusted_path
    )


async def _link_to(
    ctx: SessionContext, session: AsyncSession, snapshot: Snapshot, page_url: str, target: str
) -> str | None:
    """`check_link` for `target`, or for an address the browser is on record as redirecting to
    it: a page may link `portal.biddingo.com/landingpage/x`, which answers from
    `biddingo.com/x`, the address the agent landed on."""
    link = await evidence.check_link(ctx.store, snapshot, page_url, target)
    if link is not None:
        return link
    for start in await graph.redirected_from(session, target):
        link = await evidence.check_link(ctx.store, snapshot, page_url, start)
        if link is not None:
            return link
    return None
