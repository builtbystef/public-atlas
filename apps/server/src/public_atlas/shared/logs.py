import json
import logging
import secrets
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Literal

LogFormat = Literal["text", "json"]

# Set by the API's request-ID middleware for the length of a request, and by
# `jobs.context.running` for the length of a job run. "-" outside both.
request_id: ContextVar[str] = ContextVar("request_id", default="-")

TEXT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] [%(request_id)s] %(message)s"

# Uvicorn gives these their own handlers. They are pointed at ours instead, so
# every line has the same shape, and its access log is dropped in favour of
# `public_atlas.access`, which carries the request ID.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error")
_UVICORN_ACCESS_LOGGER = "uvicorn.access"
# Its lines quote every job's arguments (an email with its link, say), so its
# chatter is dropped in favour of `public_atlas.jobs`, one line per run. A job
# that has failed for good is still reported here, arguments and traceback included.
_PROCRASTINATE_WORKER_LOGGER = "procrastinate.worker"


def new_request_id() -> str:
    return secrets.token_hex(8)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


class TextFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__(TEXT_FORMAT)

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802, ARG002
        return _timestamp(record)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, str] = {
            "time": _timestamp(record),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", request_id.get()),
            "message": record.getMessage(),
        }
        if record.exc_info:
            line["exception"] = self.formatException(record.exc_info)
        return json.dumps(line, ensure_ascii=False)


def _timestamp(record: logging.LogRecord) -> str:
    created = datetime.fromtimestamp(record.created, tz=UTC)
    return created.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def make_formatter(log_format: LogFormat) -> logging.Formatter:
    return JsonFormatter() if log_format == "json" else TextFormatter()


def configure(level: str, log_format: LogFormat = "text") -> None:
    """A handler and level for the root logger, so the app's loggers print, and
    Uvicorn's loggers routed through it. Adds nothing where the root logger
    already has a handler (the tests' capture, say), but still filters and
    formats what is there.
    """
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        root.addHandler(logging.StreamHandler(sys.stderr))
    formatter = make_formatter(log_format)
    for handler in root.handlers:
        handler.setFormatter(formatter)
        if not any(isinstance(f, RequestIdFilter) for f in handler.filters):
            handler.addFilter(RequestIdFilter())

    for name in _UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    access = logging.getLogger(_UVICORN_ACCESS_LOGGER)
    access.handlers.clear()
    access.propagate = False
    logging.getLogger(_PROCRASTINATE_WORKER_LOGGER).setLevel(logging.WARNING)
