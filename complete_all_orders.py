"""
Mark all PENDING, PREPARING, and HOLD orders as COMPLETED
"""
from app import app
from models import db, Order
from utils import get_ph_time

def complete_all_orders():
    with app.app_context():
        print("\n" + "="*70)
        print("  COMPLETING ALL PENDING/PREPARING/HOLD ORDERS")
        print("="*70)
        
        # Get all non-completed orders
        incomplete_orders = Order.query.filter(
            Order.status.in_(['PENDING', 'PREPARING', 'HOLD'])
        ).all()
        
        if not incomplete_orders:
            print("\n✅ No incomplete orders found! All orders are completed.")
            print("="*70)
            return
        
        print(f"\n📊 Found {len(incomplete_orders)} incomplete orders\n")
        
        # Group by status
        from collections import Counter
        status_counts = Counter([o.status for o in incomplete_orders])
        
        print("Orders by status:")
        for status, count in status_counts.items():
            print(f"   • {status}: {count}")
        
        print(f"\n⏳ Processing {len(incomplete_orders)} orders...")
        
        # Mark all as completed
        updated_count = 0
        for order in incomplete_orders:
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
        total_completed = Order.query.filter_by(status='COMPLETED').count()
        total_orders = Order.query.count()
        
        print("\n📊 FINAL STATISTICS:")
        print(f"   Total orders: {total_orders}")
        print(f"   COMPLETED orders: {total_completed}")
        print(f"   All orders are now COMPLETED!")
        
        print("\n" + "="*70)
        print("✅ ALL ORDERS ARE NOW COMPLETED AND PAID!")
        print("   Ready to be archived")
        print("="*70 + "\n")

if __name__ == '__main__':
    complete_all_orders()
