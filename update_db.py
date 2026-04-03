from app import app
from models import db
from sqlalchemy import text

if __name__ == "__main__":
    with app.app_context():
        try:
            db.session.execute(text("ALTER TABLE supplier ADD COLUMN catalog_items TEXT;"))
            db.session.commit()
            print("Successfully added catalog_items to supplier table.")
        except Exception as e:
            print("Error modifying database (might already exist):", e)
