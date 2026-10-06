"""The one place an assignment changes status (spec section 12.2). `status` is the lifecycle,
`result` says how a finished one ended; the two are never mixed. Phase 4 adds the moves the
runner and the runs make; here are the moves and the check every one goes through."""

from public_atlas.modules.assignments.models import (
    Assignment,
    AssignmentResult,
    AssignmentStatus,
)
from public_atlas.shared.exceptions import ConflictError

# From each status, where it may go.
MOVES: dict[AssignmentStatus, frozenset[AssignmentStatus]] = {
    AssignmentStatus.HELD: frozenset({AssignmentStatus.QUEUED, AssignmentStatus.CANCELLED}),
    AssignmentStatus.QUEUED: frozenset({AssignmentStatus.RUNNING, AssignmentStatus.CANCELLED}),
    # Running goes back to queued when a job has run its twenty sessions and requeues itself.
    AssignmentStatus.RUNNING: frozenset({AssignmentStatus.QUEUED, AssignmentStatus.FINISHED}),
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


def cancel(assignment: Assignment) -> None:
    move(assignment, AssignmentStatus.CANCELLED)
