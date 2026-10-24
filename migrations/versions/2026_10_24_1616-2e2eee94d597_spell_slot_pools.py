"""spell slot pools

Revision ID: 2e2eee94d597
Revises: 70223d06724c
Create Date: 2026-10-24 16:16:57.026009

Spent spell slots are tracked per pool: Pact Magic slots ("pact") are separate from
Spellcasting slots, since they come back on a short rest and a multiclass character can have
both at the same level. Existing rows are Wizard slots, so they become "spellcasting".
Downgrading drops spent pact slots, which a short rest would restore anyway.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2e2eee94d597"
down_revision: str | Sequence[str] | None = "70223d06724c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "character_spell_slots",
        sa.Column("kind", sa.String(length=20), server_default="spellcasting", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_character_spell_slots_kind_values"),
        "character_spell_slots",
        "kind IN ('spellcasting', 'pact')",
    )
    # One statement: the primary key is also the index the character_id foreign key needs.
    op.execute(
        "ALTER TABLE character_spell_slots DROP PRIMARY KEY,"
        " ADD PRIMARY KEY (character_id, kind, slot_level)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM character_spell_slots WHERE kind = 'pact'")
    op.execute(
        "ALTER TABLE character_spell_slots DROP PRIMARY KEY,"
        " ADD PRIMARY KEY (character_id, slot_level)"
    )
    op.drop_constraint(
        op.f("ck_character_spell_slots_kind_values"), "character_spell_slots", type_="check"
    )
    op.drop_column("character_spell_slots", "kind")
