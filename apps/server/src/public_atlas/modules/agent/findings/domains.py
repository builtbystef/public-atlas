"""The domain decisions of a `find_homepage` session (spec sections 6.3 and 7.2): `confirm_domain`
runs every check before the candidate domain is trusted, `reject_domain` closes a dead or
unrelated site, and `domain_moved` follows a recorded redirect to another domain."""

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import RunContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.agent.context import Candidate, SessionContext
from public_atlas.modules.agent.findings.shared import (
    FindingError,
    absolute_url,
    add_quote,
    describe_assignments,
    in_session,
    page_of,
    require_name,
    spawn,
    visited_page,
)
from public_atlas.modules.assignments.models import AssignmentResult
from public_atlas.modules.countries.naming import Naming
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.evidence.models import Evidence, EvidenceKind, Snapshot
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import (
    Alias,
    Domain,
    DomainKind,
    EnteredBy,
    EntityStatus,
    Homepage,
    Institution,
    Webpage,
)
from public_atlas.modules.review import service as review

# A failed check the agent can put right (a mistyped quote, a page it never opened) is sent back
# with what to fix, up to this many `confirm_domain` calls per session; then the domain goes to
# a human. A check it cannot put right (another institution's homepage) goes to a human at once.
MAX_CONFIRM_ATTEMPTS = 3
# "College" names nothing, "Fanshawe College" does.
MIN_SITE_NAME_WORDS = 2


class DomainQuote(BaseModel):
    url: str = Field(description="A page on the candidate domain that you opened.")
    quote: str = Field(
        description="A verbatim phrase from it showing the site is the institution's."
    )


@dataclass(frozen=True, slots=True)
class Decided:
    """How a decision left the assignment: ended with a result, or still going with the next
    step for the agent."""

    message: str
    result: AssignmentResult | None = None

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class Subject:
    domain: Domain
    homepage: Homepage
    institution: Institution
    webpage: Webpage


async def confirm_domain(
    ctx: RunContext[SessionContext], quotes: list[DomainQuote], name_used: str | None = None
) -> Decided:
    """Decide that the candidate domain is the institution's own. Give quotes from the
    domain's pages; at least one must contain the institution's name or acronym. The
    backend checks every quote and the trusted link before anything becomes verified,
    and when a check fails on something you can fix (a quote that is not word for word,
    a page you did not open) it tells you what, with the page's closest wording: fix it
    and call again. This ends the assignment.

    Args:
        quotes: One or more quotes, each with the page it is on.
        name_used: The name the site calls the institution by, when it is the opening
            words of a recorded name ("Fanshawe College" for "Fanshawe College of
            Applied Arts and Technology") or its place name with another designator
            ("Elmwood Township" for "Township of Elmwood"); a quote must contain it.
            Leave it out when a quote contains a recorded name.
    """
    return await in_session(
        ctx,
        lambda session: confirm_candidate(
            ctx.deps,
            session,
            [Quote(url=q.url, quote=q.quote) for q in quotes],
            name_used=name_used,
        ),
    )


async def reject_domain(
    ctx: RunContext[SessionContext], reason: str, *, another_body: bool = False
) -> Decided:
    """Decide that the candidate domain is not the institution's: a dead site (it does
    not resolve, refuses or drops the connection, times out, or every page is an error
    or empty), a domain parked or for sale, or an unrelated site. Then keep looking: the
    next candidate you save is decided the same way, or finish when there is nothing
    more to try. For a platform that many bodies publish on, or a live site that
    refuses you (Access Denied, a captcha), call request_review on the domain instead.

    Args:
        reason: What you saw.
        another_body: True when the site is the official site of another public body
            (a neighbouring municipality, a city with the same place name): only this
            institution's claim is withdrawn, and the domain stays open for the body it
            belongs to.
    """
    return await in_session(
        ctx,
        lambda session: reject_candidate(ctx.deps, session, reason, another_body=another_body),
    )


async def domain_moved(ctx: RunContext[SessionContext], url: str) -> Decided:
    """Decide that the candidate homepage has moved: opening it, or the domain's home
    page with or without www, redirects to a page on another domain, which navigate
    reported as outside the allowed domains. The backend checks that the browser saw
    that redirect and records the new page as the institution's candidate homepage: on
    a trusted domain it is verified; on a new domain it becomes your candidate to open
    and decide.

    Args:
        url: The URL the candidate redirects to, as navigate reported it.
    """
    return await in_session(ctx, lambda session: candidate_moved(ctx.deps, session, url))


@dataclass(frozen=True, slots=True)
class Quote:
    url: str
    quote: str


async def _subject(ctx: SessionContext, session: AsyncSession) -> tuple[Candidate, Subject]:
    """The claim the session is deciding on, reloaded."""
    candidate = ctx.candidate
    if candidate is None or not ctx.finding_homepage:
        raise FindingError(
            "No candidate to decide on: save the institution's homepage first (save_homepage "
            "from a page that links to it, or from a search result), then decide it."
        )
    homepage = await session.get_one(Homepage, candidate.homepage_id)
    return candidate, Subject(
        domain=await session.get_one(Domain, candidate.domain_id),
        homepage=homepage,
        institution=await session.get_one(Institution, homepage.institution_id),
        webpage=await session.get_one(Webpage, homepage.webpage_id),
    )


# --- confirm_domain ---


async def confirm_candidate(  # noqa: C901, PLR0912, PLR0915 - one pass over every check
    ctx: SessionContext,
    session: AsyncSession,
    quotes: Sequence[Quote],
    *,
    name_used: str | None = None,
) -> Decided:
    """The agent says the candidate domain is the institution's. When every check of spec
    section 6.3 passes the domain is trusted, the homepage verified and the follow-up work
    spawned; a fixable failure is sent back; a claim no trusted page links to goes to a human
    with the quotes, as does one the checks refuse for good."""
    _, subject = await _subject(ctx, session)
    domain, homepage, institution, webpage = (
        subject.domain,
        subject.homepage,
        subject.institution,
        subject.webpage,
    )
    if not quotes:
        raise FindingError("Pass at least one quote from the candidate domain's own pages.")
    # What another call could put right, and what no call could.
    fixable: list[str] = []
    fatal: list[str] = []
    matches: list[tuple[Quote, evidence.QuoteMatch]] = []
    unlinked = await _linking_failures(ctx, session, homepage, webpage)

    for quote in quotes:
        try:
            page = await visited_page(session, quote.url)
        except FindingError as exc:
            fixable.append(str(exc))
            continue
        if not _covers(graph.host_of(page.webpage.url), domain.name):
            fixable.append(f"{page.webpage.url} is not on {domain.name}")
            continue
        match = await evidence.check_quote(session, ctx.store, page.webpage, quote.quote)
        if match is None:
            nearest = await evidence.nearest_text(session, ctx.store, page.webpage, quote.quote)
            hint = f" (the closest text on that page: {nearest!r})" if nearest else ""
            fixable.append(f"quote not found on {page.webpage.url}: {quote.quote[:80]!r}{hint}")
        else:
            matches.append((quote, match))

    names = await graph.names_of(session, institution)
    site_name: tuple[str, str] | None = None
    if name_used is not None:
        try:
            site_name = _site_name(ctx.rules.naming, name_used, names)
        except FindingError as exc:
            fixable.append(str(exc))
    wanted = [name.text for name in names]
    if site_name is not None:
        wanted.append(site_name[0])
    naming = ctx.rules.naming
    if matches and not any(
        evidence.mentions_any(q.quote, wanted, key=naming.key) for q, _ in matches
    ):
        fixable.append(
            f"no quote contains the institution's name or acronym ({', '.join(wanted)}). When "
            'the site calls itself by the opening words of a recorded name ("Fanshawe College" '
            'for "Fanshawe College of Applied Arts and Technology"), or by its place name with '
            'another designator ("Elmwood Township" for "Township of Elmwood"), pass that as '
            "name_used with a quote that contains it"
        )

    other = await graph.verified_homepage_owner(session, webpage, excluding=institution)
    if other is not None:
        fatal.append(
            f"{other.name!r} ({other.id}) has {webpage.url} as its verified homepage already"
        )

    ctx.confirm_attempts += 1
    if fixable and not fatal and ctx.confirm_attempts < MAX_CONFIRM_ATTEMPTS:
        raise FindingError(
            f"Not confirmed, nothing saved (attempt {ctx.confirm_attempts} of "
            f"{MAX_CONFIRM_ATTEMPTS}). Put these right and call confirm_domain again, with "
            "every quote copied exactly as the page writes it:\n- " + "\n- ".join(fixable)
        )

    for quote, match in matches:
        await add_quote(ctx, session, domain.id, match, quote.quote)
        if match.snapshot.webpage_id == webpage.id:
            await add_quote(ctx, session, homepage.id, match, quote.quote)
    failures = [*fatal, *fixable, *unlinked]
    if failures:
        reason = "confirm_domain checks failed:\n- " + "\n- ".join(failures)
        await review.raise_review(
            session,
            domain,
            rule=review.Rule.DOMAIN_CHECKS,
            reason=reason,
            question={"homepage_id": str(homepage.id), "institution_id": str(institution.id)},
            assignment_id=ctx.assignment_id,
        )
        # The claim waits with its domain, so no new search is spawned meanwhile.
        await status_changes.send_to_review(session, homepage)
        # Only the missing trusted link: the agent and the checks agree, a reviewer approves
        # (spec section 7.2). Anything else is a disagreement.
        result = (
            AssignmentResult.COMPLETE
            if not fatal and not fixable
            else AssignmentResult.NEEDS_REVIEW
        )
        ctx.drop_candidate()
        ctx.end(result, reason)
        return Decided(f"The domain goes to a human: {reason}", result)

    spawns = await status_changes.verify_domain(session, domain, entered_by=EnteredBy.AGENT)
    spawns.extend(
        await status_changes.verify_homepage(session, homepage, entered_by=EnteredBy.AGENT)
    )
    if site_name is not None:
        # The site's own name for the institution, vouched for by the trusted link and the
        # quote that carries it.
        await graph.add_alias(
            session, institution, site_name[0], language=site_name[1], entered_by=EnteredBy.AGENT
        )
    created = await spawn(ctx, session, spawns)
    summary = (
        f"Verified {domain.name} as an official domain of {institution.name!r}; {webpage.url} is "
        f"its homepage. Queued: {describe_assignments(created)}."
    )
    ctx.drop_candidate()
    ctx.end(AssignmentResult.COMPLETE, summary)
    return Decided(summary, AssignmentResult.COMPLETE)


def _covers(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def _site_name(naming: Naming, name_used: str, names: Sequence[Alias]) -> tuple[str, str]:
    """The name the site uses for the institution, with the language of the recorded name it
    matches: the opening words of a recorded name, or a government's place name with another
    designator ("Elmwood Township" for "Township of Elmwood")."""
    used = require_name(name_used, "site")
    needle = naming.without_leading(naming.key(used))
    if len(needle.split()) < MIN_SITE_NAME_WORDS:
        raise FindingError(
            f"name_used {used!r} is too short: pass at least {MIN_SITE_NAME_WORDS} words of the "
            "recorded name, as the site writes them."
        )
    recorded = [name for name in names if not name.is_acronym]
    for name in recorded:
        full = naming.without_leading(naming.key(name.text))
        if full == needle or full.startswith(f"{needle} "):
            return used, name.language
    if naming.designators_in(used):
        core = naming.core(used)
        for name in recorded:
            if naming.designators_in(name.text) and naming.core(name.text) == core:
                return used, name.language
    raise FindingError(
        f"name_used {used!r} does not begin any recorded name of the institution "
        f"({', '.join(name.text for name in recorded)}), nor is it one of them with another "
        "designator. It must be the opening words of one, or its place name with the site's "
        "designator, as the site writes them; a different name goes to request_review."
    )


async def _trusted_link(
    session: AsyncSession, homepage: Homepage
) -> tuple[Webpage, Evidence, Snapshot] | None:
    """The trusted page on record as linking to the claim, with the `links_to` quote and the
    stored copy it was found in: the page the claim was found on when it has one, else any
    trusted page a `links_to` quote cites, such as the official list the loader read (a register
    is trusted from the start, spec section 6.1). The linking page's domain must be trusted now,
    not just then."""
    rows = await session.execute(
        select(Evidence, Snapshot)
        .join(Snapshot, Snapshot.id == Evidence.snapshot_id)
        .where(Evidence.entity_id == homepage.id, Evidence.kind == EvidenceKind.LINKS_TO)
        .order_by(Evidence.id)
    )
    found = rows.all()
    preferred = [
        (row, snapshot)
        for row, snapshot in found
        if snapshot.webpage_id == homepage.found_on_webpage_id
    ]
    for row, snapshot in [*preferred, *found]:
        linking = await session.get_one(Webpage, snapshot.webpage_id)
        if (await page_of(session, linking)).trusted:
            return linking, row, snapshot
    return None


async def _linking_failures(
    ctx: SessionContext, session: AsyncSession, homepage: Homepage, webpage: Webpage
) -> list[str]:
    """Why no trusted page vouches for the candidate homepage, as one failure or none (spec
    section 6.3). The link is checked in the copy the evidence cites. A link to a URL the
    browser was redirected from counts when the redirect to the candidate is on record."""
    link = await _trusted_link(session, homepage)
    if link is None:
        if homepage.found_on_webpage_id is None:
            return [
                (
                    f"no trusted page links to {webpage.url}: it was found by a web search or on "
                    "an untrusted page, so a human decides, with the quotes recorded here"
                )
            ]
        found_on = await session.get_one(Webpage, homepage.found_on_webpage_id)
        return [
            (
                f"{found_on.url}, the page recorded as linking to {webpage.url}, is not on a "
                "trusted domain"
            )
        ]
    found_on, row, snapshot = link
    target = row.link_url or webpage.url
    if not await evidence.check_link(ctx.store, snapshot, found_on.url, target, quote=row.quote):
        return [
            (
                f"the trusted page {found_on.url} does not link to {target} in the stored copy "
                "the finding cites"
            )
        ]
    if target != webpage.url and not await graph.redirects_to(session, target, webpage.url):
        return [
            (
                f"the trusted page {found_on.url} links to {target}, which is not on record as "
                f"redirecting to {webpage.url}"
            )
        ]
    return []


# --- reject_domain ---


async def reject_candidate(
    ctx: SessionContext, session: AsyncSession, reason: str, *, another_body: bool = False
) -> Decided:
    """The agent says the candidate domain is not the institution's. The domain is rejected
    and every institution that claimed a homepage on it looks again (spec section 7.3); this
    session keeps looking itself. With `another_body` the site is official but someone else's:
    only this institution's claim is withdrawn, and the domain stays a candidate for its real
    owner."""
    _, subject = await _subject(ctx, session)
    reason = " ".join(reason.split()) or "rejected by the agent"
    if another_body:
        spawns = await status_changes.reject_homepage(
            session,
            subject.homepage,
            entered_by=EnteredBy.AGENT,
            reason=f"another body's site: {reason}",
        )
        await spawn(ctx, session, spawns)
        ctx.drop_candidate()
        return Decided(
            f"{subject.webpage.url} is not {subject.institution.name!r}'s site but another "
            f"body's: {reason}. The claim is withdrawn and {subject.domain.name} stays a "
            "candidate. Keep looking for the institution's own homepage."
        )
    spawns = await status_changes.reject_domain(
        session, subject.domain, entered_by=EnteredBy.AGENT, reason=reason
    )
    created = await spawn(ctx, session, spawns)
    ctx.drop_candidate()
    return Decided(
        f"Rejected {subject.domain.name}: {reason}. Queued: {describe_assignments(created)}. Keep "
        "looking for the institution's current homepage; the next candidate you save can be "
        "opened and decided the same way, or finish when there is nothing more to try."
    )


# --- domain_moved ---


async def candidate_moved(ctx: SessionContext, session: AsyncSession, url: str) -> Decided:  # noqa: C901, PLR0915
    """The agent says the candidate homepage redirects to `url` on another domain. The browser
    must have the redirect on record; the agent's word is not enough. The landing page becomes
    the institution's candidate homepage, vouched for by the same trusted link, and the domain
    that only redirected is rejected (spec section 6.3)."""
    _, subject = await _subject(ctx, session)
    domain, homepage, institution, webpage = (
        subject.domain,
        subject.homepage,
        subject.institution,
        subject.webpage,
    )
    target = absolute_url(url)
    if not await graph.redirects_to(session, webpage.url, target):
        chain = await graph.redirect_chain(session, webpage.url)
        seen = f" On record: {' -> '.join(chain)}." if chain else " No redirect is on record."
        raise FindingError(
            f"Neither {webpage.url} nor its home page (with or without www) is on record as "
            f"redirecting to {target}. Open the candidate homepage, then the home page with "
            f"and without www, with navigate; a redirect it makes is recorded then.{seen}"
        )
    if _covers(graph.host_of(target), domain.name):
        raise FindingError(
            f"{target} is on {domain.name} itself. Open it and confirm or reject the domain."
        )
    moved = await graph.ensure_webpage(session, target, assignment_id=ctx.assignment_id)
    other = await graph.verified_homepage_owner(session, moved, excluding=institution)
    if other is not None:
        reason = (
            f"{webpage.url}, the candidate homepage of {institution.name!r}, redirects to "
            f"{target}, the verified homepage of {other.name!r} ({other.id})."
        )
        await review.raise_review(
            session,
            homepage,
            rule=review.Rule.DOMAIN_MOVED,
            reason=reason,
            assignment_id=ctx.assignment_id,
        )
        ctx.drop_candidate()
        ctx.end(AssignmentResult.NEEDS_REVIEW, reason)
        return Decided(f"The claim goes to a human: {reason}", AssignmentResult.NEEDS_REVIEW)

    found_on = (
        await session.get(Webpage, homepage.found_on_webpage_id)
        if homepage.found_on_webpage_id is not None
        else None
    )
    new_claim = await graph.create_homepage(
        session, institution, moved, entered_by=EnteredBy.AGENT, found_on=found_on
    )
    link = await _trusted_link(session, homepage)
    if link is not None:
        # The trusted page's link to the old URL is what vouches for the new one; the redirect
        # between them is the browser's own record.
        _, row, snapshot = link
        await evidence.add_evidence(
            session,
            entity_id=new_claim.id,
            snapshot=snapshot,
            kind=EvidenceKind.LINKS_TO,
            quote=row.quote,
            entered_by=EnteredBy.AGENT,
            locator=row.locator,
            link_url=row.link_url or webpage.url,
            assignment_id=ctx.assignment_id,
        )
    new_domain = await graph.domain_of_host(session, graph.host_of(target))
    if new_domain is None:
        new_domain, _ = await graph.ensure_domain(
            session, graph.host_of(target), entered_by=EnteredBy.AGENT
        )
    moved.domain_id = new_domain.id
    await session.flush()
    # The old domain served a redirect and nothing else: its claims are rejected, and any other
    # institution that claimed a homepage on it looks again.
    spawns = await status_changes.reject_domain(
        session, domain, entered_by=EnteredBy.AGENT, reason=f"redirects to {target}"
    )
    ctx.drop_candidate()
    result: AssignmentResult | None = None
    if new_domain.domain_kind is DomainKind.PLATFORM:
        reason = (
            f"{webpage.url} redirects to {target} on the platform {new_domain.name}; a platform "
            "page needs a human to say it is the institution's homepage."
        )
        await review.raise_review(
            session,
            new_claim,
            rule=review.Rule.DOMAIN_MOVED,
            reason=reason,
            assignment_id=ctx.assignment_id,
        )
        outcome = f"{new_domain.name} is a platform, so the claim goes to a human"
        result = AssignmentResult.NEEDS_REVIEW
    elif graph.is_trusted(new_domain):
        spawns.extend(
            await status_changes.verify_homepage(session, new_claim, entered_by=EnteredBy.AGENT)
        )
        outcome = f"{new_domain.name} is trusted, so {target} is verified as its homepage"
        result = AssignmentResult.COMPLETE
    elif new_domain.status is EntityStatus.REJECTED:
        spawns.extend(
            await status_changes.reject_homepage(
                session,
                new_claim,
                entered_by=EnteredBy.AGENT,
                reason=f"{new_domain.name} was rejected earlier",
            )
        )
        outcome = (
            f"{new_domain.name} was rejected earlier, so keep looking for the current homepage"
        )
    elif new_domain.status is EntityStatus.NEEDS_REVIEW:
        outcome = f"a human is deciding on {new_domain.name}; nothing else happens until they do"
        result = AssignmentResult.COMPLETE
    else:
        ctx.take_candidate(new_domain, new_claim)
        outcome = (
            f"{new_domain.name} is now this session's candidate: open {target} and decide it with "
            "confirm_domain, domain_moved or reject_domain"
        )
    created = await spawn(ctx, session, spawns)
    summary = (
        f"{webpage.url} redirects to {target}: {domain.name} is rejected (it only redirects) and "
        f"{outcome}. Queued: {describe_assignments(created)}."
    )
    if result is not None:
        ctx.end(result, summary)
    return Decided(summary, result)


__all__ = [
    "MAX_CONFIRM_ATTEMPTS",
    "Decided",
    "DomainQuote",
    "Quote",
    "candidate_moved",
    "confirm_candidate",
    "confirm_domain",
    "domain_moved",
    "reject_candidate",
    "reject_domain",
]
