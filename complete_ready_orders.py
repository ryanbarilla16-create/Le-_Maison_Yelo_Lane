"""
Mark all READY orders as COMPLETED so they can be archived
"""
from app import app
from models import db, Order
from utils import get_ph_time

def complete_ready_orders():
    with app.app_context():
        print("\n" + "="*70)
        print("  MARKING READY ORDERS AS COMPLETED")
        print("="*70)
        
        # Get all READY orders
        ready_orders = Order.query.filter_by(status='READY').all()
        
        if not ready_orders:
            print("\n✅ No READY orders found!")
            print("="*70)
            return
        
        print(f"\n📊 Found {len(ready_orders)} READY orders\n")
        
        # Show details
        print("Orders to be marked as COMPLETED:")
        for order in ready_orders[:10]:  # Show first 10
            print(f"   • Order #{order.id} ({order.order_code}) - ₱{order.total_amount} - {order.payment_status}")
        if len(ready_orders) > 10:
            print(f"   ... and {len(ready_orders) - 10} more")
        
        print(f"\n⏳ Processing {len(ready_orders)} orders...")
        
        # Mark all as completed
        updated_count = 0
        for order in ready_orders:
            try:
                order.status = 'COMPLETED'
                # If table order, mark table as available
                if order.table_number:
                    order.table_status = 'AVAILABLE'
                updated_count += 1
            except Exception as e:
                print(f"   ❌ Error updating Order #{order.id}: {str(e)}")
        
        # Commit changes
        try:
            db.session.commit()
            print(f"\n✅ SUCCESS! Updated {updated_count} orders to COMPLETED status")
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ ERROR: Failed to save changes: {str(e)}")
            return
        
        # Verify
        remaining_ready = Order.query.filter_by(status='READY').count()
        total_completed = Order.query.filter_by(status='COMPLETED').count()
        
        print("\n📊 UPDATED STATISTICS:")
        print(f"   Total COMPLETED orders: {total_completed}")
        print(f"   Remaining READY orders: {remaining_ready}")
        
        print("\n" + "="*70)
        print("✅ ALL READY ORDERS ARE NOW COMPLETED!")
        print("   These orders can now be archived")
        print("="*70 + "\n")

if __name__ == '__main__':
    complete_ready_orders()
