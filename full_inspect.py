from app import app
from sqlalchemy import inspect
from models import db

def full_inspect():
    with app.app_context():
        inspector = inspect(db.engine)
        schemas = inspector.get_schema_names()
        print(f"Schemas: {schemas}")
        for schema in schemas:
            if schema in ['public', 'main']:
                tables = inspector.get_table_names(schema=schema)
                print(f"Tables in {schema}: {tables}")
                for table in tables:
                    columns = [c['name'] for c in inspector.get_columns(table, schema=schema)]
                    if 'order' in table.lower():
                        print(f"Columns in {schema}.{table}: {columns}")

if __name__ == "__main__":
    full_inspect()
