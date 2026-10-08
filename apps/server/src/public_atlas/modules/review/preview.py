"""What a decision would do, shown before it is made (spec section 6.5): the decision runs as
it would, through the same functions, while its status changes are collected; the work it asks
for is checked against the run it would start in; then the session is rolled back, so nothing
is kept. A preview cannot drift from the decision, since it is the decision."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.assignments import service as assignments
from public_atlas.modules.assignments.models import AssignmentType
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import EntityStatus
from public_atlas.modules.review import service
from public_atlas.modules.review.reading import EntityRef, entity_ref

__all__ = ["Change", "Planned", "Preview", "RunRef", "preview"]


@dataclass(frozen=True, slots=True)
class Change:
    entity: EntityRef
    before: EntityStatus
    after: EntityStatus


@dataclass(frozen=True, slots=True)
class Planned:
    """Work the decision asks for, with why it would not start; None when it would."""

    type: AssignmentType
    subject: EntityRef
    skipped: assignments.SkipReason | None


@dataclass(frozen=True, slots=True)
class RunRef:
    id: uuid.UUID
    name: str


@dataclass(frozen=True, slots=True)
class Preview:
    # Each entity whose status would change, once, in the order the decision changes them.
    changes: list[Change]
    spawn: list[Planned]
    # The run the work would start in; None when no run would take it.
    run: RunRef | None


async def preview(
    session: AsyncSession,
    decide: Callable[[], Awaitable[service.Decision | service.KindDecision]],
) -> Preview:
    """Make the decision `decide` makes, say what it did, and roll it back. Raises what the
    decision would raise, so a preview also says when a decision would be refused."""
    try:
        with status_changes.previewing() as recorded:
            decision = await decide()
        items = decision.items if isinstance(decision, service.KindDecision) else [decision.item]
        first = items[0]
        run = await assignments.run_for_decision(
            session,
            assignment_id=first.raised_by_assignment_id,
            country_code=await service.country_of(session, first),
        )
        planned = await assignments.would_spawn(session, run, decision.spawn)
        return Preview(
            changes=await _changes(session, recorded),
            spawn=[
                Planned(type=spawn.type, subject=subject, skipped=skipped)
                for spawn, skipped in planned
                if (subject := await entity_ref(session, spawn.subject_id)) is not None
            ],
            run=RunRef(id=run.id, name=run.name) if run is not None else None,
        )
    finally:
        await session.rollback()


async def _changes(
    session: AsyncSession, recorded: list[status_changes.StatusChange]
) -> list[Change]:
    """One change per entity, from its first status to its last; none when it ends as it began."""
    first: dict[uuid.UUID, status_changes.StatusChange] = {}
    last: dict[uuid.UUID, EntityStatus] = {}
    for change in recorded:
        first.setdefault(change.entity.id, change)
        last[change.entity.id] = change.after
    return [
        Change(
            entity=EntityRef(
                change.entity.id, change.entity.kind, await graph.label_of(session, change.entity)
            ),
            before=change.before,
            after=last[entity_id],
        )
        for entity_id, change in first.items()
        if last[entity_id] is not change.before
    ]
