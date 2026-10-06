from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import timedelta


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    key: str
    size: int
    content_type: str


class ObjectStore(Protocol):
    """Implement this to add a backend, then return it from `create_object_store`.

    The store holds bytes and a content type, nothing else. Access is decided by
    the app, which hands out short-lived URLs so the bytes never pass through
    the API.
    """

    async def ping(self) -> None:
        """Raises when the store (or the bucket) is not reachable. For health checks."""
        ...

    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes:
        """Raises `ObjectNotFoundError`."""
        ...

    async def head(self, key: str) -> ObjectInfo | None:
        """`None` when there is no such object."""
        ...

    async def delete(self, key: str) -> None:
        """Deleting a missing object is not an error."""
        ...

    async def delete_prefix(self, prefix: str) -> None:
        """Delete every object whose key starts with `prefix`."""
        ...

    async def upload_url(
        self, key: str, content_type: str, size: int, expires_in: timedelta
    ) -> str:
        """A URL that accepts one `PUT` of a body with exactly this `Content-Type` and
        exactly `size` bytes. The store refuses anything else, so a client cannot
        upload more than it declared."""
        ...

    async def download_url(self, key: str, filename: str, expires_in: timedelta) -> str:
        """A URL that serves the object as a download named `filename`."""
        ...


class ObjectNotFoundError(KeyError):
    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key
