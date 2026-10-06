from typing import TYPE_CHECKING, Literal

from public_atlas.integrations.storage.base import ObjectInfo, ObjectNotFoundError, ObjectStore
from public_atlas.integrations.storage.s3 import S3Config, S3ObjectStore

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from public_atlas.config import Settings

StorageProvider = Literal["s3"]


def create_object_store(settings: Settings) -> AbstractAsyncContextManager[ObjectStore]:
    match settings.storage_provider:
        case "s3":
            return S3ObjectStore(
                S3Config(
                    bucket=settings.storage_bucket,
                    access_key=settings.storage_access_key,
                    secret_key=settings.storage_secret_key.get_secret_value(),
                    region=settings.storage_region,
                    endpoint_url=url_or_none(settings.storage_endpoint_url),
                    public_endpoint_url=url_or_none(settings.storage_public_endpoint_url),
                    path_style=settings.storage_path_style,
                )
            )


def url_or_none(url: object) -> str | None:
    """`HttpUrl` adds a trailing slash, which botocore would double."""
    return None if url is None else str(url).rstrip("/")


__all__ = [
    "ObjectInfo",
    "ObjectNotFoundError",
    "ObjectStore",
    "S3Config",
    "S3ObjectStore",
    "StorageProvider",
    "create_object_store",
]
