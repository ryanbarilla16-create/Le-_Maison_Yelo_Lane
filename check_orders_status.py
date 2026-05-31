"""
Check why orders are not being archived
"""
from app import app
from models import Order
from utils import get_ph_time
from datetime import timedelta

def check_orders():
    with app.app_context():
        print("\n" + "="*70)
        print("  CHECKING ORDERS STATUS")
        print("="*70)
        
        # Get all orders
        all_orders = Order.query.order_by(Order.created_at.desc()).limit(20).all()
        
        print(f"\n📊 Total Orders in Main DB: {Order.query.count()}")
        print(f"\n🔍 Checking last 20 orders:\n")
        
        cutoff_date = get_ph_time() - timedelta(days=1)
        
        for order in all_orders:
            age_days = (get_ph_time() - order.created_at).days if order.created_at else 0
            age_hours = (get_ph_time() - order.created_at).total_seconds() / 3600 if order.created_at else 0
            
            is_eligible = (
                order.status in ['COMPLETED', 'CANCELLED'] and 
                order.created_at and 
                order.created_at < cutoff_date
            )
            
            status_icon = "✅" if is_eligible else "❌"
            
            print(f"{status_icon} Order #{order.id} ({order.order_code})")
            print(f"   Status: {order.status}")
            print(f"   Payment: {order.payment_status}")
            print(f"   Created: {order.created_at}")
            print(f"   Age: {age_days} days ({age_hours:.1f} hours)")
            print(f"   Eligible: {'YES' if is_eligible else 'NO'}")
            
            if not is_eligible:
                reasons = []
                if order.status not in ['COMPLETED', 'CANCELLED']:
                    reasons.append(f"Status is '{order.status}' (needs COMPLETED or CANCELLED)")
                if not order.created_at:
                    reasons.append("No created_at timestamp")
                elif order.created_at >= cutoff_date:
                    reasons.append(f"Too recent (less than 1 day old)")
                
                print(f"   Reason: {', '.join(reasons)}")
            print()
        
        # Count by status
        print("\n📊 ORDERS BY STATUS:")
        from sqlalchemy import func
        status_counts = db.session.query(
            Order.status, 
            func.count(Order.id)
        ).group_by(Order.status).all()
        
        for status, count in status_counts:
            print(f"   {status}: {count}")
        
        # Count eligible
        eligible_count = Order.query.filter(
            Order.status.in_(['COMPLETED', 'CANCELLED']),
            Order.created_at < cutoff_date
        ).count()
        
        print(f"\n🎯 ELIGIBLE FOR ARCHIVE: {eligible_count}")
        
        print("\n" + "="*70)
        print("💡 KEY INSIGHT:")
        print("   Orders must be COMPLETED or CANCELLED status")
        print("   AND older than 1 day to be archived.")
        print("   ")
        print("   'Ready' status means order is prepared but NOT completed!")
        print("   'Paid' payment status is different from order status!")
        print("="*70)

if __name__ == '__main__':
    from models import db
    check_orders()
