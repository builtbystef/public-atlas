"""Every checked string's constraint, in the models and in the migrated database, lists exactly
its enum's values. A value added to an enum without a migration, or a migration that lists the
wrong values, fails here."""

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, text

from public_atlas.db.checked_strings import COLUMN_KEY, ENUM_KEY, CheckedString, check_sql
from public_atlas.db.models import Base

if TYPE_CHECKING:
    from enum import StrEnum

    from sqlalchemy.engine import Connection
    from sqlalchemy.ext.asyncio import AsyncEngine

API_ROOT = Path(__file__).resolve().parents[3]

# PostgreSQL stores `x IN ('a', 'b')` as `(x = ANY (ARRAY['a'::text, 'b'::text]))`, and
# `x IN ('a')` as `(x = 'a'::text)`.
STORED_CHECK = re.compile(r"^CHECK \(\((\w+) = (?:ANY \(ARRAY\[.*\]\)|'[^']*'::text)\)\)$")
STORED_VALUE = re.compile(r"'([^']*)'::text")

CONSTRAINTS_SQL = text(
    "SELECT rel.relname, con.conname, pg_get_constraintdef(con.oid)"
    " FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid"
    " WHERE con.contype = 'c' AND rel.relnamespace = 'public'::regnamespace"
)


def checked_columns() -> list[tuple[str, str, type[StrEnum], str]]:
    """(table, constraint name, enum, column) for every checked string in the models."""
    found = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if not isinstance(column.type, CheckedString):
                continue
            checks = [c for c in column.constraints if isinstance(c, CheckConstraint)]
            assert len(checks) == 1, f"{table.name}.{column.name} has {len(checks)} checks"
            found.append((table.name, str(checks[0].name), checks[0].info[ENUM_KEY], column.name))
    return found


def test_the_models_declare_checked_strings():
    assert len(checked_columns()) > 10


@pytest.mark.parametrize(("table", "name", "enum", "column"), checked_columns())
def test_the_constraint_in_the_models_names_the_column_and_lists_the_enum(
    table, name, enum, column
):
    constraint = next(
        c for c in Base.metadata.tables[table].columns[column].constraints if c.name == name
    )
    assert name == f"ck_{table}_{column}"
    assert constraint.info[COLUMN_KEY] == column
    assert str(constraint.sqltext) == check_sql(enum, column)
    assert isinstance(Base.metadata.tables[table].columns[column].type, CheckedString)
    assert Base.metadata.tables[table].columns[column].type.enum is enum


def _upgrade_and_read(connection: Connection) -> dict[tuple[str, str], str]:
    config = Config(file_=API_ROOT / "alembic.ini", toml_file=API_ROOT / "pyproject.toml")
    config.attributes["connection"] = connection
    command.upgrade(config, "head")
    rows = connection.execute(CONSTRAINTS_SQL).all()
    command.downgrade(config, "base")
    return {(table, name): definition for table, name, definition in rows}


def test_the_migrated_constraints_list_the_enums(engine: AsyncEngine):
    async def run() -> dict[tuple[str, str], str]:
        async with engine.connect() as connection:
            await connection.begin()
            stored = await connection.run_sync(_upgrade_and_read)
            await connection.rollback()
        await engine.dispose()
        return stored

    stored = asyncio.run(run())
    for table, name, enum, column in checked_columns():
        definition = stored.get((table, name))
        assert definition is not None, f"the migration has no constraint {name} on {table}"
        match = STORED_CHECK.match(definition)
        assert match is not None, f"{name} is not a plain list of values: {definition}"
        assert match.group(1) == column
        values = STORED_VALUE.findall(definition)
        assert values == [member.value for member in enum], f"{name} drifted from {enum}"
