"""add_is_bestseller_to_menuitem

Revision ID: 139843fdfcdf
Revises: 8ec59b4444e5
Create Date: 2026-07-17 13:32:49.567227

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '139843fdfcdf'
down_revision = '8ec59b4444e5'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add column to menu_item and indexes
    with op.batch_alter_table('menu_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_bestseller', sa.Boolean(), nullable=True))
        batch_op.create_index(batch_op.f('ix_menu_item_branch'), ['branch'], unique=False)
        batch_op.create_index(batch_op.f('ix_menu_item_is_bestseller'), ['is_bestseller'], unique=False)

    # Add other indexes for standard optimization (safe and clean)
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_log_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_log_target_type'), ['target_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_log_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('ingredient', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ingredient_branch'), ['branch'], unique=False)
        batch_op.create_index(batch_op.f('ix_ingredient_category'), ['category'], unique=False)

    with op.batch_alter_table('notification', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notification_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('order', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_order_branch'), ['branch'], unique=False)
        batch_op.create_index(batch_op.f('ix_order_payment_status'), ['payment_status'], unique=False)
        batch_op.create_index(batch_op.f('ix_order_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('reservation', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reservation_branch'), ['branch'], unique=False)
        batch_op.create_index(batch_op.f('ix_reservation_date'), ['date'], unique=False)
        batch_op.create_index(batch_op.f('ix_reservation_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('review', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_review_order_id'), ['order_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_review_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_branch'), ['branch'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_status'), ['status'], unique=False)

    # 2. RUN DATA MIGRATION LOGIC
    connection = op.get_bind()
    
    # Initialize all is_bestseller to False
    connection.execute(sa.text("UPDATE menu_item SET is_bestseller = FALSE"))

    # Migrate non-duplicate best-seller items
    connection.execute(sa.text(
        "UPDATE menu_item SET category = 'Rice Plates', is_bestseller = TRUE "
        "WHERE name = 'Bacon Rice' AND category = 'Best Sellers'"
    ))
    connection.execute(sa.text(
        "UPDATE menu_item SET category = 'Pasta & Salads', is_bestseller = TRUE "
        "WHERE name = 'Italian Carbonara' AND category = 'Best Sellers'"
    ))

    # Identify and merge duplicate items under 'Best Sellers' and a real category
    duplicates = connection.execute(sa.text(
        "SELECT b.name, b.id as best_seller_id, r.id as real_id "
        "FROM menu_item b "
        "JOIN menu_item r ON b.name = r.name "
        "WHERE b.category = 'Best Sellers' AND r.category != 'Best Sellers' "
        "AND b.is_deleted = FALSE AND r.is_deleted = FALSE"
    )).fetchall()

    for row in duplicates:
        name = row[0]
        bs_id = row[1]
        real_id = row[2]
        
        # A. Update order items referencing the Best Sellers version to point to the Real version
        connection.execute(
            sa.text("UPDATE order_item SET menu_item_id = :real_id WHERE menu_item_id = :bs_id"),
            {"real_id": real_id, "bs_id": bs_id}
        )
        
        # B. Set the real version as a best seller
        connection.execute(
            sa.text("UPDATE menu_item SET is_bestseller = TRUE WHERE id = :real_id"),
            {"real_id": real_id}
        )
        
        # C. Delete recipe ingredients of the duplicate Best Sellers item
        connection.execute(
            sa.text("DELETE FROM menu_item_ingredient WHERE menu_item_id = :bs_id"),
            {"bs_id": bs_id}
        )
        
        # D. Delete the duplicate Best Sellers item itself
        connection.execute(
            sa.text("DELETE FROM menu_item WHERE id = :bs_id"),
            {"bs_id": bs_id}
        )

    # Final cleanup of any leftover items in category 'Best Sellers'
    connection.execute(sa.text(
        "DELETE FROM menu_item_ingredient WHERE menu_item_id IN "
        "(SELECT id FROM menu_item WHERE category = 'Best Sellers')"
    ))
    connection.execute(sa.text("DELETE FROM menu_item WHERE category = 'Best Sellers'"))


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_status'))
        batch_op.drop_index(batch_op.f('ix_user_branch'))

    with op.batch_alter_table('review', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_review_user_id'))
        batch_op.drop_index(batch_op.f('ix_review_order_id'))

    with op.batch_alter_table('reservation', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reservation_user_id'))
        batch_op.drop_index(batch_op.f('ix_reservation_date'))
        batch_op.drop_index(batch_op.f('ix_reservation_branch'))

    with op.batch_alter_table('order', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_order_user_id'))
        batch_op.drop_index(batch_op.f('ix_order_payment_status'))
        batch_op.drop_index(batch_op.f('ix_order_branch'))

    with op.batch_alter_table('notification', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notification_user_id'))

    with op.batch_alter_table('menu_item', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_menu_item_is_bestseller'))
        batch_op.drop_index(batch_op.f('ix_menu_item_branch'))
        batch_op.drop_column('is_bestseller')

    with op.batch_alter_table('ingredient', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ingredient_category'))
        batch_op.drop_index(batch_op.f('ix_ingredient_branch'))

    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_log_user_id'))
        batch_op.drop_index(batch_op.f('ix_audit_log_target_type'))
        batch_op.drop_index(batch_op.f('ix_audit_log_created_at'))
