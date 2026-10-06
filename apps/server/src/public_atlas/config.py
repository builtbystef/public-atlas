"""Deployment settings, read from `PUBLIC_ATLAS_*` environment variables and `.env`.

Deployment values only: addresses, credentials, pool sizes, retention, budgets. Product data
(country names, institution types, prices, model names) lives in tables or data files, never
here. Nothing reads these at import time; each process builds one `Settings` at its entry point
and `build_resources` (resources.py) takes it as an argument.
"""

from datetime import timedelta
from pathlib import Path

from pydantic import Field, HttpUrl, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from public_atlas.integrations.parse import ParseProvider
from public_atlas.integrations.search import SearchProvider
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
    # "s3" covers every S3-compatible service: RustFS locally, Cloudflare R2 hosted (see
    # `.env.example` for the R2 values).
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

    # --- Parsing ---
    # "docling" needs the parse dependency group, which only the parse image installs. "memory"
    # is the test double: the bytes are the text.
    parse_provider: ParseProvider = "docling"
    # Pages of a PDF per Docling call. Docling keeps every page of a call in memory until the
    # call is done: a long budget book parsed in one call took the worker past 10 GB. A call is
    # cheap, so few pages. A file whose first attempt took the worker down is retried one page
    # per call.
    parse_page_batch: int = Field(10, ge=1)
    # Per range of `parse_page_batch` pages; a range that runs longer fails the parse.
    parse_timeout: timedelta = timedelta(minutes=3)
    # After a job, the parse worker stops itself once its resident memory passes this many MB,
    # and its supervisor restarts it: Docling and the OCR runtime keep what a heavy page cost,
    # and a fresh process is the only way to give it back.
    parse_retire_rss_mb: int = Field(4000, ge=1)
    # A PDF with more pages is recorded `failed` unparsed, and the agent is told why.
    parse_max_pages: int = Field(500, ge=1)

    # --- Browser ---
    # Token cap on what one browser tool call returns to the model.
    browser_max_content_tokens: int = Field(8000, ge=500)
    # At least this long between two page loads on one host, across every session the worker
    # runs. At one second, with two sessions on the anchor, ontario.ca throttled the network
    # within two minutes.
    browser_min_interval: timedelta = timedelta(seconds=3)
    browser_respect_robots: bool = True
    # Off where Chromium's sandbox cannot start, as in a container without the privileges it
    # needs.
    browser_chromium_sandbox: bool = True

    # --- Files (the read_file tool) ---
    read_file_max_bytes: int = Field(50 * 1024 * 1024, ge=1024)
    # Characters of text per chunk returned to the model.
    read_file_chunk_chars: int = Field(12_000, ge=1000)
    # How long the tool waits for the parse queue before telling the agent to check `status`.
    read_file_wait: timedelta = timedelta(seconds=90)
    # A file another assignment fetched this recently is read from its snapshot, text included,
    # instead of being downloaded and parsed again.
    read_file_reuse: timedelta = timedelta(days=1)

    # --- Web search ---
    # "brave" backs the `search` tool; "none" leaves the tool out.
    search_provider: SearchProvider = "none"
    brave_api_key: SecretStr | None = None

    # env_ignore_empty: hosting platforms often pass an unset variable as "", which must read
    # as the default (None for the Logfire token), not as "".
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="PUBLIC_ATLAS_", env_ignore_empty=True
    )
