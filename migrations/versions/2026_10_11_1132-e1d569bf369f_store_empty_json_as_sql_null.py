"""store empty json as sql null

Revision ID: e1d569bf369f
Revises: 7211d4a4522d
Create Date: 2026-10-11 11:32:08.893838

Nullable JSON columns stored Python None as the JSON value null, which `IS NULL` filters
don't match. The models now store SQL NULL (NullableJSON); this converts existing rows.

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1d569bf369f"
down_revision: str | Sequence[str] | None = "7211d4a4522d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NULLABLE_JSON = {
    "features": ["uses", "slot_recovery", "grants"],
    "choice_options": ["damage_reaction", "grants"],
    "classes": ["spellcasting"],
    "items": ["contents", "definition"],
}


def upgrade() -> None:
    """Upgrade schema."""
    for table, columns in NULLABLE_JSON.items():
        for column in columns:
            op.execute(f"UPDATE {table} SET {column} = NULL WHERE {column} = CAST('null' AS JSON)")


def downgrade() -> None:
    """Downgrade schema."""
    # Nothing to undo: SQL NULL and JSON null both load as None.
