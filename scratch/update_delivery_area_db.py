from app import app
from models import db
from sqlalchemy import text

with app.app_context():
    try:
        db.session.execute(text("ALTER TABLE delivery_area ADD COLUMN branch VARCHAR(50) DEFAULT 'Pagsanjan'"))
        db.session.commit()
        print("Successfully added 'branch' column to 'delivery_area' table.")
    except Exception as e:
        print(f"Error or column already exists: {e}")
