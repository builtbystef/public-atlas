from typing import TYPE_CHECKING, ClassVar, cast

from starlette import status
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.requests import Request


class AppError(Exception):
    """Base class. `detail` is what the client sees; `status_code` is per subclass."""

    status_code: ClassVar[int] = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, detail: str, *, headers: dict[str, str] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.headers = headers


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN


class NotFoundError(AppError):
    """No such row for this caller. Also for rows that exist outside their reach, so ids
    leak nothing."""

    status_code = status.HTTP_404_NOT_FOUND


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT


class GoneError(AppError):
    """The link or token existed but has expired."""

    status_code = status.HTTP_410_GONE


class PayloadTooLargeError(AppError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS


async def handle_app_error(_request: Request, exc: Exception) -> JSONResponse:
    """Registered for `AppError`, so that is what arrives; typed as Starlette asks."""
    error = cast("AppError", exc)
    return JSONResponse(
        {"detail": error.detail}, status_code=error.status_code, headers=error.headers
    )
