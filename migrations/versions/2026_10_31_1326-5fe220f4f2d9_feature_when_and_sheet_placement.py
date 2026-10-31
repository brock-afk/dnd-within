"""feature when and sheet placement

Revision ID: 5fe220f4f2d9
Revises: 8ba6e1d34e01
Create Date: 2026-10-31 13:26:00.000000

Where a feature or option shows on the Play sheet: a triggered feature's timing (`when`, for
the Actions section's Triggered group), and a passive one's row of Attributes (`sheet`).

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5fe220f4f2d9"
down_revision: str | Sequence[str] | None = "8ba6e1d34e01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHEET_VALUES = "sheet IN ('senses', 'saves', 'speed', 'resistances', 'traits')"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("features", sa.Column("when", sa.String(length=120), nullable=True))
    for table in ("features", "choice_options"):
        op.add_column(table, sa.Column("sheet", sa.String(length=20), nullable=True))
        op.create_check_constraint(op.f(f"ck_{table}_sheet_values"), table, SHEET_VALUES)


def downgrade() -> None:
    """Downgrade schema."""
    for table in ("features", "choice_options"):
        op.drop_constraint(op.f(f"ck_{table}_sheet_values"), table, type_="check")
        op.drop_column(table, "sheet")
    op.drop_column("features", "when")
