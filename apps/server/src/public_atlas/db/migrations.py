"""Alembic from inside the process: its configuration, the head revision, and whether a
database is at it. The migrations themselves live in `alembic/`."""

from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection

SERVER_ROOT = Path(__file__).resolve().parents[3]


class NotMigratedError(RuntimeError):
    """A database is not at the latest migration."""


def alembic_config() -> Config:
    """The settings are in pyproject.toml; alembic.ini holds only a logging configuration, which
    would replace this process's loggers, so it is left out."""
    return Config(toml_file=SERVER_ROOT / "pyproject.toml")


def head_revision() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    if head is None:
        raise RuntimeError("no migrations found under alembic/versions")
    return head


def current_revisions(connection: Connection) -> tuple[str, ...]:
    """The revisions the database is stamped with: empty when it was never migrated."""
    return MigrationContext.configure(connection).get_current_heads()


def check_head(connection: Connection) -> None:
    """Raise `NotMigratedError` unless the database is at the latest migration."""
    current = current_revisions(connection)
    head = head_revision()
    if current != (head,):
        at = ", ".join(current) or "no revision"
        raise NotMigratedError(
            f"the database {connection.engine.url.database!r} is at {at}, not at the latest "
            f"migration {head}: run `alembic upgrade head` (vp run db:migrate) first"
        )


def stamp_head(connection: Connection) -> None:
    """Mark the database as at the latest migration without running any: for a database whose
    tables were created from the models, as the tests do."""
    MigrationContext.configure(connection).stamp(
        ScriptDirectory.from_config(alembic_config()), "head"
    )
