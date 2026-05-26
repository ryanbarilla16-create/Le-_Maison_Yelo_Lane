"""add table_number to order

Revision ID: add_table_number
Revises: 
Create Date: 2024-05-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_table_number'
down_revision = 'ebec3c859fdc'
branch_labels = None
depends_on = None


def upgrade():
    # Add table_number column to order table
    op.add_column('order', sa.Column('table_number', sa.Integer(), nullable=True))
    op.add_column('order', sa.Column('table_status', sa.String(20), nullable=True, server_default='AVAILABLE'))


def downgrade():
    # Remove table_number column from order table
    op.drop_column('order', 'table_status')
    op.drop_column('order', 'table_number')
