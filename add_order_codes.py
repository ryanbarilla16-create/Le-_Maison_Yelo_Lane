"""
Backfill script to add order codes to existing orders.
Format: ORD-YYYYMMDD-SEQUENCE (e.g., ORD-20240526-001)
"""

from app import app
from models import db, Order
from datetime import date
from collections import defaultdict

def generate_order_code_for_date(order_date, sequence):
    """
    Generate order code for a specific date and sequence.
    Format: ORD-YYYYMMDD-SEQUENCE
    """
    date_str = order_date.strftime('%Y%m%d')
    return f"ORD-{date_str}-{sequence:03d}"

def backfill_order_codes():
    """Add order codes to all existing orders that don't have one."""
    with app.app_context():
        # Get all orders without order_code, ordered by created_at
        orders = Order.query.filter(
            (Order.order_code == None) | (Order.order_code == '')
        ).order_by(Order.created_at.asc()).all()
        
        if not orders:
            print("✅ All orders already have order codes!")
            return
        
        print(f"📦 Found {len(orders)} orders without order codes")
        print("🔄 Generating order codes...")
        
        # Group orders by date to maintain sequence per day
        orders_by_date = defaultdict(list)
        for order in orders:
            order_date = order.created_at.date()
            orders_by_date[order_date].append(order)
        
        # Generate codes for each date
        updated_count = 0
        for order_date in sorted(orders_by_date.keys()):
            date_orders = orders_by_date[order_date]
            
            # Check if there are existing orders with codes for this date
            existing_codes = Order.query.filter(
                Order.order_code.like(f'ORD-{order_date.strftime("%Y%m%d")}-%')
            ).order_by(Order.order_code.desc()).first()
            
            # Determine starting sequence
            if existing_codes and existing_codes.order_code:
                try:
                    last_seq = int(existing_codes.order_code.split('-')[-1])
                    start_seq = last_seq + 1
                except (ValueError, IndexError):
                    start_seq = 1
            else:
                start_seq = 1
            
            # Assign codes to orders for this date
            for idx, order in enumerate(date_orders, start=start_seq):
                order_code = generate_order_code_for_date(order_date, idx)
                order.order_code = order_code
                updated_count += 1
                
                if updated_count % 50 == 0:
                    print(f"   ⏳ Processed {updated_count}/{len(orders)} orders...")
        
        # Commit all changes
        try:
            db.session.commit()
            print(f"\n✅ Successfully added order codes to {updated_count} orders!")
            print(f"📊 Orders grouped by {len(orders_by_date)} different dates")
            
            # Show sample codes
            print("\n📋 Sample order codes:")
            sample_orders = Order.query.filter(
                Order.order_code != None
            ).order_by(Order.created_at.desc()).limit(5).all()
            
            for order in sample_orders:
                print(f"   • Order #{order.id}: {order.order_code} (Created: {order.created_at.strftime('%Y-%m-%d %H:%M')})")
                
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Error during commit: {str(e)}")
            raise

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 ORDER CODE BACKFILL SCRIPT")
    print("=" * 60)
    print()
    
    backfill_order_codes()
    
    print()
    print("=" * 60)
    print("✨ Backfill complete!")
    print("=" * 60)
