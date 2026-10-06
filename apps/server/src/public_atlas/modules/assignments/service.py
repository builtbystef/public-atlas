"""The assignments module's door: recording what a call cost, what a status change asks to
spawn, and the open work on a subject. Phase 4 adds runs, assignments, spawning and budgets."""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.assignments import lifecycle
from public_atlas.modules.assignments.models import (
    OPEN_STATUSES,
    Assignment,
    AssignmentType,
    Usage,
    UsageKind,
)
from public_atlas.modules.assignments.pricing import load_prices

__all__ = ["Spawn", "cancel", "move_subject", "open_assignments", "record_usage"]

logger = logging.getLogger(__name__)

_unpriced: set[str] = set()


@dataclass(frozen=True, slots=True)
class Spawn:
    """Work a status change asks for (spec section 7.3): one assignment type on one subject. The
    backend inserts it and queues or holds it by the run's mode; the status change only says."""

    type: AssignmentType
    subject_id: uuid.UUID


async def open_assignments(session: AsyncSession, subject_id: uuid.UUID) -> list[Assignment]:
    """The held, queued and running assignments on a subject."""
    rows = await session.scalars(
        select(Assignment)
        .where(Assignment.subject_id == subject_id, Assignment.status.in_(OPEN_STATUSES))
        .order_by(Assignment.id)
    )
    return list(rows)


def cancel(assignment: Assignment) -> None:
    lifecycle.cancel(assignment)


async def move_subject(session: AsyncSession, from_id: uuid.UUID, into_id: uuid.UUID) -> None:
    """When two entities merge, the duplicate's open assignments move to the survivor, except
    where the survivor has one of that type open already: those are cancelled, since one open
    assignment per subject and type is all the index allows."""
    taken = {assignment.type for assignment in await open_assignments(session, into_id)}
    for assignment in await open_assignments(session, from_id):
        if assignment.type in taken:
            lifecycle.cancel(assignment)
        else:
            assignment.subject_id = into_id
            taken.add(assignment.type)
    await session.flush()


async def record_usage(  # noqa: PLR0913
    session: AsyncSession,
    *,
    assignment_id: uuid.UUID,
    kind: UsageKind,
    provider: str,
    purpose: str,
    units: int,
    cached_units: int = 0,
    output_units: int = 0,
    at: datetime | None = None,
) -> Usage:
    """One priced model or search call for the assignment. `provider` is the price list's key:
    the model's name for a model call, the engine's name for a search. `purpose` names what the
    call was for (the assignment type, "handoff", "summary"). For a model, `units` is every
    token the call used, `cached_units` the input served from the cache and `output_units` the
    output; for a search, `units` is the requests. Flushed, not committed."""
    cost = load_prices().cost(
        kind, provider, units=units, cached_units=cached_units, output_units=output_units
    )
    if cost is None:
        if provider not in _unpriced:
            _unpriced.add(provider)
            logger.warning("No price for %s %s: its usage is recorded at zero cost", kind, provider)
        cost = Decimal(0)
    usage = Usage(
        assignment_id=assignment_id,
        kind=kind,
        provider=provider,
        purpose=purpose,
        units=units,
        cached_units=cached_units,
        cost=cost,
    )
    if at is not None:
        usage.at = at
    session.add(usage)
    await session.flush()
    return usage
