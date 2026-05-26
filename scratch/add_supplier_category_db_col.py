import sys
sys.path.append(r'c:\Users\Ryan Bien Barilla\OneDrive\Desktop\python web (capstone)')
from app import app
from models import db
from sqlalchemy import text, inspect

with app.app_context():
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('supplier')]
    
    if 'category' not in columns:
        print("Adding column 'category' to 'supplier' table...")
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE supplier ADD COLUMN category VARCHAR(100)"))
            conn.commit()
        print("Column 'category' added successfully!")
    else:
        print("Column 'category' already exists in 'supplier' table.")
