"""merge heads

Revision ID: 8ec59b4444e5
Revises: add_branch_model, d840fb9b7cf8
Create Date: 2026-07-16 12:25:44.772575

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8ec59b4444e5'
down_revision = ('add_branch_model', 'd840fb9b7cf8')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
