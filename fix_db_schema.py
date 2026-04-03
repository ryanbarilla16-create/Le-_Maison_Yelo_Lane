from app import app
from models import db
from sqlalchemy import text

def fix_schema():
    with app.app_context():
        # Add missing columns to 'order' table
        order_columns = [
            ("processed_by_id", "INTEGER"),
            ("prep_start_at", "TIMESTAMP"),
            ("prep_end_at", "TIMESTAMP"),
            ("prep_duration", "INTEGER"),
            ("estimated_cost", "NUMERIC(10, 2) DEFAULT 0")
        ]
        
        for col_name, col_type in order_columns:
            try:
                db.session.execute(text(f"ALTER TABLE \"order\" ADD COLUMN {col_name} {col_type};"))
                db.session.commit()
                print(f"Added {col_name} to 'order' table.")
            except Exception as e:
                db.session.rollback()
                print(f"Skipping {col_name} (it might already exist): {e}")

        # Add missing columns to 'order_item' table
        try:
            db.session.execute(text("ALTER TABLE \"order_item\" ADD COLUMN cost_at_time NUMERIC(10, 2);"))
            db.session.commit()
            print("Added cost_at_time to 'order_item' table.")
        except Exception as e:
            db.session.rollback()
            print(f"Skipping cost_at_time: {e}")

if __name__ == "__main__":
    fix_schema()
