import sqlite3
import os
from app import app, db
from sqlalchemy import inspect, text

def sync_database_schema():
    """Automatically synchronizes missing model columns with existing SQLite tables."""
    with app.app_context():
        db.create_all()
        engine = db.engine
        inspector = inspect(engine)
        
        for table_name, table in db.metadata.tables.items():
            if not inspector.has_table(table_name):
                continue
            existing_cols = {col['name'] for col in inspector.get_columns(table_name)}
            for column in table.columns:
                if column.name not in existing_cols:
                    col_type = column.type.compile(engine.dialect)
                    sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {col_type}'
                    print(f"Syncing missing column: {table_name}.{column.name}")
                    try:
                        with engine.connect() as conn:
                            conn.execute(text(sql))
                            conn.commit()
                            print(f"✅ Added {column.name} to {table_name}")
                    except Exception as e:
                        print(f"⚠️ Warning adding {column.name} to {table_name}: {e}")

if __name__ == "__main__":
    sync_database_schema()
