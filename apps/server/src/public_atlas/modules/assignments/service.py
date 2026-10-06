"""The assignments module's door. Phase 2: recording what a call cost. Phase 4 adds runs,
assignments, spawning and budgets."""

import logging
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.assignments.models import Usage, UsageKind
from public_atlas.modules.assignments.pricing import load_prices

__all__ = ["record_usage"]

logger = logging.getLogger(__name__)

_unpriced: set[str] = set()


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
