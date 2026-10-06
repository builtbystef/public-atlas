"""One `usage` row per priced call."""

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from public_atlas.modules.assignments import service
from public_atlas.modules.assignments.models import Usage, UsageKind

if TYPE_CHECKING:
    from tests.integration.conftest import Database

    from public_atlas.modules.assignments.models import Assignment


def test_model_and_search_calls_are_recorded_and_priced(
    db: Database, assignment: Assignment, caplog: pytest.LogCaptureFixture
):
    async def scenario() -> list[Usage]:
        async with db.session() as session:
            await service.record_usage(
                session,
                assignment_id=assignment.id,
                kind=UsageKind.MODEL,
                provider="gpt-6-luna",
                purpose="find_sources",
                units=1_000_000,
                cached_units=200_000,
                output_units=100_000,
            )
            await service.record_usage(
                session,
                assignment_id=assignment.id,
                kind=UsageKind.SEARCH,
                provider="brave",
                purpose="find_homepage",
                units=1,
            )
            await service.record_usage(
                session,
                assignment_id=assignment.id,
                kind=UsageKind.MODEL,
                provider="gpt-9",
                purpose="summary",
                units=10,
            )
            await session.commit()
            return list(
                await session.scalars(
                    select(Usage).where(Usage.assignment_id == assignment.id).order_by(Usage.id)
                )
            )

    model, search, unpriced = db.run(scenario)
    assert (model.kind, model.provider, model.units, model.cached_units) == (
        UsageKind.MODEL,
        "gpt-6-luna",
        1_000_000,
        200_000,
    )
    assert model.cost == Decimal("0.122000")
    assert (search.kind, search.units, search.cost) == (UsageKind.SEARCH, 1, Decimal("0.005000"))
    assert unpriced.cost == Decimal(0)
    assert "No price for model gpt-9" in caplog.text
