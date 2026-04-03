from app import app
from models import db, MenuItem
with app.app_context():
    try:
        count = MenuItem.query.count()
        print(f"Connection successful. MenuItem count: {count}")
    except Exception as e:
        print(f"Connection failed: {e}")
