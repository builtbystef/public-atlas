"""webpages domain nullable

A page is captured when the browser lands on it, which on a site a search returned is before
any domain row exists; the domain is attached once it does.

Revision ID: 9d2f7b3a1c45
Revises: 7c4e2a9b1d08
Create Date: 2026-10-06 14:00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "9d2f7b3a1c45"
down_revision: str | Sequence[str] | None = "7c4e2a9b1d08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("webpages", "domain_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    op.alter_column("webpages", "domain_id", existing_type=sa.Uuid(), nullable=False)
