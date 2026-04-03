import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

db_url = os.environ.get('NEON_DATABASE_URL') or os.environ.get('SQLALCHEMY_DATABASE_URI')

if not db_url:
    print("Database URL not found in .env")
    exit(1)

# Ensure the URL is in a format SQLAlchemy likes
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(db_url)

with engine.connect() as conn:
    try:
        print("Checking if column 'table_number' exists in 'reservation'...")
        # Check if table exists
        conn.execute(text("ALTER TABLE reservation ADD COLUMN table_number VARCHAR(20)"))
        # commit happens automatically with with engine.connect() if the DB supports it
        # but in newer SQLAlchemy we need to be careful.
        # Let's use the explicit way:
        from sqlalchemy import text
        conn.execute(text("ALTER TABLE reservation ADD COLUMN IF NOT EXISTS table_number VARCHAR(20)"))
        conn.commit()
        print("Column 'table_number' verified or added successfully.")
    except Exception as e:
        print(f"Error: {e}")
