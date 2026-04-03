from app import app
from sqlalchemy import inspect
from models import db

def inspect_db():
    with app.app_context():
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"Tables: {tables}")
        for table in tables:
            columns = [c['name'] for c in inspector.get_columns(table)]
            print(f"Columns in {table}: {columns}")

if __name__ == "__main__":
    inspect_db()
