from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self
from urllib.parse import quote

from aiobotocore.config import AioConfig
from aiobotocore.session import get_session
from botocore.exceptions import ClientError

from public_atlas.integrations.storage.base import ObjectInfo, ObjectNotFoundError

if TYPE_CHECKING:
    from datetime import timedelta

    from types_aiobotocore_s3 import S3Client
    from types_aiobotocore_s3.type_defs import ObjectIdentifierTypeDef

MISSING = {"404", "NoSuchKey", "NotFound"}
# S3 deletes at most this many keys per request.
DELETE_BATCH = 1000


def content_disposition(filename: str) -> str:
    """`attachment` with the name in both the ASCII form (for old clients) and the
    RFC 5987 UTF-8 form (which every browser prefers). The ASCII form is a
    quoted-string, so quotes, backslashes, and control characters are replaced."""
    ascii_name = "".join(
        c if c.isprintable() and c != "\\" else "_"
        for c in filename.encode("ascii", "replace").decode()
    ).replace('"', "'")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


@dataclass(frozen=True, slots=True)
class S3Config:
    bucket: str
    access_key: str
    secret_key: str
    region: str = "us-east-1"
    # `None` is AWS itself.
    endpoint_url: str | None = None
    # The address the browser reaches the service at, when it differs from the one
    # the API uses (inside Docker, say). Presigned URLs embed the host they were
    # signed for, so they are signed with this one.
    public_endpoint_url: str | None = None
    # `host/bucket/key` (RustFS, MinIO) rather than `bucket.host/key` (AWS).
    path_style: bool = True


class S3ObjectStore:
    """One bucket on an S3-compatible service. Use as an async context manager: the
    clients are opened on enter."""

    def __init__(self, config: S3Config) -> None:
        self.bucket = config.bucket
        self._endpoint_url = config.endpoint_url
        self._public_endpoint_url = config.public_endpoint_url or config.endpoint_url
        self._client_kwargs = {
            "region_name": config.region,
            "aws_access_key_id": config.access_key,
            "aws_secret_access_key": config.secret_key,
            "config": AioConfig(
                signature_version="s3v4",
                s3={"addressing_style": "path" if config.path_style else "virtual"},
            ),
        }
        self._stack = AsyncExitStack()
        self._client: S3Client | None = None
        self._signer: S3Client | None = None

    async def __aenter__(self) -> Self:
        session = get_session()
        self._client = await self._stack.enter_async_context(
            session.create_client("s3", endpoint_url=self._endpoint_url, **self._client_kwargs)
        )
        if self._public_endpoint_url == self._endpoint_url:
            self._signer = self._client
        else:
            self._signer = await self._stack.enter_async_context(
                session.create_client(
                    "s3", endpoint_url=self._public_endpoint_url, **self._client_kwargs
                )
            )
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._stack.aclose()
        self._client = self._signer = None

    @property
    def client(self) -> S3Client:
        if self._client is None:
            msg = "S3ObjectStore is used outside its `async with` block"
            raise RuntimeError(msg)
        return self._client

    @property
    def signer(self) -> S3Client:
        if self._signer is None:
            msg = "S3ObjectStore is used outside its `async with` block"
            raise RuntimeError(msg)
        return self._signer

    async def ping(self) -> None:
        await self.client.head_bucket(Bucket=self.bucket)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
        )

    async def get(self, key: str) -> bytes:
        try:
            response = await self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in MISSING:
                raise ObjectNotFoundError(key) from exc
            raise
        async with response["Body"] as body:
            return await body.read()

    async def head(self, key: str) -> ObjectInfo | None:
        try:
            response = await self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in MISSING:
                return None
            raise
        return ObjectInfo(
            key=key,
            size=response["ContentLength"],
            content_type=response.get("ContentType", "application/octet-stream"),
        )

    async def delete(self, key: str) -> None:
        await self.client.delete_object(Bucket=self.bucket, Key=key)

    async def delete_prefix(self, prefix: str) -> None:
        paginator = self.client.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys: list[ObjectIdentifierTypeDef] = [
                {"Key": item["Key"]} for item in page.get("Contents", [])
            ]
            for start in range(0, len(keys), DELETE_BATCH):
                await self.client.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": keys[start : start + DELETE_BATCH], "Quiet": True},
                )

    async def upload_url(
        self, key: str, content_type: str, size: int, expires_in: timedelta
    ) -> str:
        # `ContentType` and `ContentLength` become signed headers: a PUT with another
        # type or another body size fails the signature check before anything is
        # written.
        return await self.signer.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ContentType": content_type,
                "ContentLength": size,
            },
            ExpiresIn=int(expires_in.total_seconds()),
        )

    async def download_url(self, key: str, filename: str, expires_in: timedelta) -> str:
        return await self.signer.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentDisposition": content_disposition(filename),
            },
            ExpiresIn=int(expires_in.total_seconds()),
        )
