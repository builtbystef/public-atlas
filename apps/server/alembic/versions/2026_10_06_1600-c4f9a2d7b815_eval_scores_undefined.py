"""eval scores undefined

Recall is undefined when a measure has nothing to find, precision when nothing was saved; the
scorer records null rather than a number that means nothing.

Revision ID: c4f9a2d7b815
Revises: b3e8d1f4a627
Create Date: 2026-10-06 16:00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "c4f9a2d7b815"
down_revision: str | Sequence[str] | None = "b3e8d1f4a627"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("eval_scores", "recall", existing_type=sa.Float(), nullable=True)
    op.alter_column("eval_scores", "precision", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE eval_scores SET recall = 0 WHERE recall IS NULL")
    op.execute("UPDATE eval_scores SET precision = 0 WHERE precision IS NULL")
    op.alter_column("eval_scores", "precision", existing_type=sa.Float(), nullable=False)
    op.alter_column("eval_scores", "recall", existing_type=sa.Float(), nullable=False)
