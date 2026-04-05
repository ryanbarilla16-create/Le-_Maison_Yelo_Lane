from app import app
from models import db
from sqlalchemy import inspect
import os

with app.app_context():
    inspector = inspect(db.engine)
    columns = [column['name'] for column in inspector.get_columns('reservation')]
    print(f"Columns in reservation table: {columns}")
    
    if 'cancellation_reason' in columns:
        print("Success: cancellation_reason exists!")
    else:
        print("Missing: cancellation_reason does NOT exist!")
