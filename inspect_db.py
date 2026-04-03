from app import app
from models import db
from sqlalchemy import text

def inspect_columns():
    with app.app_context():
        # PostgreSQL syntax to list columns
        query = text("SELECT column_name FROM information_schema.columns WHERE table_name = 'order';")
        result = db.session.execute(query).fetchall()
        print("Columns in 'order' table:")
        for row in result:
            print(f"- {row[0]}")

if __name__ == "__main__":
    inspect_columns()
