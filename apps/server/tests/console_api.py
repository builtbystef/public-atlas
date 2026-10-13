"""The API for the console smoke (apps/web/e2e), on a database of its own: `public_atlas_e2e`
on the configured server, dropped and rebuilt each time (migrated, then seeded with Canada), so
the smoke never writes to the development database and always starts from the same rows. Then
serves the API on that database, on the port given (8100 by default):

    uv run python tests/console_api.py [port]

apps/web/playwright.config.ts starts it. Not a test module, so pytest does not collect it."""

import asyncio
import os
import sys

from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from public_atlas.cli import seed
from public_atlas.config import Settings
from public_atlas.db import migrations

E2E_DATABASE = "public_atlas_e2e"


def rebuild_database(settings: Settings) -> str:
    """Drop and create the e2e database on the configured server. Its URL."""
    configured = make_url(str(settings.database_url))
    if configured.database == E2E_DATABASE:
        raise SystemExit(f"the configured database is {E2E_DATABASE!r}; the smoke would drop it")
    # DROP and CREATE DATABASE cannot run inside a transaction, hence autocommit.
    engine = create_engine(configured, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        with engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{E2E_DATABASE}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{E2E_DATABASE}"'))
    finally:
        engine.dispose()
    return configured.set(database=E2E_DATABASE).render_as_string(hide_password=False)


def main() -> None:
    port = sys.argv[1] if len(sys.argv) > 1 else "8100"
    # The environment wins over .env, so Alembic's env.py, the seed and the API all read it.
    os.environ["PUBLIC_ATLAS_DATABASE_URL"] = rebuild_database(Settings())
    command.upgrade(migrations.alembic_config(), "head")
    asyncio.run(seed(Settings(), "canada"))
    # The API replaces this process, so Playwright stops the server it started.
    os.execv(sys.executable, [sys.executable, "-m", "fastapi", "run", "--port", port])  # noqa: S606


if __name__ == "__main__":
    main()
