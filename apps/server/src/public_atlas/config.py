"""Deployment settings, read from `PUBLIC_ATLAS_*` environment variables and `.env`.

Deployment values only: addresses, credentials, pool sizes, retention. Product data (country
names, institution types, prices, model names) lives in tables or data files, never here.
Nothing reads these at import time; each process builds one `Settings` at its entry point and
`build_resources` (resources.py) takes it as an argument.
"""

from datetime import timedelta
from pathlib import Path

from pydantic import Field, HttpUrl, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from public_atlas.integrations.storage import StorageProvider
from public_atlas.shared.logs import LogFormat


class Settings(BaseSettings):
    """`.env.example` documents every field."""

    # --- Logs ---
    log_level: str = "INFO"
    # "text" for a terminal, "json" for a log collector.
    log_format: LogFormat = "text"
    # Logfire write token. None: telemetry is off.
    logfire_token: SecretStr | None = None
    # Shown in Logfire to tell deployments apart.
    logfire_environment: str = "development"

    # --- Database ---
    database_url: PostgresDsn = PostgresDsn(
        "postgresql+psycopg://public_atlas:public_atlas@localhost:5432/public_atlas"
    )
    database_echo: bool = False
    database_pool_size: int = Field(5, ge=1)
    database_max_overflow: int = Field(10, ge=0)
    # PostgreSQL cancels any statement that runs longer than this.
    database_statement_timeout: timedelta = timedelta(seconds=30)

    # --- Object storage ---
    # "s3" covers every S3-compatible service: RustFS locally, Cloudflare R2 hosted.
    storage_provider: StorageProvider = "s3"
    storage_bucket: str = "public-atlas"
    # None for AWS S3 itself.
    storage_endpoint_url: HttpUrl | None = HttpUrl("http://127.0.0.1:9000")
    # Where the browser reaches storage, when that differs from the endpoint above.
    storage_public_endpoint_url: HttpUrl | None = None
    storage_region: str = "us-east-1"
    storage_access_key: str = "rustfsadmin"
    storage_secret_key: SecretStr = SecretStr("rustfsadmin")
    # True: host/bucket/key URLs (RustFS, MinIO). False: bucket.host/key (AWS, R2).
    storage_path_style: bool = True
    storage_url_ttl: timedelta = timedelta(minutes=15)

    # --- Official lists ---
    # Where `public-atlas load-list` keeps the files it downloads, checked against the hash the
    # list module records. Outside the repository, so it does not depend on the working directory.
    lists_cache_dir: Path = Field(
        default_factory=lambda: Path.home() / ".cache" / "public-atlas" / "official-lists"
    )

    # --- Background jobs ---
    # Jobs one worker process runs at a time.
    jobs_concurrency: int = Field(2, ge=1)
    # A job that failed for good stays in the queue's table, to be looked at, this long.
    purge_after: timedelta = timedelta(days=7)

    # env_ignore_empty: hosting platforms often pass an unset variable as "", which must read
    # as the default (None for the Logfire token), not as "".
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="PUBLIC_ATLAS_", env_ignore_empty=True
    )
