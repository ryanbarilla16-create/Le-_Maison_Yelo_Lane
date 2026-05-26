import sys
sys.path.append(r'c:\Users\Ryan Bien Barilla\OneDrive\Desktop\python web (capstone)')
from app import app
from models import db, Ingredient, MenuItemIngredient, MenuItem

def fill_stocks_and_link_recipes():
    print("=" * 70)
    print("FILLING STOCKS + LINKING MISSING RECIPES TO UNUSED INGREDIENTS")
    print("=" * 70)

    with app.app_context():

        # ── STEP 1: Fix stock levels for any ingredient with low/zero stock ──────
        # (stock_qty = warehouse stock, kitchen_qty = kitchen pantry)
        print("\n[1/3] Setting warehouse stock + kitchen stock for all relevant ingredients...")

        # name_match -> (stock_qty, kitchen_qty, unit, category_label)
        # All sensible real-world values for a restaurant
        stock_targets = {
            # New ingredients
            "Espresso Beans (Iced)":  (50.0,  10.0),
            "Vanilla Ice Cream":       (100.0, 20.0),
            "Le Maison Secret Sauce":  (50.0,  10.0),
            "Condensed Milk":          (100.0, 25.0),
            "Graham Crackers":         (10000.0, 2000.0),
            "Frappe Base Powder":      (30.0,  5.0),
            "Cucumber Extract":        (40.0,  8.0),

            # Previously unlinked - ensure they have proper stock
            "Sugar":               (5000.0, 1000.0),
            "Butter":              (5000.0, 1000.0),
            "Evaporated Milk":     (200.0,  50.0),
            "Tea Leaves":          (30.0,   8.0),
            "Milk":                (100.0,  20.0),
            "Dark Chocolate / Cocoa": (20.0, 5.0),
            "Fruit Extract / Puree":  (50.0, 10.0),
            "Onion & Garlic":      (30.0,   8.0),
            "Tomato":              (30.0,   8.0),
            "Shrimp":              (20.0,   5.0),
            "Cheese":              (20.0,   5.0),
            "Soy Sauce":           (20.0,   5.0),
            "Cooking Oil":         (20.0,   5.0),
            "Garlic":              (5000.0, 1000.0),
            "Salt":                (5000.0, 1000.0),
            "Black Pepper":        (2000.0, 500.0),
            "Breakfast Sausage":   (200.0,  50.0),
            "Teriyaki Sauce":      (20.0,   5.0),
            "Vinegar":             (20.0,   5.0),
            "Salmon Fillet":       (20.0,   5.0),
            "Spam / Luncheon Meat": (100.0, 20.0),
        }

        updated = 0
        for name, (stock_qty, kitchen_qty) in stock_targets.items():
            ing = Ingredient.query.filter(Ingredient.name.ilike(f"%{name}%")).first()
            if ing:
                ing.stock_qty = stock_qty
                ing.kitchen_qty = kitchen_qty
                print(f"  [STOCK SET] '{ing.name}' -> Warehouse: {stock_qty} {ing.unit} | Kitchen: {kitchen_qty} {ing.unit}")
                updated += 1
            else:
                print(f"  [NOT FOUND] '{name}' not in DB")

        db.session.commit()
        print(f"\n  Total ingredients updated: {updated}")

        # ── STEP 2: Link missing recipes to unused ingredients ──────────────────
        print("\n[2/3] Linking unused ingredients to appropriate menu items recipes...")

        def add_recipe_link(menu_item_name, ingredient_name, qty, unit_check=None):
            item = MenuItem.query.filter(MenuItem.name.ilike(f"%{menu_item_name}%"), MenuItem.is_deleted == False).first()
            if not item:
                print(f"  [SKIP] Menu item '{menu_item_name}' not found.")
                return

            ing = Ingredient.query.filter(Ingredient.name.ilike(f"%{ingredient_name}%")).first()
            if not ing:
                print(f"  [SKIP] Ingredient '{ingredient_name}' not found.")
                return

            exists = MenuItemIngredient.query.filter_by(menu_item_id=item.id, ingredient_id=ing.id).first()
            if not exists:
                db.session.add(MenuItemIngredient(
                    menu_item_id=item.id,
                    ingredient_id=ing.id,
                    quantity_needed=qty
                ))
                print(f"  [LINKED] '{ingredient_name}' -> '{item.name}' ({item.category}) | Qty: {qty} {ing.unit}")
            else:
                print(f"  [EXISTS] '{ingredient_name}' already in recipe of '{item.name}'")

        def add_recipe_to_all_in_category(category, ingredient_name, qty):
            ing = Ingredient.query.filter(Ingredient.name.ilike(f"%{ingredient_name}%")).first()
            if not ing:
                print(f"  [SKIP] Ingredient '{ingredient_name}' not found.")
                return

            items = MenuItem.query.filter_by(category=category, is_deleted=False).all()
            for item in items:
                exists = MenuItemIngredient.query.filter_by(menu_item_id=item.id, ingredient_id=ing.id).first()
                if not exists:
                    db.session.add(MenuItemIngredient(
                        menu_item_id=item.id,
                        ingredient_id=ing.id,
                        quantity_needed=qty
                    ))
                    print(f"  [LINKED] '{ing.name}' -> '{item.name}' ({category}) | Qty: {qty} {ing.unit}")

        # Graham Crackers → Desserts that are no-bake/cheesecake style
        add_recipe_link("No Bake Blueberry Cheesecake", "Graham Crackers", 30.0)
        add_recipe_link("No Bake Chocolate Cheesecake", "Graham Crackers", 30.0)
        add_recipe_link("Baked Blueberry Cheesecake",   "Graham Crackers", 30.0)
        add_recipe_link("New York Style Cheesecake",    "Graham Crackers", 30.0)
        add_recipe_link("Mango Float",                  "Graham Crackers", 30.0)

        # Soy Sauce → All Day Breakfast (tapsilog style dishes)
        add_recipe_link("Beef Sirloin",      "Soy Sauce", 0.05)
        add_recipe_link("Beef Teriyaki",     "Soy Sauce", 0.05)
        add_recipe_link("Chicken Teriyaki",  "Soy Sauce", 0.05)
        add_recipe_link("Salmon Teriyaki",   "Soy Sauce", 0.05)
        add_recipe_link("Beef Salpicao",     "Soy Sauce", 0.05)
        add_recipe_link("Bangus Belly",      "Soy Sauce", 0.05)
        add_recipe_link("Lucban Longganisa", "Soy Sauce", 0.03)

        # Cooking Oil → All Day Breakfast & Rice Plates
        add_recipe_link("Lechon Kawali",        "Cooking Oil", 0.05)
        add_recipe_link("Grilled Salmon Steak", "Cooking Oil", 0.03)
        add_recipe_link("Fish & Chips",         "Cooking Oil", 0.05)
        add_recipe_link("French Fries",         "Cooking Oil", 0.05)
        add_recipe_link("Flavored Fries",       "Cooking Oil", 0.05)
        add_recipe_link("Mojos",                "Cooking Oil", 0.05)

        # Garlic → Rice Plates and Starters
        add_recipe_link("Lechon Kawali",    "Garlic", 5.0)
        add_recipe_link("Beef Salpicao",    "Garlic", 5.0)
        add_recipe_link("Garlic Shrimp",    "Garlic", 5.0)
        add_recipe_link("Grilled Herb Chicken", "Garlic", 5.0)

        # Salt → All categories
        add_recipe_link("Grilled Herb Chicken", "Salt", 2.0)
        add_recipe_link("Grilled Salmon Steak", "Salt", 2.0)
        add_recipe_link("Angus Beef Pepper Rice", "Salt", 2.0)

        # Black Pepper → Steak & Rice Plates
        add_recipe_link("Black Pepper Pork Steak",  "Black Pepper", 2.0)
        add_recipe_link("Angus Beef Pepper Rice",   "Black Pepper", 2.0)
        add_recipe_link("Beef Salpicao",            "Black Pepper", 2.0)
        add_recipe_link("Grilled Porterhouse Steak", "Black Pepper", 2.0)

        # Teriyaki Sauce → Teriyaki dishes
        add_recipe_link("Beef Teriyaki Doria",      "Teriyaki Sauce", 0.05)
        add_recipe_link("Chicken Teriyaki Doria",   "Teriyaki Sauce", 0.05)
        add_recipe_link("Salmon Teriyaki Doria",    "Teriyaki Sauce", 0.05)

        # Vinegar → Lechon Kawali
        add_recipe_link("Lechon Kawali", "Vinegar", 0.03)

        # Salmon Fillet → Salmon dishes
        add_recipe_link("Grilled Salmon Steak",   "Salmon Fillet", 0.25)
        add_recipe_link("Salmon Teriyaki Doria",  "Salmon Fillet", 0.20)
        add_recipe_link("Brown Butter Fish Fillet", "Salmon Fillet", 0.25)

        # Breakfast Sausage → Big Breakfast, Breakfast Sausage item
        add_recipe_link("Big Breakfast",        "Breakfast Sausage", 2.0)
        add_recipe_link("Breakfast Sausage",    "Breakfast Sausage", 3.0)

        # Spam / Luncheon Meat → Lucban Longganisa nearby / breakfast
        add_recipe_link("hotdog",               "Spam / Luncheon Meat", 1.0)

        # Evaporated Milk → Champorado & some desserts
        add_recipe_link("Dark Chocolate Champorado", "Evaporated Milk", 0.10)
        add_recipe_link("Mango Bingsu",              "Evaporated Milk", 0.10)
        add_recipe_link("Mango Bingsu Petite",       "Evaporated Milk", 0.10)

        # Dark Chocolate / Cocoa → Chocolate-heavy desserts and drinks
        add_recipe_link("Dark Chocolate Champorado",  "Dark Chocolate / Cocoa", 0.05)
        add_recipe_link("Better Than Ex Chocolate",   "Dark Chocolate / Cocoa", 0.05)
        add_recipe_link("Classic Hot Chocolate",      "Dark Chocolate / Cocoa", 0.05)
        add_recipe_link("Chocolate-Dipped Potato Chips", "Dark Chocolate / Cocoa", 0.05)

        db.session.commit()

        # ── STEP 3: Final report ────────────────────────────────────────────────
        print("\n[3/3] Final report of all supplier ingredient counts...")

        from models import Supplier
        suppliers = Supplier.query.order_by(Supplier.name).all()
        print(f"\n{'Supplier':<45} {'Category':<30} {'# Ingredients'}")
        print("-" * 90)
        for sup in suppliers:
            count = Ingredient.query.filter_by(supplier_id=sup.id).count()
            print(f"{sup.name:<45} {sup.category:<30} {count}")

        print("\n" + "=" * 70)
        print("[SUCCESS] Stocks filled + recipes linked correctly!")
        print("=" * 70)


if __name__ == '__main__':
    try:
        fill_stocks_and_link_recipes()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
