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

HELD = AssignmentStatus.HELD
QUEUED = AssignmentStatus.QUEUED
RUNNING = AssignmentStatus.RUNNING
FINISHED = AssignmentStatus.FINISHED
CANCELLED = AssignmentStatus.CANCELLED
STATUSES = [HELD, QUEUED, RUNNING, FINISHED, CANCELLED]
# The allowed moves, written out: a held assignment is released or cancelled, a queued one is picked
# up or cancelled, a running one is put back, finished or cancelled, and a finished or cancelled one
# goes nowhere.
ALLOWED = {
    (HELD, QUEUED),
    (HELD, CANCELLED),
    (QUEUED, RUNNING),
    (QUEUED, CANCELLED),
    (RUNNING, QUEUED),
    (RUNNING, FINISHED),
    (RUNNING, CANCELLED),
}


def assignment(status: AssignmentStatus) -> Assignment:
    """An assignment at `status`, with no run or subject behind it."""
    return Assignment(
        run_id=uuid.uuid7(),
        type=AssignmentType.FIND_SOURCES,
        subject_id=uuid.uuid7(),
        status=status,
        budget_requests=1,
        budget_tokens=1,
    )


@pytest.mark.parametrize(
    ("start", "end"),
    [(start, end) for start in STATUSES for end in STATUSES],
    ids=lambda status: status.value,
)
def test_the_transition_table(start: AssignmentStatus, end: AssignmentStatus):
    """Every pair of statuses: the seven allowed moves go through, with a result on the move to
    `finished`; the other eighteen are refused by name and leave the assignment as it was."""
    row = assignment(start)
    result = AssignmentResult.COMPLETE if end is FINISHED else None
    if (start, end) in ALLOWED:
        lifecycle.move(row, end, result=result)
        assert (row.status, row.result) == (end, result)
    else:
        with pytest.raises(ConflictError, match=f"from {start.value} to {end.value}"):
            lifecycle.move(row, end, result=result)
        assert (row.status, row.result) == (start, None)


def test_a_result_belongs_to_finished_only():
    running = assignment(RUNNING)
    with pytest.raises(ConflictError, match="a result belongs to a finished assignment"):
        lifecycle.move(running, FINISHED)
    with pytest.raises(ConflictError, match="a result belongs to a finished assignment"):
        lifecycle.move(running, QUEUED, result=AssignmentResult.COMPLETE)
    assert (running.status, running.result) == (RUNNING, None)


def test_the_named_moves_set_the_timestamps():
    """Release queues a held one; a worker starts it once; a requeue puts it back without
    touching the start; finishing stamps the end and keeps the summary it is given."""
    held = assignment(HELD)
    assert (held.started_at, held.finished_at) == (None, None)
    lifecycle.queue(held)
    lifecycle.start(held)
    started = held.started_at
    assert started is not None
    lifecycle.queue(held)
    lifecycle.start(held)
    assert held.started_at is started
    lifecycle.finish(held, AssignmentResult.OUT_OF_BUDGET, summary="Budget exhausted")
    assert (held.status, held.result, held.summary) == (
        FINISHED,
        AssignmentResult.OUT_OF_BUDGET,
        "Budget exhausted",
    )
    assert held.finished_at is not None
    with pytest.raises(ConflictError, match="from finished to running"):
        lifecycle.start(held)


def test_finishing_without_a_summary_keeps_the_old_one():
    """A finish that says nothing (a failed job's, a stopped run's) leaves the summary the
    agent wrote in an earlier session."""
    running = assignment(RUNNING)
    running.summary = "Halfway through the directory."
    lifecycle.finish(running, AssignmentResult.FAILED)
    assert (running.status, running.result, running.summary) == (
        FINISHED,
        AssignmentResult.FAILED,
        "Halfway through the directory.",
    )
