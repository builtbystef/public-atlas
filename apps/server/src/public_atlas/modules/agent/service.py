"""The agent module's door: running an assignment, and settling one whose job died."""

from public_atlas.modules.agent.context import SessionContext, SubjectMissingError, build_context
from public_atlas.modules.agent.runner import (
    MAX_SESSIONS_PER_JOB,
    PAUSED,
    ModelUnavailableError,
    record_failure,
    run_assignment,
    run_session,
)

__all__ = [
    "MAX_SESSIONS_PER_JOB",
    "PAUSED",
    "ModelUnavailableError",
    "SessionContext",
    "SubjectMissingError",
    "build_context",
    "record_failure",
    "run_assignment",
    "run_session",
]
