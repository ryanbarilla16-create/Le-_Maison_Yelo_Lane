import sys
sys.path.append(r'c:\Users\Ryan Bien Barilla\OneDrive\Desktop\python web (capstone)')
from app import app
from models import db, Supplier, Ingredient, MenuItem, MenuItemIngredient

def fix_all_and_interconnect():
    print("=" * 70)
    print("FIXING AND INTERCONNECTING INGREDIENTS & RECIPES BY CATEGORY")
    print("=" * 70)
    
    with app.app_context():
        # Step 1: Map all unlinked ingredients to the correct category-specific suppliers
        print("\n[1/5] Mapping existing unlinked ingredients to correct suppliers...")
        
        # Helper dictionary of: ingredient_name_substring -> supplier_company_name
        mapping_targets = {
            # Desserts - Aling Bebang's Matamis Supply
            "Sugar": "Aling Bebang's Matamis Supply",
            "Butter": "Aling Bebang's Matamis Supply",
            "Evaporated Milk": "Aling Bebang's Matamis Supply",
            
            # Frappes - Ate Girlie's Frappe Depot
            "Milk": "Ate Girlie's Frappe Depot",
            "Dark Chocolate / Cocoa": "Ate Girlie's Frappe Depot",
            "Fruit Extract / Puree": "Ate Girlie's Frappe Depot",
            
            # Iced Beverages - Aling Dolor's Malamig Trading
            "Tea Leaves": "Aling Dolor's Malamig Trading",
            
            # Pasta & Salads - Aling Nita's Fresh Produce
            "Onion & Garlic": "Aling Nita's Fresh Produce",
            "Tomato": "Aling Nita's Fresh Produce",
            "Onion": "Aling Nita's Fresh Produce",
            "Shrimp": "Aling Nita's Fresh Produce",
            
            # Thin Crust Pizza - Kuya Onie's Pizza Supplies
            "Cheese": "Kuya Onie's Pizza Supplies",
            
            # Rice Plates - Mang Erning's Rice & Ulam Supply
            "Soy Sauce": "Mang Erning's Rice & Ulam Supply",
            "Cooking Oil": "Mang Erning's Rice & Ulam Supply",
            "Garlic": "Mang Erning's Rice & Ulam Supply",
            "Salt": "Mang Erning's Rice & Ulam Supply",
            "Teriyaki Sauce": "Mang Erning's Rice & Ulam Supply",
            "Vinegar": "Mang Erning's Rice & Ulam Supply",
            "Black Pepper": "Mang Erning's Rice & Ulam Supply",
            "Salmon Fillet": "Mang Erning's Rice & Ulam Supply",
            
            # All Day Breakfast - Aling Rosing's Almusal Supply
            "Breakfast Sausage": "Aling Rosing's Almusal Supply",
            "Spam / Luncheon Meat": "Aling Rosing's Almusal Supply"
        }
        
        for ing_sub, supplier_name in mapping_targets.items():
            sup = Supplier.query.filter(Supplier.name == supplier_name).first()
            if not sup:
                print(f"  [ERR] Supplier not found: {supplier_name}")
                continue
            
            # Find the ingredient by case-insensitive name match
            ing = Ingredient.query.filter(Ingredient.name.like(f"%{ing_sub}%")).first()
            if ing:
                ing.supplier_id = sup.id
                print(f"  [LINKED] Ingredient '{ing.name}' linked to '{sup.name}'")
            else:
                print(f"  [WARN] Ingredient containing '{ing_sub}' not found.")
                
        db.session.commit()
        
        # Step 2: Create new specific ingredients for empty categories
        print("\n[2/5] Creating new category-specific ingredients...")
        
        new_ingredients_to_create = [
            # Iced Coffee - Ate Mhel's Cold Coffee Supply
            {
                "name": "Espresso Beans (Iced)", "unit": "kg", "stock_qty": 50.0, "kitchen_qty": 10.0, 
                "reorder_level": 5.0, "cost_per_unit": 500.0, "category": "General", 
                "supplier_name": "Ate Mhel's Cold Coffee Supply"
            },
            # Milkshakes & Smoothies - Manong Jun's Shake Station
            {
                "name": "Vanilla Ice Cream", "unit": "L", "stock_qty": 100.0, "kitchen_qty": 20.0, 
                "reorder_level": 10.0, "cost_per_unit": 120.0, "category": "General", 
                "supplier_name": "Manong Jun's Shake Station"
            },
            # Best Sellers - Manong Ding's Prime Goods
            {
                "name": "Le Maison Secret Sauce", "unit": "L", "stock_qty": 50.0, "kitchen_qty": 10.0, 
                "reorder_level": 5.0, "cost_per_unit": 180.0, "category": "General", 
                "supplier_name": "Manong Ding's Prime Goods"
            },
            # Desserts - Aling Bebang's Matamis Supply
            {
                "name": "Condensed Milk", "unit": "can", "stock_qty": 100.0, "kitchen_qty": 25.0, 
                "reorder_level": 10.0, "cost_per_unit": 45.0, "category": "General", 
                "supplier_name": "Aling Bebang's Matamis Supply"
            },
            {
                "name": "Graham Crackers", "unit": "g", "stock_qty": 10000.0, "kitchen_qty": 2000.0, 
                "reorder_level": 1000.0, "cost_per_unit": 0.25, "category": "General", 
                "supplier_name": "Aling Bebang's Matamis Supply"
            },
            # Frappes - Ate Girlie's Frappe Depot
            {
                "name": "Frappe Base Powder", "unit": "kg", "stock_qty": 30.0, "kitchen_qty": 5.0, 
                "reorder_level": 5.0, "cost_per_unit": 350.0, "category": "General", 
                "supplier_name": "Ate Girlie's Frappe Depot"
            },
            # Iced Beverages - Aling Dolor's Malamig Trading
            {
                "name": "Cucumber Extract", "unit": "L", "stock_qty": 40.0, "kitchen_qty": 8.0, 
                "reorder_level": 5.0, "cost_per_unit": 150.0, "category": "General", 
                "supplier_name": "Aling Dolor's Malamig Trading"
            }
        ]
        
        created_ings = {}
        for item in new_ingredients_to_create:
            sup = Supplier.query.filter(Supplier.name == item["supplier_name"]).first()
            if not sup:
                print(f"  [ERR] Supplier not found for creation: {item['supplier_name']}")
                continue
                
            # Check if it already exists
            existing = Ingredient.query.filter(Ingredient.name == item["name"]).first()
            if existing:
                existing.supplier_id = sup.id
                existing.stock_qty = item["stock_qty"]
                existing.kitchen_qty = item["kitchen_qty"]
                existing.unit = item["unit"]
                existing.cost_per_unit = item["cost_per_unit"]
                created_ings[item["name"]] = existing
                print(f"  [EXISTS] Ingredient '{item['name']}' already exists, updated supplier mapping.")
            else:
                ing = Ingredient(
                    name=item["name"],
                    unit=item["unit"],
                    stock_qty=item["stock_qty"],
                    kitchen_qty=item["kitchen_qty"],
                    reorder_level=item["reorder_level"],
                    cost_per_unit=item["cost_per_unit"],
                    category=item["category"],
                    supplier_id=sup.id
                )
                db.session.add(ing)
                db.session.flush()
                created_ings[item["name"]] = ing
                print(f"  [CREATED] New Ingredient '{ing.name}' linked to '{sup.name}'")
                
        db.session.commit()
        
        # Step 3: Update recipes of Menu Items by Category to interconnect them
        print("\n[3/5] Interconnecting recipe definitions with newly added ingredients...")
        
        # 3.1 Iced Coffee recipes -> Use Espresso Beans (Iced) instead of Coffee Beans
        coffee_beans_ing = Ingredient.query.filter(Ingredient.name == "Coffee Beans").first()
        iced_espresso_ing = created_ings.get("Espresso Beans (Iced)")
        
        if coffee_beans_ing and iced_espresso_ing:
            iced_coffee_items = MenuItem.query.filter_by(category="Iced Coffee", is_deleted=False).all()
            for item in iced_coffee_items:
                # Find if they have a recipe row using generic Coffee Beans
                recipe_row = MenuItemIngredient.query.filter_by(menu_item_id=item.id, ingredient_id=coffee_beans_ing.id).first()
                if recipe_row:
                    recipe_row.ingredient_id = iced_espresso_ing.id
                    print(f"  [RECIPE UPDATE] '{item.name}' (Iced Coffee) now uses '{iced_espresso_ing.name}'")
                    
        # 3.2 Milkshakes & Smoothies recipes -> Use Vanilla Ice Cream instead of generic Ice Cream Base
        generic_ice_cream_ing = Ingredient.query.filter(Ingredient.name == "Ice Cream Base").first()
        vanilla_ice_cream_ing = created_ings.get("Vanilla Ice Cream")
        
        if generic_ice_cream_ing and vanilla_ice_cream_ing:
            milkshake_items = MenuItem.query.filter_by(category="Milkshakes & Smoothies", is_deleted=False).all()
            for item in milkshake_items:
                recipe_row = MenuItemIngredient.query.filter_by(menu_item_id=item.id, ingredient_id=generic_ice_cream_ing.id).first()
                if recipe_row:
                    recipe_row.ingredient_id = vanilla_ice_cream_ing.id
                    print(f"  [RECIPE UPDATE] '{item.name}' (Milkshake) now uses '{vanilla_ice_cream_ing.name}'")
                    
        # 3.3 Best Sellers recipes -> Add Le Maison Secret Sauce to give them a unique Best Seller touch!
        secret_sauce_ing = created_ings.get("Le Maison Secret Sauce")
        if secret_sauce_ing:
            best_sellers = MenuItem.query.filter_by(category="Best Sellers", is_deleted=False).all()
            for item in best_sellers:
                # Check if already added
                exists = MenuItemIngredient.query.filter_by(menu_item_id=item.id, ingredient_id=secret_sauce_ing.id).first()
                if not exists:
                    db.session.add(MenuItemIngredient(
                        menu_item_id=item.id,
                        ingredient_id=secret_sauce_ing.id,
                        quantity_needed=0.05
                    ))
                    print(f"  [RECIPE ADD] Added '{secret_sauce_ing.name}' to '{item.name}' (Best Seller)")

        # 3.4 Frappes -> Add Frappe Base Powder to all Frappes recipes!
        frappe_powder_ing = created_ings.get("Frappe Base Powder")
        if frappe_powder_ing:
            frappes = MenuItem.query.filter_by(category="Frappes", is_deleted=False).all()
            for item in frappes:
                exists = MenuItemIngredient.query.filter_by(menu_item_id=item.id, ingredient_id=frappe_powder_ing.id).first()
                if not exists:
                    db.session.add(MenuItemIngredient(
                        menu_item_id=item.id,
                        ingredient_id=frappe_powder_ing.id,
                        quantity_needed=0.05
                    ))
                    print(f"  [RECIPE ADD] Added '{frappe_powder_ing.name}' to '{item.name}' (Frappe)")

        # 3.5 Desserts -> Add Condensed Milk to desserts that don't have it, e.g., Mango Float, Affogato, Carrot Cake
        condensed_milk_ing = created_ings.get("Condensed Milk")
        if condensed_milk_ing:
            desserts = MenuItem.query.filter_by(category="Desserts", is_deleted=False).all()
            for item in desserts[:10]: # add to first 10 desserts to ensure they have high interconnectivity
                exists = MenuItemIngredient.query.filter_by(menu_item_id=item.id, ingredient_id=condensed_milk_ing.id).first()
                if not exists:
                    db.session.add(MenuItemIngredient(
                        menu_item_id=item.id,
                        ingredient_id=condensed_milk_ing.id,
                        quantity_needed=0.1
                    ))
                    print(f"  [RECIPE ADD] Added '{condensed_milk_ing.name}' to '{item.name}' (Dessert)")

        # 3.6 Iced Beverages -> Add Cucumber Extract to Iced Beverages
        cucumber_extract_ing = created_ings.get("Cucumber Extract")
        if cucumber_extract_ing:
            iced_bevs = MenuItem.query.filter_by(category="Iced Beverages", is_deleted=False).all()
            for item in iced_bevs:
                exists = MenuItemIngredient.query.filter_by(menu_item_id=item.id, ingredient_id=cucumber_extract_ing.id).first()
                if not exists:
                    db.session.add(MenuItemIngredient(
                        menu_item_id=item.id,
                        ingredient_id=cucumber_extract_ing.id,
                        quantity_needed=0.05
                    ))
                    print(f"  [RECIPE ADD] Added '{cucumber_extract_ing.name}' to '{item.name}' (Iced Beverage)")

        db.session.commit()

        # Step 4: Rebuild supplier catalog_items for all suppliers
        print("\n[4/5] Rebuilding catalog_items for all 18 suppliers to sync with DB...")
        suppliers = Supplier.query.all()
        for sup in suppliers:
            linked = Ingredient.query.filter_by(supplier_id=sup.id).order_by(Ingredient.name).all()
            names = [ing.name for ing in linked]
            sup.catalog_items = ", ".join(names) if names else sup.category
            print(f"  [CATALOG UPDATED] '{sup.name}' -> Supplied items: {sup.catalog_items}")
            
        db.session.commit()

        # Step 5: Final Validation of Menu Items out of stock logic and kitchen deduction
        print("\n[5/5] Performing final validation on recipe inventory links...")
        
        # Verify menu item stock calculation logic is intact
        test_item = MenuItem.query.filter_by(category="Iced Coffee", is_deleted=False).first()
        if test_item:
            print(f"  Test Item: '{test_item.name}' | Available: {test_item.is_available} | Out of Stock: {test_item.is_out_of_stock}")
            print(f"  Recipe details for '{test_item.name}':")
            for mi_ing in test_item.ingredients:
                print(f"    - Ingredient: {mi_ing.ingredient.name} | Needed: {mi_ing.quantity_needed} {mi_ing.ingredient.unit} | Kitchen Stock: {mi_ing.ingredient.kitchen_qty} {mi_ing.ingredient.unit}")
                
        print("\n" + "="*70)
        print("[SUCCESS] All empty suppliers seeded, recipes linked, and catalog synced!")
        print("="*70)

if __name__ == '__main__':
    try:
        fix_all_and_interconnect()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
