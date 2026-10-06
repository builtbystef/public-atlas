"""The request ID, trace and attempt number a job run carries, so its logs and spans line up."""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from public_atlas.shared import telemetry
from public_atlas.shared.logs import new_request_id, request_id

type Trace = dict[str, str]

REQUEST_ID = "request_id"

# One line per run, like `public_atlas.access` has one per request.
log = logging.getLogger("public_atlas.jobs")


@dataclass(frozen=True, slots=True)
class Attempt:
    """Which run of its job this is. On the last one a failure is not retried, so a job that
    leaves state behind settles it before raising."""

    number: int
    last: bool


# Outside a job (a test, a script) nothing retries, so every run is the last.
OUTSIDE_A_JOB = Attempt(1, last=True)
current_attempt: ContextVar[Attempt] = ContextVar("current_attempt", default=OUTSIDE_A_JOB)


def trace() -> Trace:
    """The current request ID (none outside a request) and trace context."""
    carrier: Trace = {}
    if (rid := request_id.get()) != "-":
        carrier[REQUEST_ID] = rid
    telemetry.inject(carrier)
    return carrier


@contextmanager
def running(
    name: str, job_id: int | None, carrier: Trace | None, attempt: Attempt = OUTSIDE_A_JOB
) -> Iterator[None]:
    """The context a run executes in. A job the schedule sent, or a retry of one,
    has no request: it gets an ID of its own, so its lines still group."""
    carrier = carrier or {}
    token = request_id.set(carrier.get(REQUEST_ID) or new_request_id())
    attempt_token = current_attempt.set(attempt)
    started = time.perf_counter()
    try:
        with telemetry.job_span(name, job_id, carrier):
            yield
    except Exception:
        log.exception(
            "%s[%s] failed after %.1fms on attempt %d%s",
            name,
            job_id,
            _ms(started),
            attempt.number,
            " (the last)" if attempt.last else "",
        )
        raise
    else:
        log.info("%s[%s] done in %.1fms", name, job_id, _ms(started))
    finally:
        current_attempt.reset(attempt_token)
        request_id.reset(token)


def _ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


__all__ = ["OUTSIDE_A_JOB", "REQUEST_ID", "Attempt", "Trace", "current_attempt", "running", "trace"]
