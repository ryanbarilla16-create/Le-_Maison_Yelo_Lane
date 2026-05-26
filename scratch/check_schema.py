from app import app
from models import db
from sqlalchemy import inspect

with app.app_context():
    inspector = inspect(db.engine)
    columns = [c['name'] for c in inspector.get_columns('notification')]
    print(f'Columns: {columns}')
