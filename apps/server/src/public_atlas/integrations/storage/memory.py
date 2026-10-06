from typing import TYPE_CHECKING

from public_atlas.integrations.storage.base import ObjectInfo, ObjectNotFoundError

if TYPE_CHECKING:
    from datetime import timedelta


class MemoryObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    @staticmethod
    def key_of(url: str) -> str:
        """The object key an `upload_url`/`download_url` of this store was made for."""
        return url.removeprefix("memory://").split("?", 1)[0]

    async def ping(self) -> None:
        return

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    async def get(self, key: str) -> bytes:
        try:
            return self.objects[key][0]
        except KeyError:
            raise ObjectNotFoundError(key) from None

    async def head(self, key: str) -> ObjectInfo | None:
        if key not in self.objects:
            return None
        data, content_type = self.objects[key]
        return ObjectInfo(key=key, size=len(data), content_type=content_type)

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    async def delete_prefix(self, prefix: str) -> None:
        for key in [k for k in self.objects if k.startswith(prefix)]:
            del self.objects[key]

    async def upload_url(
        self, key: str, content_type: str, size: int, expires_in: timedelta
    ) -> str:
        return (
            f"memory://{key}?put&content_type={content_type}&size={size}"
            f"&expires={int(expires_in.total_seconds())}"
        )

    async def download_url(self, key: str, filename: str, expires_in: timedelta) -> str:
        return f"memory://{key}?get&filename={filename}&expires={int(expires_in.total_seconds())}"
