"""An assignment's status moves only along the allowed moves, and a result comes only with
`finished`."""

import uuid

import pytest

from public_atlas.modules.assignments import lifecycle
from public_atlas.modules.assignments.models import (
    Assignment,
    AssignmentResult,
    AssignmentStatus,
    AssignmentType,
)
from public_atlas.shared.exceptions import ConflictError


def assignment(status: AssignmentStatus) -> Assignment:
    return Assignment(
        run_id=uuid.uuid7(),
        type=AssignmentType.FIND_SOURCES,
        subject_id=uuid.uuid7(),
        status=status,
        budget_requests=1,
        budget_tokens=1,
    )


def test_the_allowed_moves():
    held = assignment(AssignmentStatus.HELD)
    lifecycle.move(held, AssignmentStatus.QUEUED)
    lifecycle.move(held, AssignmentStatus.RUNNING)
    lifecycle.move(held, AssignmentStatus.FINISHED, result=AssignmentResult.COMPLETE)
    assert (held.status, held.result) == (AssignmentStatus.FINISHED, AssignmentResult.COMPLETE)
    with pytest.raises(ConflictError, match="finished to queued"):
        lifecycle.move(held, AssignmentStatus.QUEUED)


def test_a_result_belongs_to_finished_only():
    running = assignment(AssignmentStatus.RUNNING)
    with pytest.raises(ConflictError, match="result"):
        lifecycle.move(running, AssignmentStatus.FINISHED)
    with pytest.raises(ConflictError, match="result"):
        lifecycle.move(running, AssignmentStatus.QUEUED, result=AssignmentResult.COMPLETE)
    assert running.status is AssignmentStatus.RUNNING


def test_cancel():
    queued = assignment(AssignmentStatus.QUEUED)
    lifecycle.cancel(queued)
    assert queued.status is AssignmentStatus.CANCELLED
    with pytest.raises(ConflictError):
        lifecycle.cancel(assignment(AssignmentStatus.RUNNING))
