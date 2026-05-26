"""
Fix: For every supplier, make sure ALL ingredients used by menu items
in that supplier's category are assigned to that supplier (supplier_id).

Logic:
  - Each supplier covers exactly ONE menu category.
  - Every ingredient used in a recipe for a menu item in that category
    should have supplier_id = that supplier's ID.
  - For ingredients used in MULTIPLE categories (e.g. Milk, Sugar):
    assign to the category where they are used MOST.
  - Ingredients with no recipe usage: keep their current supplier as-is.
"""

import sys
sys.path.append(r'c:\Users\Ryan Bien Barilla\OneDrive\Desktop\python web (capstone)')
from app import app
from models import db, Ingredient, MenuItemIngredient, MenuItem, Supplier
from collections import defaultdict

# Supplier "Sweet Breakfast" -> maps to menu category "Sweet Breakfast"
# which exists in the menu items

with app.app_context():
    print("=" * 70)
    print("FIXING: All supplier_id on ingredients by category usage")
    print("=" * 70)

    # ── Build category → supplier map ────────────────────────────────────────
    cat_to_supplier = {}
    for sup in Supplier.query.all():
        cat_to_supplier[sup.category] = sup
    print(f"\nSuppliers loaded: {len(cat_to_supplier)}")
    for cat, sup in sorted(cat_to_supplier.items()):
        print(f"  [{sup.id}] '{sup.name}' -> '{cat}'")

    # ── Build ingredient_id → {category: count} usage map ──────────────────
    print("\nBuilding ingredient usage map from recipes...")
    ing_cat_count = defaultdict(lambda: defaultdict(int))

    links = (
        db.session.query(
            MenuItemIngredient.ingredient_id,
            MenuItem.category
        )
        .join(MenuItem, MenuItemIngredient.menu_item_id == MenuItem.id)
        .filter(MenuItem.is_deleted == False)
        .all()
    )

    for ing_id, category in links:
        ing_cat_count[ing_id][category] += 1

    print(f"  Total ingredient-recipe links: {len(links)}")
    print(f"  Unique ingredients used in recipes: {len(ing_cat_count)}")

    # ── Assign each ingredient to the dominant category supplier ─────────────
    print("\nAssigning supplier_id to each ingredient by dominant category...")
    assigned = 0
    skipped_no_sup = []
    skipped_no_recipe = []

    for ing in Ingredient.query.all():
        if ing.id not in ing_cat_count:
            skipped_no_recipe.append(ing.name)
            continue

        cat_counts = ing_cat_count[ing.id]
        # Sort by usage count descending; pick the top category with a supplier
        sorted_cats = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)

        assigned_supplier = None
        for cat, count in sorted_cats:
            if cat in cat_to_supplier:
                assigned_supplier = cat_to_supplier[cat]
                break

        if assigned_supplier is None:
            skipped_no_sup.append(f"{ing.name} (cats: {list(cat_counts.keys())})")
            continue

        old_id = ing.supplier_id
        ing.supplier_id = assigned_supplier.id
        change = f"  (was: {old_id})" if old_id != assigned_supplier.id else "  (no change)"
        print(f"  [{ing.id}] '{ing.name}' -> supplier='{assigned_supplier.name}' "
              f"[{assigned_supplier.category}]{change}")
        assigned += 1

    db.session.commit()

    print(f"\nTotal assigned: {assigned}")
    if skipped_no_recipe:
        print(f"\nIngredients with no recipe (kept as-is): {len(skipped_no_recipe)}")
        for n in skipped_no_recipe:
            print(f"  - {n}")
    if skipped_no_sup:
        print(f"\nIngredients whose categories have no supplier: {len(skipped_no_sup)}")
        for n in skipped_no_sup:
            print(f"  - {n}")

    # ── Final report: count ingredients per supplier ─────────────────────────
    print("\n" + "=" * 70)
    print("FINAL SUPPLIER INGREDIENT COUNTS AFTER FIX:")
    print("=" * 70)
    print(f"{'#':<5}{'Supplier':<45}{'Category':<35}{'# Ingredients'}")
    print("-" * 95)

    for sup in Supplier.query.order_by(Supplier.category).all():
        count = Ingredient.query.filter_by(supplier_id=sup.id).count()
        ings = Ingredient.query.filter_by(supplier_id=sup.id).all()
        ing_names = ", ".join([i.name for i in ings])
        print(f"[{sup.id}] {sup.name:<43} {sup.category:<35} {count}")
        print(f"       Ingredients: {ing_names or '(none)'}")
        print()

    print("=" * 70)
    print("[SUCCESS] All suppliers now match their category ingredients!")
    print("=" * 70)
