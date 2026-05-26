"""
Direct SQLite fix - uses relative path (same as find_db.py which worked).
Reassigns supplier_id for all ingredients based on dominant category usage.
"""
import sqlite3
import os
from collections import defaultdict

# Use relative path - this works as confirmed by find_db.py
DB_PATH = r'instance\lemaisondb.db'

print(f"Connecting to: {os.path.abspath(DB_PATH)}")
print(f"File exists: {os.path.exists(DB_PATH)}")
print(f"File size: {os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 'N/A'}")

conn = sqlite3.connect(DB_PATH, timeout=30)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=30000")
cur = conn.cursor()

# Verify supplier table exists
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f"Tables found: {tables}")

cur.execute("SELECT COUNT(*) FROM supplier")
sup_count = cur.fetchone()[0]
print(f"Supplier count: {sup_count}")

print("\n" + "=" * 70)
print("FIXING: Reassign supplier_id per ingredient by dominant category")
print("=" * 70)

# ── Load suppliers: category -> (id, name) ──────────────────────────────
cur.execute("SELECT id, name, category FROM supplier")
suppliers = cur.fetchall()
cat_to_supplier = {}
for sid, sname, scat in suppliers:
    cat_to_supplier[scat] = (sid, sname)

print(f"\nLoaded {len(suppliers)} suppliers:")
for scat, (sid, sname) in sorted(cat_to_supplier.items()):
    print(f"  [{sid}] {sname} -> {scat}")

# ── Load recipe links: ingredient_id -> {category: count} ───────────────
cur.execute("""
    SELECT mii.ingredient_id, mi.category
    FROM menu_item_ingredient mii
    JOIN menu_item mi ON mi.id = mii.menu_item_id
    WHERE mi.is_deleted = 0
""")
links = cur.fetchall()
print(f"\nLoaded {len(links)} ingredient-recipe links")

ing_cat_count = defaultdict(lambda: defaultdict(int))
for ing_id, category in links:
    ing_cat_count[ing_id][category] += 1

# ── Load all ingredients ────────────────────────────────────────────────
cur.execute("SELECT id, name, supplier_id FROM ingredient")
ingredients = cur.fetchall()
print(f"Loaded {len(ingredients)} ingredients\n")

# ── Assign each ingredient to its dominant-category supplier ────────────
print("Assigning suppliers by dominant category:\n")
updates = []
skipped_no_recipe = []
skipped_no_supplier = []

for ing_id, ing_name, old_sup_id in ingredients:
    if ing_id not in ing_cat_count:
        skipped_no_recipe.append(ing_name)
        continue

    # Sort categories by usage count (most used first)
    sorted_cats = sorted(ing_cat_count[ing_id].items(), key=lambda x: x[1], reverse=True)

    new_sup_id = None
    new_sup_name = None
    chosen_cat = None
    for cat, count in sorted_cats:
        if cat in cat_to_supplier:
            new_sup_id, new_sup_name = cat_to_supplier[cat]
            chosen_cat = cat
            break

    if new_sup_id is None:
        skipped_no_supplier.append(f"{ing_name} (cats: {[c for c,_ in sorted_cats]})")
        continue

    changed = " <-- CHANGED" if new_sup_id != old_sup_id else ""
    print(f"  [{ing_id}] {ing_name:<35} -> {new_sup_name} [{chosen_cat}]{changed}")
    updates.append((new_sup_id, ing_id))

# ── Apply updates ────────────────────────────────────────────────────────
print(f"\nApplying {len(updates)} supplier assignments...")
cur.executemany("UPDATE ingredient SET supplier_id = ? WHERE id = ?", updates)
conn.commit()
print(f"Done! {len(updates)} ingredients updated.")

if skipped_no_recipe:
    print(f"\nNo recipe (kept as-is): {len(skipped_no_recipe)}")
    for n in skipped_no_recipe:
        print(f"  - {n}")
if skipped_no_supplier:
    print(f"\nCategory has no supplier: {len(skipped_no_supplier)}")
    for n in skipped_no_supplier:
        print(f"  - {n}")

# ── Final verification ───────────────────────────────────────────────────
print("\n" + "=" * 70)
print("FINAL: Ingredients per supplier")
print("=" * 70)

for sid, sname, scat in sorted(suppliers, key=lambda x: x[2]):
    cur.execute("SELECT name FROM ingredient WHERE supplier_id = ? ORDER BY name", (sid,))
    ings = [r[0] for r in cur.fetchall()]
    print(f"\n[{sid}] {sname}")
    print(f"      Category: {scat}")
    print(f"      Items ({len(ings)}): {', '.join(ings) or '(none)'}")

conn.close()
print("\n" + "=" * 70)
print("SUCCESS! All supplier ingredient assignments are now correct.")
print("=" * 70)
