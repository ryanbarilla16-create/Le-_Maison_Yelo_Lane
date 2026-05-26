import sys
sys.path.append(r'c:\Users\Ryan Bien Barilla\OneDrive\Desktop\python web (capstone)')
from app import app
from models import db, Ingredient, MenuItemIngredient, MenuItem

with app.app_context():
    # New ingredients created/linked
    target_names = [
        "Espresso Beans (Iced)",
        "Vanilla Ice Cream",
        "Le Maison Secret Sauce",
        "Condensed Milk",
        "Graham Crackers",
        "Frappe Base Powder",
        "Cucumber Extract",
        # Previously unlinked, now linked
        "Sugar",
        "Butter",
        "Evaporated Milk",
        "Tea Leaves",
        "Milk",
        "Dark Chocolate / Cocoa",
        "Fruit Extract / Puree",
        "Onion & Garlic",
        "Tomato",
        "Onion",
        "Shrimp",
        "Cheese",
        "Soy Sauce",
        "Cooking Oil",
        "Garlic",
        "Salt",
        "Breakfast Sausage",
        "Teriyaki Sauce",
        "Vinegar",
        "Black Pepper",
        "Salmon Fillet",
        "Spam / Luncheon Meat",
    ]

    print("=== CHECKING INGREDIENTS STOCK STATE ===")
    for name in target_names:
        ing = Ingredient.query.filter(Ingredient.name.ilike(f"%{name}%")).first()
        if ing:
            # Check which menu items use this ingredient
            usages = db.session.query(MenuItem.name, MenuItem.category).join(
                MenuItemIngredient, MenuItem.id == MenuItemIngredient.menu_item_id
            ).filter(
                MenuItemIngredient.ingredient_id == ing.id,
                MenuItem.is_deleted == False
            ).all()
            usage_str = ", ".join([f"{m.name} ({m.category})" for m in usages[:3]])
            if len(usages) > 3:
                usage_str += f" +{len(usages)-3} more"
            print(f"[{ing.id}] '{ing.name}' | Unit: {ing.unit} | Stock: {ing.stock_qty} | Kitchen: {ing.kitchen_qty} | Used in: {usage_str or 'NONE'}")
        else:
            print(f"  [NOT FOUND] Ingredient '{name}' not in DB")
