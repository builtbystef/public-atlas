"""The findings: the typed functions the agent calls through the adapter in `tools.py`. Each
takes the session's context and returns a typed result, or raises `FindingError` with what the
model should do instead. The saving tools (`save_institution`, `save_homepage`, `save_source`,
the domain decisions, `read_file`, `search`, `request_review`) come with the second half of
phase 4; here are the two every type has: `status` and `finish`."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic_ai import ModelRetry, RunContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.agent.context import SessionContext
from public_atlas.modules.assignments.descriptors import Checklist
from public_atlas.modules.assignments.models import Assignment, AssignmentResult
from public_atlas.modules.evidence.models import Evidence, Snapshot
from public_atlas.modules.graph import service as graph
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

# Every tool spells out `RunContext[SessionContext]`: Pydantic AI recognises the run context only
# when the annotation is `RunContext[...]` itself, not an alias of it.

# Pages `status` lists, newest first.
MAX_VISITED = 30


class FindingError(Exception):
    """Refused, with what the model should do instead. The adapter turns it into a retry prompt."""


async def in_session[T](
    ctx: RunContext[SessionContext], work: Callable[[AsyncSession], Awaitable[T]]
) -> T:
    """Run `work` in a database session of its own and commit, so what a tool saved survives
    whatever the agent does next. A refusal rolls back and is returned to the model."""
    async with ctx.deps.session() as session:
        try:
            result = await work(session)
        except FindingError as exc:
            await session.rollback()
            raise ModelRetry(str(exc)) from None
        await session.commit()
    return result


# --- status ---


@dataclass(frozen=True, slots=True)
class Status:
    """What the assignment has saved and opened, and what is left to spend."""

    saved: list[str]
    checklist_remaining: list[str]
    visited: list[str]
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
        lines.append(f"Budget left: {self.requests_left} requests, {self.tokens_left} tokens.")
        if self.handoff_note:
            lines.append(f"Handoff note from the previous session: {self.handoff_note}")
        return "\n".join(lines)


async def status(ctx: RunContext[SessionContext]) -> Status:
    """What this assignment has saved so far, the pages it opened, the types still to account
    for, and the budget left. Use it instead of remembering, and after a restart."""
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
            .where(Snapshot.assignment_id == assignment.id)
            .distinct()
            .order_by(Webpage.url)
            .limit(MAX_VISITED)
        )
    )
    return Status(
        saved=saved,
        checklist_remaining=await remaining_checklist(ctx, session),
        visited=visited,
        requests_left=max(assignment.budget_requests - assignment.requests_used - requests_now, 0),
        tokens_left=max(assignment.budget_tokens - assignment.tokens_used - tokens_now, 0),
        handoff_note=assignment.handoff_note,
    )


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
    """One line to recognise an entity by, with its status."""
    match entity:
        case Institution():
            return f"institution {entity.name!r} ({entity.institution_type}, {entity.status.value})"
        case Place():
            return f"place {entity.name!r} ({entity.administrative_level}, {entity.status.value})"
        case Domain():
            return f"domain {entity.name} ({entity.status.value})"
        case Homepage():
            webpage = await session.get_one(Webpage, entity.webpage_id)
            return f"homepage {webpage.url} ({entity.status.value})"
        case Source():
            webpage = await session.get_one(Webpage, entity.webpage_id)
            return f"{entity.source_type} source {webpage.url} ({entity.status.value})"
        case _:  # pragma: no cover - every kind is listed above
            return f"{entity.kind.value} {entity.id}"


async def remaining_checklist(ctx: SessionContext, session: AsyncSession) -> list[str]:
    """The types the assignment still has to account for: the ones expected for the subject
    with nothing saved under it yet, rejected rows aside. Empty for a type with no checklist."""
    match ctx.descriptor.checklist:
        case Checklist.INSTITUTION_TYPES:
            expected = ctx.rules.expected_institution_types(ctx.place.administrative_level)
            saved = set(
                await session.scalars(
                    select(Institution.institution_type).where(
                        Institution.place_id == ctx.place.id,
                        Institution.status != EntityStatus.REJECTED,
                    )
                )
            )
        case Checklist.SOURCE_TYPES:
            if not isinstance(ctx.subject, Institution):  # pragma: no cover - by descriptor
                return []
            expected = ctx.rules.expected_source_types(ctx.subject.institution_type)
            saved = set(
                await session.scalars(
                    select(Source.source_type).where(
                        Source.institution_id == ctx.subject.id,
                        Source.status != EntityStatus.REJECTED,
                    )
                )
            )
        case _:
            return []
    return [name for name in expected if name not in saved]


# --- finish ---


@dataclass(frozen=True, slots=True)
class Finished:
    summary: str

    def __str__(self) -> str:
        return "Assignment finished."


async def finish(
    ctx: RunContext[SessionContext], summary: str, types_not_found: list[str] | None = None
) -> Finished:
    """End this assignment. Call it only when you have looked for everything the goal lists.

    Args:
        summary: What was found, and for each type you did not find, where you looked.
        types_not_found: find_institutions and find_sources only: each institution type (or
            source type) you looked for and did not find, as the goal names them.
    """
    return await in_session(
        ctx, lambda session: finish_assignment(ctx.deps, session, summary, types_not_found)
    )


async def finish_assignment(
    ctx: SessionContext, session: AsyncSession, summary: str, types_not_found: list[str] | None
) -> Finished:
    """Record the summary and the types not found, and end the session `complete`. The
    checklist, the refused short finish and `complete_with_gaps` come with the second half of
    phase 4."""
    if "finish" not in ctx.descriptor.finishing_tools:
        raise FindingError(
            f"a {ctx.descriptor.type.value} assignment ends with "
            f"{', '.join(ctx.descriptor.finishing_tools)}."
        )
    summary = " ".join(summary.split())
    if not summary:
        raise FindingError("summary must say what was found.")
    known = set(ctx.rules.institution_types) | set(ctx.rules.source_types)
    listed: list[str] = []
    for raw in types_not_found or ():
        name = raw.strip()
        if name and name not in listed:
            if name not in known:
                raise FindingError(f"{name!r} is not a type the goal names.")
            listed.append(name)
    assignment = await session.get_one(Assignment, ctx.assignment_id)
    assignment.summary = summary
    assignment.types_not_found = listed
    await session.flush()
    ctx.end(AssignmentResult.COMPLETE, summary)
    return Finished(summary)
