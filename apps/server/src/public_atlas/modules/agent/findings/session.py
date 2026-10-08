"""The tools a session uses on its own assignment rather than to save findings: `status` reports
progress, `request_review` hands an entity to a human, and `finish` ends it (spec section 7.2)."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic_ai import RunContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.agent.context import SessionContext
from public_atlas.modules.agent.findings.shared import FindingError, in_session, parse_uuid
from public_atlas.modules.assignments.descriptors import Checklist
from public_atlas.modules.assignments.models import Assignment, AssignmentResult
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.evidence.models import Evidence, Snapshot, TextStatus
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import (
    Domain,
    Entity,
    EntityStatus,
    Homepage,
    Institution,
    Place,
    Source,
    Webpage,
)
from public_atlas.modules.review import service as review

# Pages `status` lists, newest first.
MAX_VISITED = 30


# --- status ---


@dataclass(frozen=True, slots=True)
class Status:
    """What the assignment has saved and opened, and what is left to spend."""

    saved: list[str]
    checklist_remaining: list[str]
    visited: list[str]
    # Files read with `read_file` and how their parsing stands.
    files: list[str]
    candidate: str | None
    requests_left: int
    tokens_left: int
    handoff_note: str | None

    def __str__(self) -> str:
        lines = ["Saved in this assignment:"]
        lines.extend(f"- {item}" for item in self.saved) if self.saved else lines.append(
            "- nothing yet"
        )
        if self.checklist_remaining:
            lines.append("Types still to account for: " + ", ".join(self.checklist_remaining) + ".")
        lines.append("Pages opened in this assignment:")
        lines.extend(f"- {url}" for url in self.visited) if self.visited else lines.append("- none")
        if self.files:
            lines.append("Files read:")
            lines.extend(f"- {item}" for item in self.files)
        if self.candidate:
            lines.append(self.candidate)
        lines.append(f"Budget left: {self.requests_left} requests, {self.tokens_left} tokens.")
        if self.handoff_note:
            lines.append(f"Handoff note from the previous session: {self.handoff_note}")
        return "\n".join(lines)


async def status(ctx: RunContext[SessionContext]) -> Status:
    """What this assignment has saved so far, the pages it opened, the files it read and
    whether they are parsed, the types still to account for, and the budget left. Use it
    instead of remembering, and after a restart."""
    spent = (ctx.usage.requests, ctx.usage.total_tokens)
    return await in_session(ctx, lambda session: status_of(ctx.deps, session, spent_now=spent))


async def status_of(
    ctx: SessionContext, session: AsyncSession, *, spent_now: tuple[int, int] = (0, 0)
) -> Status:
    """`spent_now` is what this session has used so far: the row is written up only when the
    session ends."""
    assignment = await session.get_one(Assignment, ctx.assignment_id)
    requests_now, tokens_now = spent_now
    saved = [
        await describe(session, entity) for entity in await saved_entities(session, assignment.id)
    ]
    visited = list(
        await session.scalars(
            select(Webpage.url)
            .join(Snapshot, Snapshot.webpage_id == Webpage.id)
            .where(Snapshot.assignment_id == assignment.id, Snapshot.media_type == evidence.HTML)
            .distinct()
            .order_by(Webpage.url)
            .limit(MAX_VISITED)
        )
    )
    files = await _files(session, assignment.id)
    candidate = None
    if ctx.candidate is not None:
        homepage = await session.get_one(Homepage, ctx.candidate.homepage_id)
        webpage = await session.get_one(Webpage, homepage.webpage_id)
        candidate = (
            f"Candidate to decide: {webpage.url} on the candidate domain "
            f"{ctx.candidate.domain_name} (confirm_domain, reject_domain or domain_moved)."
        )
    return Status(
        saved=saved,
        checklist_remaining=await remaining_checklist(ctx, session),
        visited=visited,
        files=files,
        candidate=candidate,
        requests_left=max(assignment.budget_requests - assignment.requests_used - requests_now, 0),
        tokens_left=max(assignment.budget_tokens - assignment.tokens_used - tokens_now, 0),
        handoff_note=assignment.handoff_note,
    )


async def _files(session: AsyncSession, assignment_id: uuid.UUID) -> list[str]:
    rows = await session.execute(
        select(Webpage.url, Snapshot.text_status, Snapshot.text_error)
        .join(Snapshot, Snapshot.webpage_id == Webpage.id)
        .where(Snapshot.assignment_id == assignment_id, Snapshot.media_type != evidence.HTML)
        .order_by(Snapshot.fetched_at)
    )
    found: dict[str, str] = {}
    for url, text_status, error in rows.all():
        state = text_status.value
        if text_status is TextStatus.FAILED and error:
            state = f"failed: {error}"
        found[url] = state
    return [f"{url}: {state}" for url, state in found.items()]


async def saved_entities(session: AsyncSession, assignment_id: uuid.UUID) -> list[Entity]:
    """Every entity the assignment quoted evidence for, oldest first."""
    ids = await session.scalars(
        select(Evidence.entity_id)
        .where(Evidence.assignment_id == assignment_id)
        .group_by(Evidence.entity_id)
        .order_by(Evidence.entity_id)
    )
    found = []
    for entity_id in ids:
        entity = await graph.entity_by_id(session, entity_id)
        if entity is not None:
            found.append(entity)
    return found


async def describe(session: AsyncSession, entity: Entity) -> str:
    """One line to recognise an entity by, with its status and the id the tools take."""
    match entity:
        case Institution():
            return (
                f"institution {entity.name!r} ({entity.institution_type}, {entity.status.value}) "
                f"id={entity.id}"
            )
        case Place():
            return (
                f"place {entity.name!r} ({entity.administrative_level}, {entity.status.value}) "
                f"id={entity.id}"
            )
        case Domain():
            return f"domain {entity.name} ({entity.status.value}) id={entity.id}"
        case Homepage():
            webpage = await session.get_one(Webpage, entity.webpage_id)
            return f"homepage {webpage.url} ({entity.status.value}) id={entity.id}"
        case Source():
            webpage = await session.get_one(Webpage, entity.webpage_id)
            return (
                f"{entity.source_type} source {webpage.url} ({entity.status.value}) id={entity.id}"
            )
        case _:  # pragma: no cover - every kind is listed above
            return f"{entity.kind.value} {entity.id}"


# --- The checklist ---


async def expected_types(ctx: SessionContext, session: AsyncSession) -> list[str]:
    """The types a discovery assignment must account for, sorted; empty for a type with no
    checklist."""
    match ctx.descriptor.checklist:
        case Checklist.INSTITUTION_TYPES:
            return sorted(ctx.rules.expected_institution_types(ctx.place.administrative_level))
        case Checklist.SOURCE_TYPES:
            if not isinstance(ctx.subject, Institution):  # pragma: no cover - by descriptor
                return []
            institution = await session.get_one(Institution, ctx.subject.id)
            return sorted(ctx.rules.expected_source_types(institution.institution_type))
        case _:
            return []


async def saved_types(ctx: SessionContext, session: AsyncSession) -> set[str]:
    """The types with something saved under the subject, rejected rows aside, by any
    assignment. For institution types, a body under a place above the subject counts too: a
    body serving a whole region is saved under the region, as the goal text asks, and it
    serves the town as much as one of the town's own would."""
    match ctx.descriptor.checklist:
        case Checklist.INSTITUTION_TYPES:
            place = await session.get_one(Place, ctx.place.id)
            chain = await graph.place_chain(session, place)
            rows = await session.scalars(
                select(Institution.institution_type).where(
                    Institution.place_id.in_([found.id for found in chain]),
                    Institution.status != EntityStatus.REJECTED,
                )
            )
        case Checklist.SOURCE_TYPES:
            rows = await session.scalars(
                select(Source.source_type).where(
                    Source.institution_id == ctx.subject.id,
                    Source.status != EntityStatus.REJECTED,
                )
            )
        case _:
            return set()
    return set(rows)


async def remaining_checklist(ctx: SessionContext, session: AsyncSession) -> list[str]:
    """The types the assignment still has to account for: the ones expected for the subject
    with nothing saved under it, or under a place above it, yet."""
    saved = await saved_types(ctx, session)
    return [name for name in await expected_types(ctx, session) if name not in saved]


def _known_types(ctx: SessionContext) -> tuple[str, list[str]]:
    """What `types_not_found` may name, and what to call it."""
    if ctx.descriptor.checklist is Checklist.SOURCE_TYPES:
        return "source type", sorted(ctx.rules.source_types)
    return "institution type", sorted(ctx.rules.institution_types)


def listed_types(ctx: SessionContext, types_not_found: Iterable[str] | None) -> list[str]:
    """`types_not_found` cleaned: trimmed, in order, once each, every one a known type."""
    kind, known = _known_types(ctx)
    listed: list[str] = []
    for raw in types_not_found or ():
        name = raw.strip()
        if name and name not in listed:
            listed.append(name)
    unknown = [name for name in listed if name not in known]
    if unknown:
        raise FindingError(
            f"types_not_found names no {kind} the country lists: {', '.join(unknown)}. The "
            f"{kind}s are: {', '.join(known)}."
        )
    return listed


# --- finish ---


@dataclass(frozen=True, slots=True)
class Finished:
    result: AssignmentResult
    summary: str

    def __str__(self) -> str:
        return f"Assignment finished ({self.result.value})."


async def finish(
    ctx: RunContext[SessionContext], summary: str, types_not_found: list[str] | None = None
) -> Finished:
    """End this assignment. Call it only when you have looked for everything the goal lists.

    Args:
        summary: What was found, and for each type you did not find, where you looked.
        types_not_found: find_institutions and find_sources only: each institution type (or
            source type) you looked for and did not find, as the goal names them. Every type
            expected for the subject must be saved under it (or, for a body serving a whole
            place above, under that place) or named here; a finish that leaves one out is
            refused once.
    """
    return await in_session(
        ctx, lambda session: finish_assignment(ctx.deps, session, summary, types_not_found)
    )


async def finish_assignment(
    ctx: SessionContext, session: AsyncSession, summary: str, types_not_found: list[str] | None
) -> Finished:
    """Record the summary and end the session. A discovery finish is checked against the
    checklist: one that leaves an expected type neither saved under the subject (or a place
    above it) nor named in `types_not_found` is refused once with the gap; finished short
    again, the assignment ends `complete_with_gaps` with a review item. A `find_homepage`
    finish ends `complete` when the homepage is verified or with a reviewer, and
    `no_homepage` with a review item when the searches found nothing."""
    if "finish" not in ctx.descriptor.finishing_tools:
        raise FindingError(
            f"a {ctx.descriptor.type.value} assignment ends with "
            f"{', '.join(ctx.descriptor.finishing_tools)}."
        )
    summary = " ".join(summary.split())
    if not summary:
        raise FindingError("summary must say what was found.")
    assignment = await session.get_one(Assignment, ctx.assignment_id)
    if ctx.descriptor.checklist is Checklist.NONE:
        result = await _homepage_result(ctx, session, summary)
    else:
        listed = listed_types(ctx, types_not_found)
        result, summary = await _discovery_result(ctx, session, summary, listed)
        assignment.types_not_found = listed
    assignment.summary = summary
    await session.flush()
    ctx.end(result, summary)
    return Finished(result, summary)


async def _homepage_result(
    ctx: SessionContext, session: AsyncSession, summary: str
) -> AssignmentResult:
    if ctx.candidate is not None:
        raise FindingError(
            "Not finished: decide the candidate you saved first, with confirm_domain, "
            "reject_domain or domain_moved."
        )
    institution = await session.get_one(Institution, ctx.subject.id)
    if institution.homepage_id is not None:
        return AssignmentResult.COMPLETE
    with_reviewer = await session.scalar(
        select(Homepage.id)
        .where(
            Homepage.institution_id == institution.id,
            Homepage.status == EntityStatus.NEEDS_REVIEW,
        )
        .limit(1)
    )
    if with_reviewer is not None:
        return AssignmentResult.COMPLETE
    await review.raise_review(
        session,
        institution,
        rule=review.Rule.NO_HOMEPAGE,
        reason=f"The searches found no homepage: {summary}",
        assignment_id=ctx.assignment_id,
    )
    return AssignmentResult.NO_HOMEPAGE


async def _discovery_result(
    ctx: SessionContext, session: AsyncSession, summary: str, listed: list[str]
) -> tuple[AssignmentResult, str]:
    kind, _ = _known_types(ctx)
    saved = await saved_types(ctx, session)
    missing = [
        name
        for name in await expected_types(ctx, session)
        if name not in saved and name not in listed
    ]
    if not missing:
        return AssignmentResult.COMPLETE, summary
    ctx.short_closes += 1
    if ctx.short_closes == 1:
        raise FindingError(
            f"Not finished: these {kind}s are neither saved under the subject (or a place "
            f"above it) nor named in types_not_found: {', '.join(missing)}. Look for each "
            "(status() shows what is saved), save what you find, then finish again with "
            "types_not_found naming the ones you looked for and did not find."
        )
    summary = f"Not accounted for: {', '.join(missing)}. {summary}"
    subject = await graph.entity_by_id(session, ctx.subject.id)
    if subject is not None:
        await review.raise_review(
            session,
            subject,
            rule=review.Rule.GAPS,
            reason=summary,
            question={"types_missing": missing, "checklist": kind},
            assignment_id=ctx.assignment_id,
        )
    return AssignmentResult.COMPLETE_WITH_GAPS, summary


# --- request_review ---


@dataclass(frozen=True, slots=True)
class Reviewed:
    entity_id: uuid.UUID
    ended: bool

    def __str__(self) -> str:
        if self.ended:
            return "Sent to a human; this assignment is finished until they decide."
        return f"Sent {self.entity_id} to review."


async def request_review(ctx: RunContext[SessionContext], entity_id: str, reason: str) -> Reviewed:
    """Send something you are not sure about to a human: a doubtful match, a domain
    that looks like a shared platform or refuses you, a page that contradicts another.
    In find_homepage, sending the candidate domain ends the assignment.

    Args:
        entity_id: The id of the thing to review, as status() or a save reported it.
        reason: What the human should decide, and what you saw.
    """
    return await in_session(ctx, lambda session: raise_item(ctx.deps, session, entity_id, reason))


async def raise_item(
    ctx: SessionContext, session: AsyncSession, entity_id: str, reason: str
) -> Reviewed:
    entity = await graph.entity_by_id(session, parse_uuid(entity_id, "entity_id"))
    if entity is None:
        raise FindingError(f"Nothing with id {entity_id}. Check status() for the ids.")
    reason = " ".join(reason.split())
    if not reason:
        raise FindingError("reason must say what the human should decide.")
    await review.raise_review(
        session, entity, rule=review.Rule.AGENT, reason=reason, assignment_id=ctx.assignment_id
    )
    candidate = ctx.candidate
    if candidate is None or entity.id not in (candidate.domain_id, candidate.homepage_id):
        return Reviewed(entity.id, ended=False)
    homepage = await session.get_one(Homepage, candidate.homepage_id)
    await status_changes.send_to_review(session, homepage)
    ctx.drop_candidate()
    ctx.end(AssignmentResult.NEEDS_REVIEW, reason)
    return Reviewed(entity.id, ended=True)
