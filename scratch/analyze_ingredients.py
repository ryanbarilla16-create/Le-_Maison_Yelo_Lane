import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
db_url = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL")

conn = psycopg2.connect(db_url)
cur = conn.cursor()

# Get all suppliers
cur.execute("SELECT id, name, category FROM supplier")
suppliers = cur.fetchall()
sup_by_id = {row[0]: (row[1], row[2]) for row in suppliers}
sup_by_cat = {row[2]: (row[0], row[1]) for row in suppliers}

# Get all ingredients
cur.execute("SELECT id, name, category, supplier_id FROM ingredient")
ingredients = cur.fetchall()
ing_by_id = {row[0]: {"name": row[1], "category": row[2], "supplier_id": row[3]} for row in ingredients}

# Get menu item ingredients linked to menu items
cur.execute("""
    SELECT mii.ingredient_id, mi.name, mi.category 
    FROM menu_item_ingredient mii
    JOIN menu_item mi ON mi.id = mii.menu_item_id
    WHERE NOT mi.is_deleted
""")
links = cur.fetchall()

out_path = r"c:\Users\Ryan Bien Barilla\OneDrive\Desktop\python web (capstone)\scratch\ingredients_analysis.txt"
with open(out_path, "w", encoding="utf-8") as out:
    out.write("--- Category to Menu Items & Ingredients ---\n")
    cat_to_ings = {}
    for ing_id, mi_name, mi_cat in links:
        if mi_cat not in cat_to_ings:
            cat_to_ings[mi_cat] = set()
        if ing_id in ing_by_id:
            cat_to_ings[mi_cat].add(ing_by_id[ing_id]["name"])

    for cat, ings in sorted(cat_to_ings.items()):
        sup_info = sup_by_cat.get(cat, ("None", "None"))
        out.write(f"\nCategory: {cat} (Supplier: {sup_info[1]}, ID: {sup_info[0]})\n")
        out.write("Ingredients in recipes:\n")
        for ing in sorted(list(ings)):
            out.write(f"  - {ing}\n")

    # Print ingredients currently assigned to each supplier
    out.write("\n--- Ingredients assigned to each Supplier ID ---\n")
    for sup_id, (name, cat) in sorted(sup_by_id.items()):
        cur.execute("SELECT name FROM ingredient WHERE supplier_id = %s", (sup_id,))
        ings = [r[0] for r in cur.fetchall()]
        out.write(f"Supplier: {name} (ID: {sup_id}, Category: {cat})\n")
        out.write(f"  Ingredients: {', '.join(ings) if ings else '(none)'}\n")

cur.close()
conn.close()
print("Analysis complete.")
