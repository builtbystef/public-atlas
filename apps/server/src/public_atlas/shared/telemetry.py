import logging
from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from typing import TYPE_CHECKING, Any

import logfire
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncEngine
    from starlette.requests import Request
    from starlette.websockets import WebSocket

    from public_atlas.config import Settings


def enabled(settings: Settings) -> bool:
    return settings.logfire_token is not None


def configure(settings: Settings, *, service_name: str) -> logfire.LogfireLoggingHandler | None:
    """Connect to Logfire and return the handler that forwards the app's logs, or
    None when telemetry is off. Call once per process, before instrumenting."""
    if settings.logfire_token is None:
        return None
    logfire.configure(
        token=settings.logfire_token.get_secret_value(),
        service_name=service_name,
        environment=settings.logfire_environment,
        # The plain logging handler already prints to the terminal.
        console=False,
        # Do not continue a trace from an incoming `traceparent` header: the web
        # app sends none, and anyone could.
        distributed_tracing=False,
    )
    handler = logfire.LogfireLoggingHandler()
    handler.addFilter(_OwnLogsAndWarnings())
    return handler


class _OwnLogsAndWarnings(logging.Filter):
    """The app's own records at any level; libraries only when something is wrong.
    Keeps Procrastinate's and Uvicorn's per-request chatter out."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith("public_atlas") or record.levelno >= logging.WARNING


def quiet() -> AbstractContextManager[None]:
    """Records nothing inside. For polled checks, which would otherwise leave a
    span per poll."""
    return logfire.suppress_instrumentation()


def instrument_app(app: FastAPI) -> None:
    """One span per request. Health checks are polled, so they are left out (their
    handlers run under `quiet` for the same reason)."""
    logfire.instrument_fastapi(
        app,
        excluded_urls=r"/health(/.*)?$",
        request_attributes_mapper=_drop_endpoint_arguments,
    )


def instrument_engine(engine: AsyncEngine) -> None:
    logfire.instrument_sqlalchemy(engine=engine.sync_engine)


def _drop_endpoint_arguments(
    _request: Request | WebSocket, attributes: dict[str, Any]
) -> dict[str, Any]:
    """The parsed endpoint arguments include emails, names, and passwords. Keep only
    which fields failed validation, which names no values."""
    return {"errors": attributes["errors"]} if attributes.get("errors") else {}


def inject(carrier: dict[str, str]) -> None:
    """Write the current trace context into `carrier`, for a job's arguments.
    Writes nothing when telemetry is off."""
    propagate.inject(carrier)


@contextmanager
def job_span(name: str, job_id: int | None, carrier: Mapping[str, str]) -> Iterator[None]:
    """One span per job run, under the request that queued it when `carrier` holds
    its trace context. An exception is recorded and re-raised. Nothing is
    recorded when telemetry is off."""
    attributes: dict[str, str | int] = {"job.name": name}
    if job_id is not None:
        attributes["job.id"] = job_id
    with trace.get_tracer(__name__).start_as_current_span(
        f"job {name}",
        context=propagate.extract(carrier),
        kind=SpanKind.CONSUMER,
        attributes=attributes,
    ):
        yield
