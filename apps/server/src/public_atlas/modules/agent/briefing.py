"""What a session is told (spec section 8): the briefing with the subject and its ids, the
places a body may be saved under, the checklist of types still to account for, where to look,
the homepages claimed before, the pages already visited and the last handoff note. Never the old
transcript. The standing instructions are in `prompts.py`."""

import uuid
from collections import Counter
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.agent import findings
from public_atlas.modules.agent.context import SessionContext
from public_atlas.modules.agent.prompts import instructions
from public_atlas.modules.assignments.descriptors import Checklist
from public_atlas.modules.assignments.models import Assignment
from public_atlas.modules.evidence.models import Evidence, Snapshot
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph.models import (
    Domain,
    EnteredBy,
    EntityStatus,
    Homepage,
    Institution,
    Place,
    Webpage,
)

__all__ = [
    "briefing",
    "earlier_claims",
    "instructions",
    "places_to_save_under",
    "recorded_under",
    "where_to_look",
]

# Records a domain with a reason to look there; a domain that is not allowed is dropped.
type Note = Callable[[str | None, str], None]


async def briefing(ctx: SessionContext, session: AsyncSession) -> str:
    """The user prompt of a session: the subject, the checklist still open, where to look, the
    pages this assignment opened already, and the previous session's handoff note."""
    assignment = await session.get_one(Assignment, ctx.assignment_id)
    parts = [f"Assignment: {ctx.descriptor.type.value}, session {assignment.sessions}."]
    parts.extend(await _subject_lines(ctx, session))
    remaining = await findings.remaining_checklist(ctx, session)
    if remaining:
        parts.append(
            "Types still to account for: " + ", ".join(remaining) + ". Each is saved (under "
            "the subject, or under the place above it that the body serves) or named in "
            "types_not_found when you finish."
        )
    if ctx.descriptor.checklist is Checklist.INSTITUTION_TYPES:
        recorded = await recorded_under(session, ctx.place)
        if recorded is not None:
            parts.append(recorded)
    parts.extend(await where_to_look(ctx, session))
    visited = list(
        await session.scalars(
            select(Webpage.url)
            .join(Snapshot, Snapshot.webpage_id == Webpage.id)
            .where(Snapshot.assignment_id == assignment.id)
            .distinct()
            .order_by(Webpage.url)
            .limit(findings.MAX_VISITED)
        )
    )
    if visited:
        parts.append("Pages this assignment opened already:")
        parts.extend(f"- {url}" for url in visited)
    if assignment.handoff_note:
        parts.append(f"Handoff note from the previous session: {assignment.handoff_note}")
    parts.append(
        f"Budget left: {max(assignment.budget_requests - assignment.requests_used, 0)} requests."
    )
    parts.append("Begin. Start with the subject's pages listed above.")
    return "\n".join(parts)


# --- The subject ---


async def _subject_lines(ctx: SessionContext, session: AsyncSession) -> list[str]:
    place = await session.get_one(Place, ctx.place.id)
    if isinstance(ctx.subject, Place):
        names = await findings_names(session, place)
        lines = [f"Subject: the place {names} ({place.administrative_level}, id {place.id})."]
        if place.government_institution_id is not None:
            government = await session.get_one(Institution, place.government_institution_id)
            lines.append(await _institution_line(session, government, "Its government"))
            lines.extend(await _homepage_lines(session, government))
        if ctx.descriptor.checklist is Checklist.INSTITUTION_TYPES:
            lines.append(await places_to_save_under(session, place))
        return lines
    institution = await session.get_one(Institution, ctx.subject.id)
    lines = [await _institution_line(session, institution, "Subject"), _belongs_to(place)]
    lines.extend(await _homepage_lines(session, institution))
    if ctx.finding_homepage:
        lines.extend(await earlier_claims(session, institution))
        lines.extend(await _candidate_lines(ctx, session))
    if ctx.descriptor.checklist is Checklist.SOURCE_TYPES:
        lines.append(_source_types_line(ctx, institution))
        lines.append(await places_to_save_under(session, place))
    return lines


async def findings_names(session: AsyncSession, owner: Place | Institution) -> str:
    """Every name the body goes by, as one string."""
    names = [alias.text for alias in await graph.names_of(session, owner)]
    return " / ".join(names) if names else owner.name


async def _institution_line(session: AsyncSession, institution: Institution, label: str) -> str:
    names = await findings_names(session, institution)
    return (
        f"{label}: the institution {names} ({institution.institution_type}, id {institution.id})."
    )


def _belongs_to(place: Place) -> str:
    """The institution's place: many places share a name, so a search, on the web or in a
    site's own search box, has to name it."""
    return (
        f"It belongs to: {place.name} ({place.administrative_level}, id {place.id}). Name the "
        "place in your searches."
    )


async def _homepage_lines(session: AsyncSession, institution: Institution) -> list[str]:
    """The institution's verified homepage, or its open claims."""
    lines = []
    for homepage in await graph.homepages_of(session, institution):
        url = (await session.get_one(Webpage, homepage.webpage_id)).url
        if homepage.id == institution.homepage_id:
            lines.append(f"Homepage (verified): {url}")
        elif homepage.status in (EntityStatus.CANDIDATE, EntityStatus.NEEDS_REVIEW):
            lines.append(f"Candidate homepage ({homepage.status.value}): {url}")
    if not lines:
        lines.append("Homepage: none known yet.")
    return lines


async def earlier_claims(session: AsyncSession, institution: Institution) -> list[str]:
    """The homepages claimed for the institution before and what became of each, so a new
    search does not bring back a dead or wrong one."""
    rows = await session.execute(
        select(Homepage, Webpage)
        .join(Webpage, Webpage.id == Homepage.webpage_id)
        .where(
            Homepage.institution_id == institution.id,
            Homepage.status == EntityStatus.REJECTED,
        )
        .order_by(Homepage.id)
    )
    lines = [
        f"- {webpage.url}: rejected ({homepage.rejected_reason or 'no reason recorded'})"
        for homepage, webpage in rows.all()
    ]
    if not lines:
        return []
    return ["Homepages claimed for it before; do not save these again:", *lines]


async def _candidate_lines(ctx: SessionContext, session: AsyncSession) -> list[str]:
    """The claim the session is deciding on, and whether a trusted page vouches for it."""
    if ctx.candidate is None:
        return []
    homepage = await session.get_one(Homepage, ctx.candidate.homepage_id)
    webpage = await session.get_one(Webpage, homepage.webpage_id)
    lines = [
        (
            f"Candidate to decide: {webpage.url} on the candidate domain "
            f"{ctx.candidate.domain_name}, which is open to you. Open it, judge it, and end "
            "with confirm_domain, reject_domain or domain_moved."
        )
    ]
    if homepage.found_on_webpage_id is not None:
        found_on = await session.get_one(Webpage, homepage.found_on_webpage_id)
        lines.append(f"Found as a link on the trusted page {found_on.url}.")
    else:
        lines.append(
            "No trusted page links to it: it was found by a web search or on an untrusted page. "
            "Judge the site as usual; if you confirm it, a human makes the final call with your "
            "quotes."
        )
    return lines


def _source_types_line(ctx: SessionContext, institution: Institution) -> str:
    sources = ", ".join(ctx.rules.expected_source_types(institution.institution_type))
    if sources:
        return (
            f"Source types to find for a {institution.institution_type}: {sources}. Each is "
            "saved or named in types_not_found when you finish. Save a page of any other "
            "source type too, when you meet one."
        )
    return (
        f"The country lists no source types for a {institution.institution_type}: look for a "
        "page of each source type listed above and save the ones you find."
    )


async def recorded_under(session: AsyncSession, place: Place) -> str | None:
    """The institution types with rows under the place already, as counts, never names: a list
    of names does not scale to a city with hundreds of bodies, a line of types does. A count
    from an official list means the loader read the authority's own list, which beats anything
    a directory page would add, so the agent is told to skip that type's directories. The list
    is not named: the agent cannot open it and could only be led astray by its name."""
    rows = await session.execute(
        select(Institution.institution_type, Institution.entered_by, func.count())
        .where(Institution.place_id == place.id, Institution.status != EntityStatus.REJECTED)
        .group_by(Institution.institution_type, Institution.entered_by)
    )
    totals: Counter[str] = Counter()
    listed: Counter[str] = Counter()
    for institution_type, entered_by, count in rows.all():
        totals[institution_type] += count
        if entered_by is EnteredBy.SCRIPT:
            listed[institution_type] += count
    if not totals:
        return None
    parts = []
    for institution_type in sorted(totals):
        total, from_list = totals[institution_type], listed[institution_type]
        if from_list == total:
            parts.append(f"{institution_type} ({total}, from an official list)")
        elif from_list:
            parts.append(f"{institution_type} ({total}, {from_list} from an official list)")
        else:
            parts.append(f"{institution_type} ({total})")
    return (
        "Already recorded under this place: " + ", ".join(parts) + ". A type with a count from "
        "an official list is done: skip the directory pages that list that type and do not "
        "save its bodies again."
    )


async def places_to_save_under(session: AsyncSession, place: Place) -> str:
    """The places `save_institution` accepts, with their ids: the subject's place and each place
    above it. The agent sees no other place id, so this line is how a regional body found on a
    town's site gets filed under the region."""
    chain = await graph.place_chain(session, place)
    places = "; ".join(
        f"{found.name} ({found.administrative_level}) id={found.id}" for found in chain
    )
    return (
        f"Places to save under (place_id of save_institution): {places}. The first is the "
        "default. A body serving the whole of a place above goes under that place; no other "
        "place is accepted."
    )


# --- Where to look ---


async def where_to_look(ctx: SessionContext, session: AsyncSession) -> list[str]:
    """The allowed domains with a stake in the subject, each with why: the subject's own site,
    the pages that name it, its place's government and the governments above. The allowlist
    itself is every trusted domain and every platform, enforced by the browser; the model is
    told these few instead of the whole list, so a session's briefing stays short."""
    reasons: dict[str, list[str]] = {}

    def note(domain: str | None, reason: str) -> None:
        if domain is not None and domain in ctx.allowed_domains:
            why = reasons.setdefault(domain, [])
            if reason not in why:
                why.append(reason)

    if isinstance(ctx.subject, Institution):
        institution = await session.get_one(Institution, ctx.subject.id)
        note(await _homepage_domain(session, institution), "its homepage")
        await _found_on(session, institution.id, note)
        await _governments_above(session, institution.place_id, institution.id, note)
    else:
        await _found_on(session, ctx.subject.id, note)
        await _governments_above(session, ctx.subject.id, None, note)
    if ctx.candidate is not None:
        note(ctx.candidate.domain_name, "the candidate domain, yours to decide")
    for name in sorted(ctx.search_hosts):
        note(name, "a site a search of yours returned")
    heading = (
        "Where to look (the allowed domains tied to the subject; navigate refuses every other "
        "domain"
        + (
            " until a search of yours returns a page on it, and search limited to domains "
            "takes only allowed ones):"
            if ctx.finding_homepage
            else "):"
        )
    )
    if not reasons:
        return [heading, "- none tied to the subject yet; the platforms are open to you"]
    return [heading, *(f"- {domain}: {'; '.join(why)}" for domain, why in reasons.items())]


async def _homepage_domain(session: AsyncSession, institution: Institution) -> str | None:
    if institution.homepage_id is None:
        return None
    homepage = await session.get_one(Homepage, institution.homepage_id)
    webpage = await session.get_one(Webpage, homepage.webpage_id)
    domain = await graph.domain_of_webpage(session, webpage)
    return domain.name if domain is not None else None


async def _found_on(session: AsyncSession, entity_id: uuid.UUID, note: Note) -> None:
    """One page per domain among those whose text names the entity: the site that lists it is
    where its link is most likely written."""
    rows = await session.execute(
        select(Domain.name, Webpage.url)
        .select_from(Evidence)
        .join(Snapshot, Snapshot.id == Evidence.snapshot_id)
        .join(Webpage, Webpage.id == Snapshot.webpage_id)
        .join(Domain, Domain.id == Webpage.domain_id)
        .where(Evidence.entity_id == entity_id)
        .order_by(Evidence.id)
    )
    seen: set[str] = set()
    for domain, url in rows.all():
        if domain not in seen:
            seen.add(domain)
            note(domain, f"names it: {url}")


async def _governments_above(
    session: AsyncSession,
    place_id: uuid.UUID,
    subject_institution_id: uuid.UUID | None,
    note: Note,
) -> None:
    """The homepage's domain of the government of each place from this one up to the country,
    the subject itself excepted."""
    place = await session.get_one(Place, place_id)
    for found in await graph.place_chain(session, place):
        government_id = found.government_institution_id
        if government_id is None or government_id == subject_institution_id:
            continue
        government = await session.get_one(Institution, government_id)
        note(
            await _homepage_domain(session, government),
            f"government of {found.name} ({found.administrative_level})",
        )
