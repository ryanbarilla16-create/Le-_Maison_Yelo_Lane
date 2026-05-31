"""
Migration script to add ingredient_code to existing ingredients.
Run this once to backfill codes for existing ingredients.
"""
import sys
# Try to reconfigure stdout to handle UTF-8 if possible
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

from app import app, db
from models import Ingredient
from utils import generate_ingredient_code

def backfill_ingredient_codes():
    """Add unique codes to all existing ingredients that don't have one."""
    with app.app_context():
        print("Starting ingredient code backfill...")
        
        # Get all ingredients without codes
        ingredients_without_codes = Ingredient.query.filter(
            (Ingredient.ingredient_code == None) | (Ingredient.ingredient_code == '')
        ).all()
        
        print(f"Found {len(ingredients_without_codes)} ingredients without codes")
        
        updated_count = 0
        for ing in ingredients_without_codes:
            try:
                # Generate code based on category
                ing_code = generate_ingredient_code(ing.category)
                ing.ingredient_code = ing_code
                db.session.commit()  # commit one by one to ensure generate_ingredient_code increments correctly!
                print(f"  [OK] {ing.name} (Category: {ing.category}) -> {ing_code}")
                updated_count += 1
            except Exception as e:
                db.session.rollback()
                print(f"  [ERR] Error generating code for {ing.name}: {e}")
        
        print(f"\n[SUCCESS] Successfully added codes to {updated_count} ingredients!")

if __name__ == '__main__':
    backfill_ingredient_codes()
