"""mamh identifier scheme

`identifiers.scheme` gains `mamh`, the code géographique of Quebec's Ministère des Affaires
municipales et de l'Habitation, so the six MRCs the census counts no division for can be
regions with a code of their own.

Revision ID: a9f2c17d64e8
Revises: 7c4d2a9e51b3
Create Date: 2026-10-09 23:00:00
"""

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "a9f2c17d64e8"
down_revision: str | Sequence[str] | None = "7c4d2a9e51b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_SCHEMES = ["statcan_sgc", "fips", "gnis", "census_gid", "nces", "ipeds"]
NEW_SCHEMES = ["statcan_sgc", "mamh", "fips", "gnis", "census_gid", "nces", "ipeds"]


def _listed(values: list[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_identifiers_scheme"), "identifiers", type_="check")
    op.create_check_constraint(
        op.f("ck_identifiers_scheme"), "identifiers", f"scheme IN ({_listed(NEW_SCHEMES)})"
    )


def downgrade() -> None:
    op.execute("DELETE FROM identifiers WHERE scheme = 'mamh'")
    op.drop_constraint(op.f("ck_identifiers_scheme"), "identifiers", type_="check")
    op.create_check_constraint(
        op.f("ck_identifiers_scheme"), "identifiers", f"scheme IN ({_listed(OLD_SCHEMES)})"
    )
