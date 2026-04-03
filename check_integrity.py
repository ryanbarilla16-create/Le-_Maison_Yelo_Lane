from app import app
from models import Order, MenuItem
with app.app_context():
    try:
        orders = Order.query.limit(20).all()
        for o in orders:
            print(f"Order #{o.id}")
            for item in o.items:
                if item.menu_item is None:
                    print(f"  Warning: Order {o.id} has an item with missing MenuItem (id: {item.menu_item_id})")
                else:
                    print(f"  Item: {item.menu_item.name}")
        print("Order check successful.")
    except Exception as e:
        print(f"Order check failed: {e}")
