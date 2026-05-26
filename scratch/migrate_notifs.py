from app import app
from models import db
from sqlalchemy import text

with app.app_context():
    try:
        # Add 'link' column to 'notification' table if it doesn't exist
        db.session.execute(text("ALTER TABLE notification ADD COLUMN link VARCHAR(500)"))
        db.session.commit()
        print("Successfully added 'link' column to 'notification' table.")
    except Exception as e:
        db.session.rollback()
        print(f"Error adding column: {e}")
