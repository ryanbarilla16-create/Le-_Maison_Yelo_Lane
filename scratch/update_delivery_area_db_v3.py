import os
from flask import Flask
from config import Config
from models import db
from sqlalchemy import text

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    try:
        # Check dialect
        dialect = db.engine.dialect.name
        print(f"Detected dialect: {dialect}")
        
        # Use a safe table name. SQLAlchemy usually uses lowercase.
        # We'll try both delivery_area and DeliveryArea just in case.
        
        sql = "ALTER TABLE delivery_area ADD COLUMN branch VARCHAR(50) DEFAULT 'Pagsanjan'"
        if dialect == 'postgresql':
            # Check if column exists first for Postgres to avoid error
            check_sql = "SELECT column_name FROM information_schema.columns WHERE table_name='delivery_area' AND column_name='branch'"
            res = db.session.execute(text(check_sql)).fetchone()
            if not res:
                db.session.execute(text(sql))
                db.session.commit()
                print("Added 'branch' column to 'delivery_area' (Postgres)")
            else:
                print("'branch' column already exists (Postgres)")
        else:
            # SQLite
            db.session.execute(text(sql))
            db.session.commit()
            print("Added 'branch' column to 'delivery_area' (SQLite)")
            
    except Exception as e:
        print(f"Error: {e}")
