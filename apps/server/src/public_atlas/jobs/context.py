import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

from public_atlas.shared import telemetry
from public_atlas.shared.logs import new_request_id, request_id

type Trace = dict[str, str]

REQUEST_ID = "request_id"

# One line per run, like `public_atlas.access` has one per request.
log = logging.getLogger("public_atlas.jobs")


def trace() -> Trace:
    """The current request ID (none outside a request) and trace context."""
    carrier: Trace = {}
    if (rid := request_id.get()) != "-":
        carrier[REQUEST_ID] = rid
    telemetry.inject(carrier)
    return carrier


@contextmanager
def running(name: str, job_id: int | None, carrier: Trace | None) -> Iterator[None]:
    """The context a run executes in. A job the schedule sent, or a retry of one,
    has no request: it gets an ID of its own, so its lines still group."""
    carrier = carrier or {}
    token = request_id.set(carrier.get(REQUEST_ID) or new_request_id())
    started = time.perf_counter()
    try:
        with telemetry.job_span(name, job_id, carrier):
            yield
    except Exception:
        log.exception("%s[%s] failed after %.1fms", name, job_id, _ms(started))
        raise
    else:
        log.info("%s[%s] done in %.1fms", name, job_id, _ms(started))
    finally:
        request_id.reset(token)


def _ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


__all__ = ["REQUEST_ID", "Trace", "running", "trace"]
