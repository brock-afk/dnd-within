"""choice counts by level and option prerequisites

Revision ID: 22f9ee8d6e67
Revises: 2e2eee94d597
Create Date: 2026-10-24 19:20:00.000000

Choices whose count grows with level (a Warlock's invocations: 1, then 3, then 5) store the
table; options can require a level or a sibling option (Thirsting Blade needs Pact of the
Blade).

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "22f9ee8d6e67"
down_revision: str | Sequence[str] | None = "2e2eee94d597"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "choice_options", sa.Column("requires", sa.JSON(none_as_null=True), nullable=True)
    )
    op.add_column("choices", sa.Column("count_by_level", sa.JSON(none_as_null=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("choices", "count_by_level")
    op.drop_column("choice_options", "requires")
