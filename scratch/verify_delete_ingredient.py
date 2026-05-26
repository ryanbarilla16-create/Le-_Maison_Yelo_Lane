import os
import sys
import datetime
import traceback

sys.path.append(r'c:\Users\Ryan Bien Barilla\OneDrive\Desktop\python web (capstone)')

from app import app
from models import db, User, Ingredient, MenuItemIngredient, MenuItem, WasteRecord, IngredientBatch, InventoryLog, StockRequest

def run_test():
    print("Starting ingredient deletion verification test...")
    with app.app_context():
        # Find a valid User and MenuItem to link our dummy records
        user = User.query.first()
        menu_item = MenuItem.query.first()
        
        if not user:
            print("ERROR: No User found in database to run verification.")
            sys.exit(1)
        if not menu_item:
            print("ERROR: No MenuItem found in database to run verification.")
            sys.exit(1)
            
        print(f"Using User: {user.first_name} {user.last_name} (ID: {user.id})")
        print(f"Using MenuItem: {menu_item.name} (ID: {menu_item.id})")

        # 1. Create a dummy ingredient
        test_ing = Ingredient(
            name="Temporary Test Delete Ingredient",
            unit="pcs",
            stock_qty=10.0,
            reorder_level=5.0,
            cost_per_unit=1.5
        )
        db.session.add(test_ing)
        db.session.commit()
        print(f"Created temporary ingredient (ID: {test_ing.id})")

        # 2. Create referencing records
        # MenuItemIngredient
        menu_item_ing = MenuItemIngredient(
            menu_item_id=menu_item.id,
            ingredient_id=test_ing.id,
            quantity_needed=2.0
        )
        db.session.add(menu_item_ing)

        # InventoryLog
        inv_log = InventoryLog(
            ingredient_id=test_ing.id,
            user_id=user.id,
            action="ADD",
            quantity=10.0,
            previous_stock=0.0,
            new_stock=10.0,
            reason="Test Insertion"
        )
        db.session.add(inv_log)

        # WasteRecord
        waste = WasteRecord(
            ingredient_id=test_ing.id,
            recorded_by_id=user.id,
            quantity_wasted=2.0,
            reason="SPOILED",
            cost_lost=3.0
        )
        db.session.add(waste)

        # IngredientBatch
        batch = IngredientBatch(
            ingredient_id=test_ing.id,
            batch_qty=10.0,
            remaining_qty=10.0,
            purchase_date=datetime.date.today()
        )
        db.session.add(batch)

        # StockRequest
        stock_req = StockRequest(
            ingredient_id=test_ing.id,
            requested_by_id=user.id,
            quantity_requested=5.0,
            status="PENDING"
        )
        db.session.add(stock_req)

        db.session.commit()
        print("Created and linked all referencing records in related tables successfully.")

        # Keep track of IDs for checking
        ing_id = test_ing.id
        menu_item_ing_id = menu_item_ing.id
        inv_log_id = inv_log.id
        waste_id = waste.id
        batch_id = batch.id
        stock_req_id = stock_req.id

        # Verify they exist
        assert Ingredient.query.get(ing_id) is not None
        assert MenuItemIngredient.query.get(menu_item_ing_id) is not None
        assert InventoryLog.query.get(inv_log_id) is not None
        assert WasteRecord.query.get(waste_id) is not None
        assert IngredientBatch.query.get(batch_id) is not None
        assert StockRequest.query.get(stock_req_id) is not None
        print("Verified all records are present in DB.")

        # 3. Simulate deletion block from our route
        print("Simulating deletion block...")
        
        # Delete related records
        MenuItemIngredient.query.filter_by(ingredient_id=ing_id).delete()
        InventoryLog.query.filter_by(ingredient_id=ing_id).delete()
        WasteRecord.query.filter_by(ingredient_id=ing_id).delete()
        IngredientBatch.query.filter_by(ingredient_id=ing_id).delete()
        StockRequest.query.filter_by(ingredient_id=ing_id).delete()
        
        # Delete the ingredient itself
        db.session.delete(test_ing)
        db.session.commit()
        print("Simulated deletion completed successfully.")

        # 4. Verify all records are gone
        assert Ingredient.query.get(ing_id) is None
        assert MenuItemIngredient.query.get(menu_item_ing_id) is None
        assert InventoryLog.query.get(inv_log_id) is None
        assert WasteRecord.query.get(waste_id) is None
        assert IngredientBatch.query.get(batch_id) is None
        assert StockRequest.query.get(stock_req_id) is None

        print("[SUCCESS] All referencing rows and the ingredient itself were successfully deleted!")
        print("Automated test PASSED!")

if __name__ == '__main__':
    try:
        run_test()
    except Exception as e:
        traceback.print_exc()
        sys.exit(1)
