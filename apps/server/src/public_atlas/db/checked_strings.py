"""Enumerations in the database: a text column with a check constraint listing the `StrEnum`'s
values, never a PostgreSQL enum type. Adding a value is a migration that replaces the
constraint, and `tests/integration/db/test_checked_strings.py` compares every constraint with
its enum so the two cannot drift."""

from enum import StrEnum

from sqlalchemy import CheckConstraint, Dialect, Text, TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column

# Keys in `CheckConstraint.info`, for the test.
ENUM_KEY = "enum"
COLUMN_KEY = "column"


class CheckedString[E: StrEnum](TypeDecorator[E]):
    """Stored as text, read back as the enum member."""

    impl = Text
    cache_ok = True

    def __init__(self, enum: type[E]) -> None:
        super().__init__()
        self.enum = enum

    def process_bind_param(self, value: E | str | None, dialect: Dialect) -> str | None:  # noqa: ARG002
        # A plain string is accepted and checked, so a value read from JSON or a request can be
        # written as it is.
        return None if value is None else self.enum(value).value

    def process_result_value(self, value: str | None, dialect: Dialect) -> E | None:  # noqa: ARG002
        return None if value is None else self.enum(value)


def check_sql(enum: type[StrEnum], column: str) -> str:
    """The constraint's expression, as the migration writes it too."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"


def checked_string[E: StrEnum](
    enum: type[E], column: str, *, default: E | None = None, index: bool = False
) -> Mapped[E]:
    """A column named `column` holding one of `enum`'s values, with the constraint named after it
    (`ck_<table>_<column>`). Nullability follows the annotation."""
    constraint = CheckConstraint(
        check_sql(enum, column), name=column, info={ENUM_KEY: enum, COLUMN_KEY: column}
    )
    return mapped_column(column, CheckedString(enum), constraint, default=default, index=index)
