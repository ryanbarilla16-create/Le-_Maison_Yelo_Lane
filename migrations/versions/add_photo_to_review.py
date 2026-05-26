"""add photo and gallery fields to review

Revision ID: add_photo_to_review
Revises: add_table_number
Create Date: 2024-05-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_photo_to_review'
down_revision = 'add_table_number'
branch_labels = None
depends_on = None


def upgrade():
    # Add photo_url and is_featured_in_gallery columns to review table
    op.add_column('review', sa.Column('photo_url', sa.String(500), nullable=True))
    op.add_column('review', sa.Column('is_featured_in_gallery', sa.Boolean(), nullable=True, server_default='false'))


def downgrade():
    # Remove columns from review table
    op.drop_column('review', 'is_featured_in_gallery')
    op.drop_column('review', 'photo_url')
