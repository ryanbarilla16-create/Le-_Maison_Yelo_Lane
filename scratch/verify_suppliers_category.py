import sys
sys.path.append(r'c:\Users\Ryan Bien Barilla\OneDrive\Desktop\python web (capstone)')
from app import app
from models import db, Supplier

def verify_categories():
    print("=" * 60)
    print("VERIFYING EXPLICIT SUPPLIER CATEGORIES")
    print("=" * 60)
    with app.app_context():
        suppliers = Supplier.query.order_by(Supplier.name).all()
        print(f"Total suppliers found in DB: {len(suppliers)}")
        
        has_category_count = 0
        for s in suppliers:
            if s.category:
                has_category_count += 1
                print(f"  [OK] Supplier '{s.name}' -> Category: '{s.category}'")
            else:
                print(f"  [ERR] Supplier '{s.name}' has no category!")
                
        print("-" * 60)
        print(f"Summary: {has_category_count}/{len(suppliers)} suppliers have explicit categories in DB.")
        assert has_category_count == len(suppliers), "Not all suppliers have explicit categories!"
        print("[SUCCESS] All seeded suppliers have correct, explicit categories assigned in DB!")
        print("=" * 60)

if __name__ == '__main__':
    try:
        verify_categories()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
