"""spell school check

Revision ID: 9c83351dc309
Revises: 5fe220f4f2d9
Create Date: 2026-11-08 15:06:51.585828

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c83351dc309"
down_revision: str | Sequence[str] | None = "5fe220f4f2d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        op.f("ck_spells_school_values"),
        "spells",
        "school IN ('abjuration', 'conjuration', 'divination', 'enchantment', "
        "'evocation', 'illusion', 'necromancy', 'transmutation')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("ck_spells_school_values"), "spells", type_="check")
