"""The settings every test builds on. Nothing here touches the environment: the configured
server (environment or `.env`) is read once, and the tests get a copy pointed at the test
database."""

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


@pytest.fixture(scope="session")
def configured_url() -> URL:
    """The development server, for creating the test database."""
    return _configured_url


@pytest.fixture(scope="session")
def test_database_name() -> str:
    return TEST_DATABASE


@pytest.fixture
def settings() -> Settings:
    """The configured settings, on the test database."""
    return _configured.model_copy(update={"database_url": PostgresDsn(_test_url)})
