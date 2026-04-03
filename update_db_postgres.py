from app import app, db
from models import Order
from sqlalchemy import text

def update_db():
    with app.app_context():
        # Using raw SQL to add columns to Order table
        try:
            db.session.execute(text("ALTER TABLE \"order\" ADD COLUMN IF NOT EXISTS prep_start_at TIMESTAMP"))
            db.session.execute(text("ALTER TABLE \"order\" ADD COLUMN IF NOT EXISTS prep_end_at TIMESTAMP"))
            db.session.commit()
            print("Successfully added prep_start_at and prep_end_at to Order table.")
        except Exception as e:
            db.session.rollback()
            print(f"Error updating Order table: {e}")

if __name__ == "__main__":
    update_db()
