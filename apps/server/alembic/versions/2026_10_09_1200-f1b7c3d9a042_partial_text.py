"""partial text

A file is parsed as the agent reads it: the first range of pages first, the next when the
agent asks for a chunk past what is parsed. A snapshot's text can therefore be `partial`, and
the row says how many pages of the document the stored text holds.

Revision ID: f1b7c3d9a042
Revises: e7a3c5b9d214
Create Date: 2026-10-09 12:00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "f1b7c3d9a042"
down_revision: str | Sequence[str] | None = "e7a3c5b9d214"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = "text_status IN ('ready', 'parsing', 'failed')"
AFTER = "text_status IN ('ready', 'parsing', 'partial', 'failed')"


def upgrade() -> None:
    op.add_column("snapshots", sa.Column("parsed_pages", sa.Integer(), nullable=True))
    op.execute("UPDATE snapshots SET parsed_pages = page_count WHERE text_status = 'ready'")
    op.drop_constraint(op.f("ck_snapshots_text_status"), "snapshots", type_="check")
    op.create_check_constraint(op.f("ck_snapshots_text_status"), "snapshots", AFTER)


def downgrade() -> None:
    # A partial text reads as a whole one to the code before this; its pages are the parsed ones.
    op.execute(
        "UPDATE snapshots SET text_status = 'ready', page_count = parsed_pages"
        " WHERE text_status = 'partial'"
    )
    op.drop_constraint(op.f("ck_snapshots_text_status"), "snapshots", type_="check")
    op.create_check_constraint(op.f("ck_snapshots_text_status"), "snapshots", BEFORE)
    op.drop_column("snapshots", "parsed_pages")
