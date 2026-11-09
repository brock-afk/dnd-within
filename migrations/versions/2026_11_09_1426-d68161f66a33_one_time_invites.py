"""one-time invites

Revision ID: d68161f66a33
Revises: 9c83351dc309
Create Date: 2026-11-09 14:26:13.648003

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d68161f66a33"
down_revision: str | Sequence[str] | None = "9c83351dc309"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("note", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("used_by_id", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "used_at IS NULL OR revoked_at IS NULL", name=op.f("ck_invites_used_or_revoked")
        ),
        sa.ForeignKeyConstraint(
            ["used_by_id"],
            ["users.id"],
            name=op.f("fk_invites_used_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invites")),
        sa.UniqueConstraint("code_hash", name=op.f("uq_invites_code_hash")),
        sa.UniqueConstraint("used_by_id", name=op.f("uq_invites_used_by_id")),
    )
    op.add_column(
        "users", sa.Column("is_admin", sa.Boolean(), server_default=sa.text("0"), nullable=False)
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
    op.drop_table("invites")
