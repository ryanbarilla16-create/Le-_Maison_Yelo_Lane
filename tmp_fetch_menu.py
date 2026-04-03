import os
from dotenv import load_dotenv
from flask import Flask
from models import db, MenuItem
from decimal import Decimal

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('NEON_DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    menu_items = MenuItem.query.all()
    if not menu_items:
        print("No menu items found.")
    else:
        for item in menu_items:
            print(f"ID: {item.id} | CATEGORY: {item.category} | NAME: {item.name} | PRICE: {item.price} | AVAILABLE: {item.is_available}")
