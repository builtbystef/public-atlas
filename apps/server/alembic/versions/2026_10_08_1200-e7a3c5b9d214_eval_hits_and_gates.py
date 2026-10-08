"""eval hits and gates

An eval score keeps its hits beside its misses and false positives, and every entry names its
kind, so a `wrong` entry (in both lists) can be told from a plain miss. An eval run keeps the
gates it was judged on. Entries recorded before this get their kind from the lists they are in;
their hits and the run's gates were never kept and stay null.

Revision ID: e7a3c5b9d214
Revises: c4f9a2d7b815
Create Date: 2026-10-08 12:00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "e7a3c5b9d214"
down_revision: str | Sequence[str] | None = "c4f9a2d7b815"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Both expressions read the row as it was, so each list is checked against the other's entries
# before either gains a kind.
ADD_KINDS = """
UPDATE eval_scores SET
    misses = (
        SELECT coalesce(jsonb_agg(
            entry || jsonb_build_object(
                'kind', CASE WHEN false_positives @> jsonb_build_array(entry)
                    THEN 'wrong' ELSE 'miss' END
            )
            ORDER BY position
        ), '[]'::jsonb)
        FROM jsonb_array_elements(misses) WITH ORDINALITY AS t(entry, position)
    ),
    false_positives = (
        SELECT coalesce(jsonb_agg(
            entry || jsonb_build_object(
                'kind', CASE WHEN misses @> jsonb_build_array(entry)
                    THEN 'wrong' ELSE 'false_positive' END
            )
            ORDER BY position
        ), '[]'::jsonb)
        FROM jsonb_array_elements(false_positives) WITH ORDINALITY AS t(entry, position)
    )
"""

DROP_KINDS = """
UPDATE eval_scores SET
    misses = (
        SELECT coalesce(jsonb_agg(entry - 'kind' ORDER BY position), '[]'::jsonb)
        FROM jsonb_array_elements(misses) WITH ORDINALITY AS t(entry, position)
    ),
    false_positives = (
        SELECT coalesce(jsonb_agg(entry - 'kind' ORDER BY position), '[]'::jsonb)
        FROM jsonb_array_elements(false_positives) WITH ORDINALITY AS t(entry, position)
    )
"""


def upgrade() -> None:
    op.add_column("eval_runs", sa.Column("gates", JSONB(), nullable=True))
    op.add_column("eval_scores", sa.Column("hits", JSONB(), nullable=True))
    op.execute(ADD_KINDS)


def downgrade() -> None:
    op.execute(DROP_KINDS)
    op.drop_column("eval_scores", "hits")
    op.drop_column("eval_runs", "gates")
