"""The one place an assignment changes status (spec section 12.2). `status` is the lifecycle,
`result` says how a finished one ended; the two are never mixed. One function per move the
runs and the runner make, each going through the same check of the allowed moves."""

from public_atlas.db.base import utcnow
from public_atlas.modules.assignments.models import (
    Assignment,
    AssignmentResult,
    AssignmentStatus,
)
from public_atlas.shared.exceptions import ConflictError

__all__ = ["MOVES", "cancel", "finish", "move", "queue", "start"]

# From each status, where it may go.
MOVES: dict[AssignmentStatus, frozenset[AssignmentStatus]] = {
    AssignmentStatus.HELD: frozenset({AssignmentStatus.QUEUED, AssignmentStatus.CANCELLED}),
    AssignmentStatus.QUEUED: frozenset({AssignmentStatus.RUNNING, AssignmentStatus.CANCELLED}),
    # Running goes back to queued when a job has run its twenty sessions and requeues itself, and
    # to cancelled when its run was stopped: after its session, by the runner alone.
    AssignmentStatus.RUNNING: frozenset(
        {AssignmentStatus.QUEUED, AssignmentStatus.FINISHED, AssignmentStatus.CANCELLED}
    ),
    AssignmentStatus.FINISHED: frozenset(),
    AssignmentStatus.CANCELLED: frozenset(),
}


def move(
    assignment: Assignment, status: AssignmentStatus, *, result: AssignmentResult | None = None
) -> None:
    """Move the assignment to `status`, or refuse. A result comes only with `finished`."""
    if status not in MOVES[assignment.status]:
        raise ConflictError(
            f"an assignment cannot go from {assignment.status.value} to {status.value}"
        )
    if (result is not None) != (status is AssignmentStatus.FINISHED):
        raise ConflictError("a result belongs to a finished assignment and to nothing else")
    assignment.status = status
    assignment.result = result


def queue(assignment: Assignment) -> None:
    """A held assignment released, or a running one whose job has had its twenty sessions."""
    move(assignment, AssignmentStatus.QUEUED)


def start(assignment: Assignment) -> None:
    """A worker picked it up: the first session starts the clock."""
    move(assignment, AssignmentStatus.RUNNING)
    if assignment.started_at is None:
        assignment.started_at = utcnow()


def finish(assignment: Assignment, result: AssignmentResult, *, summary: str | None = None) -> None:
    move(assignment, AssignmentStatus.FINISHED, result=result)
    assignment.finished_at = utcnow()
    if summary is not None:
        assignment.summary = summary


def cancel(assignment: Assignment) -> None:
    move(assignment, AssignmentStatus.CANCELLED)
