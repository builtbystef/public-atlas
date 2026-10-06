"""`save_homepage`: an institution's homepage, and what its domain's state makes of the claim
(spec sections 6.1 and 7.2). On a trusted domain or a platform the page itself is read and
quoted before it is verified; on a new domain the claim becomes a candidate, which a
`find_homepage` session opens and decides with the domain tools."""

import uuid
from dataclasses import dataclass

from pydantic_ai import RunContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.agent.context import SessionContext
from public_atlas.modules.agent.findings.shared import (
    FindingError,
    Page,
    absolute_url,
    add_quote,
    describe_assignments,
    in_session,
    matched_quote,
    name_texts,
    quote_names,
    spawn,
    subject_institution,
    visited_page,
)
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.evidence.models import EvidenceKind
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import (
    Domain,
    DomainKind,
    EnteredBy,
    EntityStatus,
    Homepage,
    Institution,
    Webpage,
)
from public_atlas.modules.review import service as review

OPEN = (EntityStatus.CANDIDATE, EntityStatus.NEEDS_REVIEW)


@dataclass(frozen=True, slots=True)
class SavedHomepage:
    """What became of the claim: verified, a candidate (this session's or another assignment's),
    or waiting on a human."""

    url: str
    institution_id: uuid.UUID
    claim_status: EntityStatus
    message: str

    def __str__(self) -> str:
        return self.message


async def save_homepage(  # noqa: PLR0913
    ctx: RunContext[SessionContext],
    *,
    url: str,
    institution_id: str | None = None,
    found_on_url: str | None = None,
    link_quote: str | None = None,
    page_quote: str | None = None,
) -> SavedHomepage:
    """Save an institution's homepage: its official starting page on the web, not an
    article about it or a directory that lists it. From a page that links to it, pass
    found_on_url and link_quote (the verbatim text around the link, naming the
    institution; an address the page writes out counts as the link). On a domain you
    can open (a trusted one, or a platform) the page is verified from its own text:
    open it, judge it the institution's own, and pass page_quote, a verbatim phrase
    from it that names the institution. On a new domain it becomes a candidate: in
    find_homepage your own to open and decide with confirm_domain, reject_domain or
    domain_moved; otherwise a find_homepage assignment decides it. In find_homepage a
    search result's site needs no linking page.

    Args:
        url: The homepage's URL: the exact href the page links to, the address it
            writes out, or the search result's URL.
        institution_id: The institution it belongs to. Defaults to this assignment's
            subject.
        found_on_url: The page the link is on (one you opened).
        link_quote: The verbatim text around the link, naming the institution.
        page_quote: A verbatim phrase from the page at url that names the institution,
            copied after you read the page.
    """
    return await in_session(
        ctx,
        lambda session: record_homepage(
            ctx.deps,
            session,
            url=url,
            institution_id=institution_id,
            found_on_url=found_on_url,
            link_quote=link_quote,
            page_quote=page_quote,
        ),
    )


async def record_homepage(  # noqa: PLR0913
    ctx: SessionContext,
    session: AsyncSession,
    *,
    url: str,
    institution_id: str | None = None,
    found_on_url: str | None = None,
    link_quote: str | None = None,
    page_quote: str | None = None,
) -> SavedHomepage:
    institution = await subject_institution(ctx, session, institution_id)
    url = absolute_url(url)
    held = await _held_already(session, institution, url)
    if held is not None:
        return held
    names = await name_texts(session, institution)
    linking, link_match = await _linking_page(
        ctx, session, institution, names, url, found_on_url, link_quote
    )
    domain = await graph.domain_of_host(session, graph.host_of(url))
    if domain is not None and domain.status is EntityStatus.REJECTED:
        raise FindingError(
            f"{domain.name} was rejected as an official domain earlier (dead, parked, or "
            "another body's). Keep looking for the institution's current homepage."
        )
    webpage = await graph.ensure_webpage(session, url, assignment_id=ctx.assignment_id)
    claim = await _claim(session, institution, webpage, linking)
    if link_match is not None and link_quote is not None:
        await add_quote(
            ctx, session, claim.id, link_match, link_quote, kind=EvidenceKind.LINKS_TO, link_url=url
        )
    if domain is not None and (
        graph.is_trusted(domain) or domain.domain_kind is DomainKind.PLATFORM
    ):
        return await _verify_from_own_text(
            ctx, session, institution, names, claim, webpage, domain, linking, page_quote
        )
    if domain is None:
        domain, _ = await graph.ensure_domain(
            session, graph.host_of(url), entered_by=EnteredBy.AGENT
        )
        webpage.domain_id = domain.id
        await session.flush()
    return _candidate_outcome(ctx, institution, claim, webpage, domain, linked=linking is not None)


async def _held_already(
    session: AsyncSession, institution: Institution, url: str
) -> SavedHomepage | None:
    """Why the institution takes no new claim on `url`: it has its verified homepage already."""
    if institution.homepage_id is None:
        return None
    current = await session.get_one(Homepage, institution.homepage_id)
    current_page = await session.get_one(Webpage, current.webpage_id)
    if current_page.url == url:
        return SavedHomepage(
            url=url,
            institution_id=institution.id,
            claim_status=EntityStatus.VERIFIED,
            message=f"{url} is the verified homepage of {institution.name!r} already.",
        )
    raise FindingError(
        f"{institution.name!r} has a verified homepage already: {current_page.url}. If that one "
        "is wrong, call request_review on the institution with what you saw."
    )


async def _linking_page(  # noqa: PLR0913, PLR0917
    ctx: SessionContext,
    session: AsyncSession,
    institution: Institution,
    names: list[str],
    url: str,
    found_on_url: str | None,
    link_quote: str | None,
) -> tuple[Page | None, evidence.QuoteMatch | None]:
    """The trusted page that links to the claim with the checked link quote, or (None, None)
    for a claim with no linking page, which only a `find_homepage` session may make for its
    own subject, from a site its searches returned or its candidate domain."""
    if found_on_url is None:
        if link_quote is not None:
            raise FindingError("link_quote goes with found_on_url: the page the link is on.")
        if not _may_claim_unlinked(ctx, institution, url):
            raise FindingError(
                f"Pass found_on_url and link_quote: the page you opened that links to {url} and "
                "the text around the link. Only a find_homepage session may save a search "
                "result's site without one."
            )
        return None, None
    if link_quote is None:
        raise FindingError(
            "Pass link_quote with found_on_url: the verbatim text around the link, naming the "
            "institution."
        )
    linking = await visited_page(session, found_on_url)
    match = await matched_quote(ctx, session, linking, link_quote)
    quote_names(link_quote, names, "institution", naming=ctx.rules.naming)
    link = await evidence.check_link(
        ctx.store, match.snapshot, linking.webpage.url, url, quote=link_quote
    )
    if link is None:
        raise FindingError(
            f"The stored copy of {linking.webpage.url} has no link to {url}. Pass the exact href "
            "the page uses (snapshot shows links), the URL as a file's cell spells it, or a "
            "link_quote in which the page writes the address out."
        )
    # A link on an untrusted page gets the claim in and vouches for nothing: the claim has no
    # linking page on record.
    return (linking if linking.trusted else None), match


def _may_claim_unlinked(ctx: SessionContext, institution: Institution, url: str) -> bool:
    if not ctx.finding_homepage or institution.id != ctx.subject.id:
        return False
    host = graph.host_of(url)
    if ctx.candidate is not None and _covers(host, ctx.candidate.domain_name):
        return True
    return any(_covers(host, found) for found in ctx.search_hosts)


def _covers(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


async def _claim(
    session: AsyncSession, institution: Institution, webpage: Webpage, linking: Page | None
) -> Homepage:
    """The institution's open claim on the page, or a new candidate one. A trusted linking page
    found later is recorded on an existing claim."""
    claim = await session.scalar(
        select(Homepage).where(
            Homepage.institution_id == institution.id,
            Homepage.webpage_id == webpage.id,
            Homepage.status.in_(OPEN),
        )
    )
    if claim is None:
        return await graph.create_homepage(
            session,
            institution,
            webpage,
            entered_by=EnteredBy.AGENT,
            found_on=linking.webpage if linking is not None else None,
        )
    if linking is not None and claim.found_on_webpage_id is None:
        claim.found_on_webpage_id = linking.webpage.id
        await session.flush()
    return claim


async def _verify_from_own_text(  # noqa: PLR0913, PLR0917
    ctx: SessionContext,
    session: AsyncSession,
    institution: Institution,
    names: list[str],
    claim: Homepage,
    webpage: Webpage,
    domain: Domain,
    linking: Page | None,
    page_quote: str | None,
) -> SavedHomepage:
    """On a decided domain the page vouches for itself: the agent opened it, judged it the
    institution's own and quoted it. A platform page needs a trusted page linking to it as well
    (spec section 6.4); without one a human decides."""
    what = "trusted" if graph.is_trusted(domain) else "a platform"
    if page_quote is None:
        return SavedHomepage(
            url=webpage.url,
            institution_id=institution.id,
            claim_status=claim.status,
            message=(
                f"Recorded {webpage.url} as a candidate homepage; {domain.name} is {what}, so the "
                "page is verified from its own text. Open it and read it. If it is the "
                "institution's own page, and not an article about it or a list that mentions "
                "it, call save_homepage again with page_quote: a phrase from the page that names "
                "the institution."
            ),
        )
    target = await visited_page(session, webpage.url)
    match = await matched_quote(ctx, session, target, page_quote)
    quote_names(page_quote, names, "institution", naming=ctx.rules.naming)
    await add_quote(ctx, session, claim.id, match, page_quote)
    other = await graph.verified_homepage_owner(session, webpage, excluding=institution)
    if other is not None:
        raise FindingError(
            f"{webpage.url} is the verified homepage of {other.name!r} (id {other.id}) already. "
            "If that is the same body, save this one with save_institution and "
            f"decision={other.id}; if two bodies share a page, call request_review."
        )
    if domain.domain_kind is DomainKind.PLATFORM and linking is None:
        reason = (
            f"{webpage.url} is on the platform {domain.name} and no trusted page links to it; "
            "the page names the institution. A human decides whether it is the institution's "
            "homepage."
        )
        await review.raise_review(
            session,
            claim,
            rule=review.Rule.PLATFORM_HOMEPAGE,
            reason=reason,
            question={"page_url": webpage.url, "platform": domain.name},
            assignment_id=ctx.assignment_id,
        )
        return SavedHomepage(
            url=webpage.url,
            institution_id=institution.id,
            claim_status=EntityStatus.NEEDS_REVIEW,
            message=f"Saved {webpage.url} as a candidate homepage, sent to review: {reason}",
        )
    spawns = await status_changes.verify_homepage(session, claim, entered_by=EnteredBy.AGENT)
    created = await spawn(ctx, session, spawns)
    why = "is trusted" if what == "trusted" else "is a platform and a trusted page links to it"
    message = (
        f"Verified {webpage.url} as the homepage of {institution.name!r} ({domain.name} {why}). "
        f"Queued: {describe_assignments(created)}."
    )
    if ctx.finding_homepage and institution.id == ctx.subject.id:
        message += " Finish with a summary."
    return SavedHomepage(
        url=webpage.url,
        institution_id=institution.id,
        claim_status=EntityStatus.VERIFIED,
        message=message,
    )


def _candidate_outcome(  # noqa: PLR0913
    ctx: SessionContext,
    institution: Institution,
    claim: Homepage,
    webpage: Webpage,
    domain: Domain,
    *,
    linked: bool,
) -> SavedHomepage:
    """A claim on a new or candidate domain. In `find_homepage`, for the subject, the session
    takes the domain as its candidate and opens it; elsewhere a `find_homepage` assignment is
    spawned when this one finishes. A domain a reviewer holds waits for them."""
    if domain.status is EntityStatus.NEEDS_REVIEW:
        return SavedHomepage(
            url=webpage.url,
            institution_id=institution.id,
            claim_status=claim.status,
            message=(
                f"Recorded {webpage.url} as a candidate homepage; a human is deciding on "
                f"{domain.name}, and nothing else happens until they do."
            ),
        )
    unlinked = (
        ""
        if linked
        else (
            " No trusted page links to it, so a confirmation goes to a human with your quotes; "
            "a trusted page that links to it or writes its address out, saved with "
            "save_homepage, would let the checks verify it."
        )
    )
    if ctx.finding_homepage and institution.id == ctx.subject.id:
        ctx.take_candidate(domain, claim)
        return SavedHomepage(
            url=webpage.url,
            institution_id=institution.id,
            claim_status=claim.status,
            message=(
                f"Recorded {webpage.url} as a candidate homepage on the candidate domain "
                f"{domain.name}, which is yours to decide. Open what you have not read yet: the "
                "home page with and without www, about, contact, the footer. Then decide it: "
                "confirm_domain with quotes naming the institution, domain_moved when it "
                "redirects to another domain, reject_domain when it is dead, parked or not the "
                f"institution's.{unlinked}"
            ),
        )
    return SavedHomepage(
        url=webpage.url,
        institution_id=institution.id,
        claim_status=claim.status,
        message=(
            f"Recorded {webpage.url} as a candidate homepage; {domain.name} is a candidate domain, "
            f"which a find_homepage assignment for {institution.name!r} decides.{unlinked}"
        ),
    )
