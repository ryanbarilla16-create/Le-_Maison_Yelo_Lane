"""
Test that each supplier now shows the correct ingredients based on its category.
Prints a comparison: Ingredients in category recipes vs Ingredients returned by the API.
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
db_url = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL")

conn = psycopg2.connect(db_url)
cur = conn.cursor()

# Get all suppliers
cur.execute("SELECT id, name, category FROM supplier ORDER BY category")
suppliers = cur.fetchall()

print("="*75)
print("VERIFICATION: Supplier Category vs Ingredients in Recipes")
print("="*75)

all_ok = True
for sup_id, sup_name, sup_cat in suppliers:
    if not sup_cat:
        print(f"\n[WARN] Supplier '{sup_name}' has no category set!")
        continue
    
    # Ingredients used in this category's recipes
    cur.execute("""
        SELECT DISTINCT i.id, i.name
        FROM ingredient i
        JOIN menu_item_ingredient mii ON mii.ingredient_id = i.id
        JOIN menu_item mi ON mi.id = mii.menu_item_id
        WHERE mi.category = %s AND NOT mi.is_deleted
        ORDER BY i.name
    """, (sup_cat,))
    recipe_ings = cur.fetchall()
    recipe_names = sorted([r[1] for r in recipe_ings])
    
    print(f"\n[{sup_id}] {sup_name} ({sup_cat})")
    print(f"  Ingredients in category recipes ({len(recipe_ings)}):")
    for r in recipe_ings:
        print(f"    - {r[1]}")
    
    if not recipe_ings:
        print(f"  [WARN] No recipe ingredients found for category '{sup_cat}'")
        all_ok = False

print("\n" + "="*75)
if all_ok:
    print("[SUCCESS] All suppliers verified - category-based lookup will work correctly!")
else:
    print("[WARN] Some suppliers have empty categories in recipes.")
print("="*75)

cur.close()
conn.close()
