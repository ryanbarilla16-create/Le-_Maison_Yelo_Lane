import sys
sys.path.append(r'c:\Users\Ryan Bien Barilla\OneDrive\Desktop\python web (capstone)')
from app import app
from models import db, Supplier, Ingredient

with app.app_context():
    suppliers = Supplier.query.all()
    print("=== SUPPLIER INGREDIENTS STATUS ===")
    for s in suppliers:
        ingredients = Ingredient.query.filter_by(supplier_id=s.id).all()
        print(f"Supplier: '{s.name}' | Category: '{s.category}' | Ingredients Linked: {len(ingredients)}")
        for ing in ingredients:
            print(f"  - {ing.name} ({ing.unit})")
    
    print("\n=== UNLINKED INGREDIENTS ===")
    unlinked = Ingredient.query.filter_by(supplier_id=None).all()
    print(f"Total unlinked ingredients: {len(unlinked)}")
    for ing in unlinked:
        print(f"  - {ing.name} (Category: {ing.category})")
