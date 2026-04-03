from app import app
from models import db
from sqlalchemy import text

def fix_schema():
    with app.app_context():
        # Try adding columns one by one without silencing the error
        try:
            db.session.execute(text("ALTER TABLE \"order\" ADD COLUMN processed_by_id INTEGER;"))
            db.session.commit()
            print("Added processed_by_id")
        except Exception as e:
            print(f"Error processed_by_id: {e}")
            db.session.rollback()

        try:
            db.session.execute(text("ALTER TABLE \"order\" ADD COLUMN prep_start_at TIMESTAMP;"))
            db.session.commit()
            print("Added prep_start_at")
        except Exception as e:
            print(f"Error prep_start_at: {e}")
            db.session.rollback()

        try:
            db.session.execute(text("ALTER TABLE \"order\" ADD COLUMN prep_end_at TIMESTAMP;"))
            db.session.commit()
            print("Added prep_end_at")
        except Exception as e:
            print(f"Error prep_end_at: {e}")
            db.session.rollback()

        try:
            db.session.execute(text("ALTER TABLE \"order\" ADD COLUMN prep_duration INTEGER;"))
            db.session.commit()
            print("Added prep_duration")
        except Exception as e:
            print(f"Error prep_duration: {e}")
            db.session.rollback()

        try:
            db.session.execute(text("ALTER TABLE \"order\" ADD COLUMN estimated_cost NUMERIC(10, 2) DEFAULT 0;"))
            db.session.commit()
            print("Added estimated_cost")
        except Exception as e:
            print(f"Error estimated_cost: {e}")
            db.session.rollback()

        try:
            db.session.execute(text("ALTER TABLE \"order_item\" ADD COLUMN cost_at_time NUMERIC(10, 2);"))
            db.session.commit()
            print("Added cost_at_time")
        except Exception as e:
            print(f"Error cost_at_time: {e}")
            db.session.rollback()

if __name__ == "__main__":
    fix_schema()
