import logging
import time
from typing import TYPE_CHECKING

from starlette import status
from starlette.responses import JSONResponse

from public_atlas.shared.logs import new_request_id, request_id

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger(__name__)
# One line per request, with the request ID. Replaces Uvicorn's access log.
access_log = logging.getLogger("public_atlas.access")

REQUEST_ID_HEADER = "X-Request-ID"
_MAX_REQUEST_ID_LENGTH = 128

INTERNAL_ERROR_DETAIL = "Something went wrong. Quote the request ID when reporting it."


def _incoming_request_id(scope: Scope) -> str | None:
    """A caller's ID, if it is short printable ASCII (log lines and headers must
    stay clean). `None` to make one."""
    header = REQUEST_ID_HEADER.lower().encode()
    for name, value in scope["headers"]:
        if name == header:
            candidate = value.decode("latin-1").strip()
            if (
                0 < len(candidate) <= _MAX_REQUEST_ID_LENGTH
                and candidate.isascii()
                and candidate.isprintable()
            ):
                return candidate
            return None
    return None


def is_health_check(path: str) -> bool:
    """Polled, so left out of the access log (and of telemetry, see there)."""
    return path == "/health" or path.startswith("/health/")


class RequestIdMiddleware:
    """Sets the request ID for the request, echoes it in the response, answers an
    unhandled error with a 500 that quotes it, and writes the access log line.

    Pure ASGI, so it costs one dict lookup per request rather than a task per
    request like `BaseHTTPMiddleware`.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid = _incoming_request_id(scope) or new_request_id()
        scope.setdefault("state", {})["request_id"] = rid
        token = request_id.set(rid)
        started = time.perf_counter()
        status_code: int | None = None

        async def send_with_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = message.setdefault("headers", [])
                headers.append((REQUEST_ID_HEADER.lower().encode(), rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            if status_code is not None:
                # Too late for a body of our own; the server closes the connection.
                raise
            log.exception("Unhandled error on %s %s", scope["method"], scope["path"])
            response = JSONResponse(
                {"detail": INTERNAL_ERROR_DETAIL, "request_id": rid},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
            await response(scope, receive, send_with_id)
        finally:
            if not is_health_check(scope["path"]):
                elapsed_ms = (time.perf_counter() - started) * 1000
                access_log.info(
                    "%s %s %s %.1fms",
                    scope["method"],
                    scope["path"],
                    status_code if status_code is not None else "-",
                    elapsed_ms,
                )
            request_id.reset(token)
