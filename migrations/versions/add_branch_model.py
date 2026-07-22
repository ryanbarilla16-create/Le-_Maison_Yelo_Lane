"""add branch model

Revision ID: add_branch_model
Revises: ebec3c859fdc
Create Date: 2026-07-14

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_branch_model'
down_revision = 'ebec3c859fdc'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'branch',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('address', sa.String(length=255), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('province', sa.String(length=100), nullable=True),
        sa.Column('phone', sa.String(length=30), nullable=True),
        sa.Column('email', sa.String(length=120), nullable=True),
        sa.Column('is_main', sa.Boolean(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )


def downgrade():
    op.drop_table('branch')
