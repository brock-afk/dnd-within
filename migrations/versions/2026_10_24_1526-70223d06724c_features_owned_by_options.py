"""features owned by options

Revision ID: 70223d06724c
Revises: e1d569bf369f
Create Date: 2026-10-24 15:26:50.072048

A choice option can own features (a Fiendish Legacy's spells), which apply while it's picked.
Downgrading fails while such features exist: the old one_source check doesn't allow them.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "70223d06724c"
down_revision: str | Sequence[str] | None = "e1d569bf369f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNERS = "(class_id IS NOT NULL) + (species_id IS NOT NULL) + (subclass_id IS NOT NULL) + (background_id IS NOT NULL) + (feat_id IS NOT NULL) + (item_id IS NOT NULL)"  # noqa: E501


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("features", sa.Column("option_id", sa.Integer(), nullable=True))
    op.create_unique_constraint(
        op.f("uq_features_option_id_slug"), "features", ["option_id", "slug"]
    )
    op.create_foreign_key(
        op.f("fk_features_option_id_choice_options"),
        "features",
        "choice_options",
        ["option_id"],
        ["id"],
    )
    op.drop_constraint(op.f("ck_features_one_source"), "features", type_="check")
    op.create_check_constraint(
        op.f("ck_features_one_source"), "features", f"{OWNERS} + (option_id IS NOT NULL) = 1"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # MySQL won't drop a column a check constraint uses.
    op.drop_constraint(op.f("ck_features_one_source"), "features", type_="check")
    op.drop_constraint(op.f("fk_features_option_id_choice_options"), "features", type_="foreignkey")
    op.drop_constraint(op.f("uq_features_option_id_slug"), "features", type_="unique")
    op.drop_column("features", "option_id")
    op.create_check_constraint(op.f("ck_features_one_source"), "features", f"{OWNERS} = 1")
