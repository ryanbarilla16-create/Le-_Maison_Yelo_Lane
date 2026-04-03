from app import app
from models import db, Order, MenuItem
import logging

logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

with app.app_context():
    try:
        print("--- Querying MenuItem ---")
        MenuItem.query.limit(1).all()
        print("--- Querying Order ---")
        Order.query.limit(1).all()
    except Exception as e:
        print(f"Error: {e}")
