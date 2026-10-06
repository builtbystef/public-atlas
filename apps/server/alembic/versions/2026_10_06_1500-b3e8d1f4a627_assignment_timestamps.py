"""assignment timestamps

When an assignment was created, when its first session started and when it finished: the purge
jobs count from the last.

Revision ID: b3e8d1f4a627
Revises: 9d2f7b3a1c45
Create Date: 2026-10-06 15:00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "b3e8d1f4a627"
down_revision: str | Sequence[str] | None = "9d2f7b3a1c45"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assignments",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            # Rows made before this migration get the time it ran; the model sets new rows'.
            server_default=sa.func.now(),
        ),
    )
    op.alter_column("assignments", "created_at", server_default=None)
    op.add_column("assignments", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "assignments", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("assignments", "finished_at")
    op.drop_column("assignments", "started_at")
    op.drop_column("assignments", "created_at")
