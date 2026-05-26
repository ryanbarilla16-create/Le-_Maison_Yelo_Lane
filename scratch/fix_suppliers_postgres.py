"""
DEFINITIVE FIX: Reassign every ingredient's supplier_id based on
which category uses it the MOST (dominant category → supplier mapping).

Uses direct psycopg2 to Neon PostgreSQL - no Flask startup needed.
"""
import os
import psycopg2
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()
db_url = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL")

print("="*70)
print("DEFINITIVE SUPPLIER FIX - Neon PostgreSQL via psycopg2")
print("="*70)
print(f"Connecting to: {db_url[:60]}...")

conn = psycopg2.connect(db_url)
cur = conn.cursor()

# ── 1. Load suppliers: category -> (id, name) ───────────────────────
cur.execute("SELECT id, name, category FROM supplier")
suppliers = cur.fetchall()
cat_to_sup = {}  # category -> (supplier_id, supplier_name)
for sid, sname, scat in suppliers:
    cat_to_sup[scat] = (sid, sname)

print(f"\nLoaded {len(suppliers)} suppliers:")
for cat, (sid, sname) in sorted(cat_to_sup.items()):
    print(f"  [{sid}] {sname} -> {cat}")

# ── 2. Get all ingredient-category links from recipes ────────────────
cur.execute("""
    SELECT mii.ingredient_id, mi.category
    FROM menu_item_ingredient mii
    JOIN menu_item mi ON mi.id = mii.menu_item_id
    WHERE NOT mi.is_deleted
""")
links = cur.fetchall()

# Count how many times each ingredient appears in each category
ing_cat_count = defaultdict(lambda: defaultdict(int))
for ing_id, cat in links:
    ing_cat_count[ing_id][cat] += 1

print(f"\nFound {len(links)} recipe links across {len(ing_cat_count)} unique ingredients")

# ── 3. Load all ingredients ──────────────────────────────────────────
cur.execute("SELECT id, name, supplier_id FROM ingredient")
all_ingredients = cur.fetchall()
print(f"\nTotal ingredients in DB: {len(all_ingredients)}")

# ── 4. Assign supplier_id by dominant category ───────────────────────
print("\n" + "="*70)
print("ASSIGNING SUPPLIER_ID BY DOMINANT CATEGORY")
print("="*70)

updated = 0
skipped_no_recipe = []
skipped_no_supplier = []

for ing_id, ing_name, old_sup_id in all_ingredients:
    if ing_id not in ing_cat_count:
        skipped_no_recipe.append(ing_name)
        continue

    # Sort categories by usage count (most used first)
    cat_counts = ing_cat_count[ing_id]
    sorted_cats = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)

    # Pick the top category that has a supplier
    assigned_sup_id = None
    assigned_sup_name = None
    assigned_cat = None
    for cat, count in sorted_cats:
        if cat in cat_to_sup:
            assigned_sup_id, assigned_sup_name = cat_to_sup[cat]
            assigned_cat = cat
            break

    if assigned_sup_id is None:
        skipped_no_supplier.append(f"{ing_name} (cats: {list(cat_counts.keys())})")
        continue

    if old_sup_id != assigned_sup_id:
        cur.execute(
            "UPDATE ingredient SET supplier_id = %s WHERE id = %s",
            (assigned_sup_id, ing_id)
        )
        print(f"  UPDATED [{ing_id}] '{ing_name}' -> {assigned_sup_name} [{assigned_cat}] (was supplier_id={old_sup_id})")
        updated += 1
    else:
        pass  # no change needed

conn.commit()

print(f"\nTotal updated: {updated}")
if skipped_no_recipe:
    print(f"\nIngredients NOT in any recipe (supplier_id unchanged): {len(skipped_no_recipe)}")
    for n in skipped_no_recipe:
        print(f"  - {n}")
if skipped_no_supplier:
    print(f"\nIngredients whose categories have no supplier: {len(skipped_no_supplier)}")
    for n in skipped_no_supplier:
        print(f"  - {n}")

# ── 5. Final report ──────────────────────────────────────────────────
print("\n" + "="*70)
print("FINAL RESULT: Ingredients per Supplier")
print("="*70)

for sid, sname, scat in sorted(suppliers, key=lambda x: x[2]):
    cur.execute("SELECT name FROM ingredient WHERE supplier_id = %s ORDER BY name", (sid,))
    ings = [r[0] for r in cur.fetchall()]
    print(f"\n[{sid}] {sname} ({scat})")
    print(f"  Ingredients ({len(ings)}): {', '.join(ings) if ings else '(none)'}")

print("\n" + "="*70)
print("[SUCCESS] All supplier-ingredient mappings updated!")
print("="*70)

cur.close()
conn.close()
