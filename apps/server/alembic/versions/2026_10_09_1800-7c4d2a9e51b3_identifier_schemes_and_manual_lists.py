"""identifier schemes and manual lists

`identifiers.scheme` gains the United States' schemes (`fips`, `gnis`, `census_gid`, `nces`,
`ipeds`). `official_lists` gains `retrieval` (`fetched` or `manual`), copied from the list
file, so the database can say which rows rest on hand-collected files; every row so far was
fetched. The lists package became a tree by country and region, and a list's name its path
under it, so Ontario's rows are renamed from `ontario_places/…` to `canada/ontario/places/…`:
the loader looks a list's rows up by this prefix, and a rerun after the rename changes
nothing.

Revision ID: 7c4d2a9e51b3
Revises: e3215d48588b
Create Date: 2026-10-09 18:00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "7c4d2a9e51b3"
down_revision: str | Sequence[str] | None = "e3215d48588b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_SCHEMES = ["statcan_sgc"]
NEW_SCHEMES = ["statcan_sgc", "fips", "gnis", "census_gid", "nces", "ipeds"]
RETRIEVALS = ["fetched", "manual"]
OLD_LIST_PREFIX = "ontario_places/"
NEW_LIST_PREFIX = "canada/ontario/places/"


def _listed(values: list[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _rename_lists(old: str, new: str) -> None:
    op.execute(
        sa.text(
            "UPDATE official_lists SET name = :new || substr(name, :cut) WHERE name LIKE :pattern"
        ).bindparams(new=new, cut=len(old) + 1, pattern=f"{old}%")
    )


def upgrade() -> None:
    op.drop_constraint(op.f("ck_identifiers_scheme"), "identifiers", type_="check")
    op.create_check_constraint(
        op.f("ck_identifiers_scheme"), "identifiers", f"scheme IN ({_listed(NEW_SCHEMES)})"
    )
    op.add_column(
        "official_lists",
        sa.Column("retrieval", sa.Text(), nullable=False, server_default="fetched"),
    )
    op.alter_column("official_lists", "retrieval", server_default=None)
    op.create_check_constraint(
        op.f("ck_official_lists_retrieval"),
        "official_lists",
        f"retrieval IN ({_listed(RETRIEVALS)})",
    )
    _rename_lists(OLD_LIST_PREFIX, NEW_LIST_PREFIX)


def downgrade() -> None:
    _rename_lists(NEW_LIST_PREFIX, OLD_LIST_PREFIX)
    op.drop_constraint(op.f("ck_official_lists_retrieval"), "official_lists", type_="check")
    op.drop_column("official_lists", "retrieval")
    op.drop_constraint(op.f("ck_identifiers_scheme"), "identifiers", type_="check")
    op.create_check_constraint(
        op.f("ck_identifiers_scheme"), "identifiers", f"scheme IN ({_listed(OLD_SCHEMES)})"
    )
