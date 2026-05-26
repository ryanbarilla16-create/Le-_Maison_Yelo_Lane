import sys
sys.path.append(r'c:\Users\Ryan Bien Barilla\OneDrive\Desktop\python web (capstone)')
from app import app
from models import db, MenuItem, MenuItemIngredient

with app.app_context():
    categories = ["Desserts", "Frappes", "Iced Beverages", "Iced Coffee", "Milkshakes & Smoothies", "Best Sellers"]
    for cat in categories:
        print(f"\n=================== CATEGORY: {cat} ===================")
        items = MenuItem.query.filter_by(category=cat, is_deleted=False).all()
        print(f"Total items found: {len(items)}")
        for item in items[:5]:  # print first 5
            print(f"  Item: '{item.name}' (ID: {item.id}) | Available: {item.is_available} | Out of Stock: {item.is_out_of_stock}")
            recipe = MenuItemIngredient.query.filter_by(menu_item_id=item.id).all()
            print(f"    Recipe ingredients ({len(recipe)}):")
            for r in recipe:
                print(f"      - {r.ingredient.name} | Qty needed: {r.quantity_needed} {r.ingredient.unit}")
