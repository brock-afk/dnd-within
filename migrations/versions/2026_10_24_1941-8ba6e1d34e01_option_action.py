"""option action

Revision ID: 8ba6e1d34e01
Revises: 22f9ee8d6e67
Create Date: 2026-10-24 19:41:00.000000

What using an option takes (action, bonus_action, reaction), like a feature's, so the Play
sheet's Features section can group picked options (Pact of the Blade: a Bonus Action).

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8ba6e1d34e01"
down_revision: str | Sequence[str] | None = "22f9ee8d6e67"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("choice_options", sa.Column("action", sa.String(length=20), nullable=True))
    op.create_check_constraint(
        op.f("ck_choice_options_action_values"),
        "choice_options",
        "action IN ('action', 'bonus_action', 'reaction')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("ck_choice_options_action_values"), "choice_options", type_="check")
    op.drop_column("choice_options", "action")
