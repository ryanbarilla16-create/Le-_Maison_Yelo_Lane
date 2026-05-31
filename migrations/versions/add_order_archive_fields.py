"""Add archive fields to Order

Revision ID: add_order_archive_fields
Revises: add_reservation_code
Create Date: 2026-05-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_order_archive_fields'
down_revision = 'add_reservation_code'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "")

    if dialect in ("postgresql", "postgres"):
        op.execute('ALTER TABLE "order" ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE')
        op.execute('ALTER TABLE "order" ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP')
        op.execute('CREATE INDEX IF NOT EXISTS ix_order_is_archived ON "order" (is_archived)')
        op.execute('CREATE INDEX IF NOT EXISTS ix_order_archived_at ON "order" (archived_at)')
        return

    op.add_column('order', sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('order', sa.Column('archived_at', sa.DateTime(), nullable=True))
    op.create_index(op.f('ix_order_archived_at'), 'order', ['archived_at'], unique=False)
    op.create_index(op.f('ix_order_is_archived'), 'order', ['is_archived'], unique=False)


def downgrade():
    bind = op.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "")

    if dialect in ("postgresql", "postgres"):
        op.execute('DROP INDEX IF EXISTS ix_order_is_archived')
        op.execute('DROP INDEX IF EXISTS ix_order_archived_at')
        op.execute('ALTER TABLE "order" DROP COLUMN IF EXISTS archived_at')
        op.execute('ALTER TABLE "order" DROP COLUMN IF EXISTS is_archived')
        return

    op.drop_index(op.f('ix_order_is_archived'), table_name='order')
    op.drop_index(op.f('ix_order_archived_at'), table_name='order')
    op.drop_column('order', 'archived_at')
    op.drop_column('order', 'is_archived')
