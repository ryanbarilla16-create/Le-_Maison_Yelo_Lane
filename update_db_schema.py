from app import app
from models import db
from sqlalchemy import text

def update_schema():
    with app.app_context():
        try:
            db.session.execute(text("ALTER TABLE \"reservation\" ADD COLUMN cancellation_reason TEXT;"))
            db.session.commit()
            print("Added cancellation_reason to reservation table")
        except Exception as e:
            print(f"Error: {e}")
            db.session.rollback()

if __name__ == "__main__":
    update_schema()
