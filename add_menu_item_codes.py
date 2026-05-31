"""
Migration script to add item_code to existing menu items.
Run this once to backfill codes for existing items.
"""
from app import app, db
from models import MenuItem
from utils import generate_menu_item_code

def backfill_menu_item_codes():
    """Add unique codes to all existing menu items that don't have one."""
    with app.app_context():
        print("Starting menu item code backfill...")
        
        # Get all menu items without codes
        items_without_codes = MenuItem.query.filter(
            (MenuItem.item_code == None) | (MenuItem.item_code == '')
        ).all()
        
        print(f"Found {len(items_without_codes)} items without codes")
        
        updated_count = 0
        for item in items_without_codes:
            try:
                # Generate code based on category
                item_code = generate_menu_item_code(item.category)
                item.item_code = item_code
                print(f"  ✓ {item.name} → {item_code}")
                updated_count += 1
            except Exception as e:
                print(f"  ✗ Error generating code for {item.name}: {e}")
        
        # Commit all changes
        try:
            db.session.commit()
            print(f"\n✅ Successfully added codes to {updated_count} menu items!")
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Error committing changes: {e}")

if __name__ == '__main__':
    backfill_menu_item_codes()
