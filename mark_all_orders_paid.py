"""
Mark all UNPAID orders as PAID
"""
from app import app
from models import db, Order
from utils import get_ph_time

def mark_all_paid():
    with app.app_context():
        print("\n" + "="*70)
        print("  MARKING ALL UNPAID ORDERS AS PAID")
        print("="*70)
        
        # Get all unpaid orders
        unpaid_orders = Order.query.filter_by(payment_status='UNPAID').all()
        
        if not unpaid_orders:
            print("\n✅ No unpaid orders found! All orders are already paid.")
            print("="*70)
            return
        
        print(f"\n📊 Found {len(unpaid_orders)} UNPAID orders\n")
        
        # Show details
        print("Orders to be marked as PAID:")
        for order in unpaid_orders:
            print(f"   • Order #{order.id} ({order.order_code}) - ₱{order.total_amount} - {order.status}")
        
        print(f"\n⏳ Processing {len(unpaid_orders)} orders...")
        
        # Mark all as paid
        updated_count = 0
        for order in unpaid_orders:
            try:
                order.payment_status = 'PAID'
                order.payment_method = 'COUNTER'  # Set default payment method
                order.amount_tendered = order.total_amount  # Set tendered amount
                order.change_amount = 0  # No change
                updated_count += 1
            except Exception as e:
                print(f"   ❌ Error updating Order #{order.id}: {str(e)}")
        
        # Commit changes
        try:
            db.session.commit()
            print(f"\n✅ SUCCESS! Updated {updated_count} orders to PAID status")
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ ERROR: Failed to save changes: {str(e)}")
            return
        
        # Verify
        remaining_unpaid = Order.query.filter_by(payment_status='UNPAID').count()
        total_paid = Order.query.filter_by(payment_status='PAID').count()
        
        print("\n📊 UPDATED STATISTICS:")
        print(f"   Total PAID orders: {total_paid}")
        print(f"   Remaining UNPAID orders: {remaining_unpaid}")
        
        print("\n" + "="*70)
        print("✅ ALL ORDERS ARE NOW PAID!")
        print("   Refresh your cashier page to see the changes")
        print("="*70 + "\n")

if __name__ == '__main__':
    mark_all_paid()
