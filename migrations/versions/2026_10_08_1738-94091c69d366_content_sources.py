"""content sources

Revision ID: 94091c69d366
Revises: 9b898cb4c947
Create Date: 2026-10-08 17:38:06.886280

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '94091c69d366'
down_revision: Union[str, Sequence[str], None] = '9b898cb4c947'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = ["classes", "skills", "species", "spells"]  # unique on (source_id, slug)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('sources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('owner_user_id', sa.Integer(), nullable=True),
    sa.Column('pack_version', sa.String(length=40), nullable=True),
    sa.Column('pack_checksum', sa.String(length=64), nullable=True),
    sa.Column('imported_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('official', 'third_party', 'homebrew')", name=op.f('ck_sources_kind_values')),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_sources_owner_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sources')),
    sa.UniqueConstraint('slug', name=op.f('uq_sources_slug'))
    )
    # Everything that exists so far came from the 2024 PHB. The content importer fills in the
    # pack version and checksum on its first run (and updates these rows in place by slug).
    op.execute(
        "INSERT INTO sources (slug, name, kind) "
        "VALUES ('phb-2024', 'Player''s Handbook (2024)', 'official')"
    )

    for table in ['features', 'choices', 'choice_options']:
        op.add_column(table, sa.Column('retired_at', sa.DateTime(), nullable=True))

    # source_id: add nullable, backfill with the PHB source, then require it.
    for table in [*TABLES, 'subclasses']:
        op.add_column(table, sa.Column('source_id', sa.Integer(), nullable=True))
        op.add_column(table, sa.Column('retired_at', sa.DateTime(), nullable=True))
        op.execute(f"UPDATE {table} SET source_id = (SELECT id FROM sources WHERE slug = 'phb-2024')")
        op.alter_column(table, 'source_id', existing_type=sa.Integer(), nullable=False)

    # Slugs become unique per source. The new unique key is created before the foreign key,
    # so MySQL uses it as the foreign key's index instead of adding another one.
    for table in TABLES:
        op.drop_index(op.f(f'uq_{table}_slug'), table_name=table)
        op.create_unique_constraint(op.f(f'uq_{table}_source_id_slug'), table, ['source_id', 'slug'])
        op.create_foreign_key(op.f(f'fk_{table}_source_id_sources'), table, 'sources', ['source_id'], ['id'])
    # Subclasses: the new key starts with class_id, so it can replace the old one as the
    # class_id foreign key's index (MySQL won't drop an index a foreign key still needs).
    op.create_unique_constraint(
        op.f('uq_subclasses_class_id_source_id_slug'), 'subclasses', ['class_id', 'source_id', 'slug']
    )
    op.drop_index(op.f('uq_subclasses_class_id_slug'), table_name='subclasses')
    op.create_foreign_key(op.f('fk_subclasses_source_id_sources'), 'subclasses', 'sources', ['source_id'], ['id'])

    # Spells: structured details replace the old display strings. Placeholders here are
    # overwritten by the first content import.
    op.add_column('spells', sa.Column('casting_unit', sa.String(length=20), nullable=True))
    op.add_column('spells', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('spells', sa.Column('details', sa.JSON(), nullable=True))
    op.execute("UPDATE spells SET casting_unit = 'action', details = JSON_OBJECT()")
    op.alter_column('spells', 'casting_unit', existing_type=sa.String(length=20), nullable=False)
    op.alter_column('spells', 'details', existing_type=sa.JSON(), nullable=False)
    for column in ['components', 'duration', 'casting_time', 'range']:
        op.drop_column('spells', column)
    # Autogenerate misses check constraints on existing tables.
    op.create_check_constraint(op.f('ck_spells_level_range'), 'spells', 'level BETWEEN 0 AND 9')
    op.create_check_constraint(
        op.f('ck_spells_casting_unit_values'), 'spells',
        "casting_unit IN ('action', 'bonus_action', 'reaction', 'minute', 'hour')",
    )


def downgrade() -> None:
    """Downgrade schema.

    Lossy for spells: the old display strings can't be rebuilt from scratch here, so they come
    back as placeholders (the previous revision re-synced them from code on startup).
    Fails if two sources share a slug, since slugs become globally unique again.
    """
    op.drop_constraint(op.f('ck_spells_casting_unit_values'), 'spells', type_='check')
    op.drop_constraint(op.f('ck_spells_level_range'), 'spells', type_='check')
    for column, length in [('range', 40), ('casting_time', 40), ('duration', 40), ('components', 20)]:
        op.add_column('spells', sa.Column(column, mysql.VARCHAR(length=length), nullable=False, server_default=''))
    op.drop_column('spells', 'details')
    op.drop_column('spells', 'description')
    op.drop_column('spells', 'casting_unit')

    op.drop_constraint(op.f('fk_subclasses_source_id_sources'), 'subclasses', type_='foreignkey')
    op.create_index(op.f('uq_subclasses_class_id_slug'), 'subclasses', ['class_id', 'slug'], unique=True)
    op.drop_constraint(op.f('uq_subclasses_class_id_source_id_slug'), 'subclasses', type_='unique')
    for table in TABLES:
        op.drop_constraint(op.f(f'fk_{table}_source_id_sources'), table, type_='foreignkey')
        op.drop_constraint(op.f(f'uq_{table}_source_id_slug'), table, type_='unique')
        op.create_index(op.f(f'uq_{table}_slug'), table, ['slug'], unique=True)
    for table in [*TABLES, 'subclasses']:
        op.drop_column(table, 'retired_at')
        op.drop_column(table, 'source_id')
    for table in ['features', 'choices', 'choice_options']:
        op.drop_column(table, 'retired_at')
    op.drop_table('sources')
