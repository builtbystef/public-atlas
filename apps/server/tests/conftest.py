"""The settings every test builds on, and the skips for tests whose tools are absent. Nothing
here touches the environment: the configured server (environment or `.env`) is read once, and
the tests get a copy pointed at the test database, with the in-memory parser and no search
engine."""

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import PostgresDsn
from sqlalchemy.engine import make_url

from public_atlas.config import Settings

if TYPE_CHECKING:
    from sqlalchemy.engine import URL

TEST_DATABASE = "public_atlas_test"

# The development server, as configured.
_configured = Settings()
_configured_url = make_url(str(_configured.database_url))
_test_url = _configured_url.set(database=TEST_DATABASE).render_as_string(hide_password=False)

# Only the `parse-cpu` dependency group installs Docling; CI runs the `parse` tests in a job of
# their own.
HAS_DOCLING = importlib.util.find_spec("docling") is not None


def _has_chromium() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415

        with sync_playwright() as playwright:
            return Path(playwright.chromium.executable_path).exists()
    except Exception:  # noqa: BLE001 - any failure to ask means no browser
        return False


HAS_CHROMIUM = _has_chromium()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    skips = []
    if not HAS_DOCLING:
        skips.append(("parse", "Docling is not installed (uv sync --group parse-cpu)"))
    if not HAS_CHROMIUM:
        skips.append(("browser", "Chromium is not installed (vp run browser:install)"))
    for marker, reason in skips:
        skip = pytest.mark.skip(reason=reason)
        for item in items:
            if item.get_closest_marker(marker) is not None:
                item.add_marker(skip)


@pytest.fixture(scope="session")
def configured_url() -> URL:
    """The development server, for creating the test database."""
    return _configured_url


@pytest.fixture(scope="session")
def test_database_name() -> str:
    return TEST_DATABASE


@pytest.fixture
def settings() -> Settings:
    """The configured settings, on the test database, with the in-memory parser, no search
    engine and no model: tests never load Docling, call Brave or run a real model."""
    return _configured.model_copy(
        update={
            "database_url": PostgresDsn(_test_url),
            "parse_provider": "memory",
            "search_provider": "none",
            "openai_api_key": None,
        }
    )
