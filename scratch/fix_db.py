from app import app, db
from sqlalchemy import text

def fix_db():
    with app.app_context():
        print("Starting DB fix...")
        try:
            # Using raw SQL to add columns if they don't exist
            # Note: PostgreSQL syntax for ADD COLUMN IF NOT EXISTS is available in 9.6+
            db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS age INTEGER"))
            db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS gender VARCHAR(20)"))
            db.session.commit()
            print("--- Database schema updated successfully: Added 'age' and 'gender' to 'user' table. ---")
        except Exception as e:
            db.session.rollback()
            print(f"--- Error updating database schema: {e} ---")

if __name__ == "__main__":
    fix_db()
