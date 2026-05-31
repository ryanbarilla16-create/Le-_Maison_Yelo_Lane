from models import db, OrderChat, Order
from app import app

with app.app_context():
    print("Cleaning up orphaned OrderChat records...\n")
    
    # Find orphaned chats (with NULL order_id or non-existent order_id)
    orphaned = OrderChat.query.filter(
        (OrderChat.order_id == None) | 
        (~OrderChat.order_id.in_(db.session.query(Order.id)))
    ).all()
    
    print(f"Found {len(orphaned)} orphaned OrderChat records")
    
    for chat in orphaned:
        print(f"  - Deleting chat #{chat.id} (order_id: {chat.order_id})")
        db.session.delete(chat)
    
    if orphaned:
        db.session.commit()
        print(f"\n✅ Deleted {len(orphaned)} orphaned records")
    else:
        print("✅ No orphaned records found")
    
    # Verify
    remaining_orphaned = OrderChat.query.filter(
        (OrderChat.order_id == None) | 
        (~OrderChat.order_id.in_(db.session.query(Order.id)))
    ).count()
    
    print(f"\nVerification: {remaining_orphaned} orphaned records remaining")
