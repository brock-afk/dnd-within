"""ac_effects_minimum_and_long_rest

Revision ID: 2136fff8ca7b
Revises: 4a3db32d0535
Create Date: 2026-10-09 01:42:50.244427

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2136fff8ca7b"
down_revision: str | Sequence[str] | None = "4a3db32d0535"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "character_ac_effects",
        sa.Column("ends_on_long_rest", sa.Boolean(), server_default=sa.text("0"), nullable=False),
    )
    # Allow the "minimum" kind (Barkskin: AC can't be lower than 17).
    op.drop_constraint(
        op.f("ck_character_ac_effects_value_range"), "character_ac_effects", type_="check"
    )
    op.drop_constraint(
        op.f("ck_character_ac_effects_kind_values"), "character_ac_effects", type_="check"
    )
    op.create_check_constraint(
        "kind_values", "character_ac_effects", "kind IN ('base', 'bonus', 'minimum')"
    )
    op.create_check_constraint(
        "value_range",
        "character_ac_effects",
        "(kind = 'bonus' AND value <> 0) OR (kind <> 'bonus' AND value BETWEEN 10 AND 30)",
    )


def downgrade() -> None:
    """Downgrade schema. Minimum effects can't exist under the old checks, so they go."""
    op.execute("DELETE FROM character_ac_effects WHERE kind = 'minimum'")
    op.drop_constraint(
        op.f("ck_character_ac_effects_value_range"), "character_ac_effects", type_="check"
    )
    op.drop_constraint(
        op.f("ck_character_ac_effects_kind_values"), "character_ac_effects", type_="check"
    )
    op.create_check_constraint("kind_values", "character_ac_effects", "kind IN ('base', 'bonus')")
    op.create_check_constraint(
        "value_range",
        "character_ac_effects",
        "(kind = 'base' AND value BETWEEN 10 AND 30) OR (kind = 'bonus' AND value <> 0)",
    )
    op.drop_column("character_ac_effects", "ends_on_long_rest")
