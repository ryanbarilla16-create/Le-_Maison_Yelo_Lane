import sys
sys.path.append(r'c:\Users\Ryan Bien Barilla\OneDrive\Desktop\python web (capstone)')
from app import app
from models import db, MenuItem

with app.app_context():
    items = MenuItem.query.filter_by(is_deleted=False).all()
    categories = sorted(list(set(item.category for item in items)))
    print("=== ALL MENU CATEGORIES AND ITEMS ===")
    for cat in categories:
        cat_items = MenuItem.query.filter_by(category=cat, is_deleted=False).all()
        print(f"\nCategory: {cat} (Total: {len(cat_items)})")
        for item in cat_items[:10]:
            print(f"  - {item.name} (ID: {item.id})")
        if len(cat_items) > 10:
            print(f"  ... and {len(cat_items) - 10} more")
