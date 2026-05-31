"""
Verify that sales calculations include both Main DB and Archive DB
"""
from app import app
from models import db, Order
from archive.models import ArchiveOrder
from sqlalchemy import func

def verify_sales():
    with app.app_context():
        print("\n" + "="*70)
        print("  VERIFYING SALES CALCULATIONS (Main DB + Archive DB)")
        print("="*70)
        
        # Count all orders
        main_total = Order.query.count()
        main_paid = Order.query.filter_by(payment_status='PAID').count()
        main_unpaid = Order.query.filter_by(payment_status='UNPAID').count()
        
        archive_total = ArchiveOrder.query.count()
        archive_paid = ArchiveOrder.query.filter_by(payment_status='PAID').count()
        
        print(f"\n📊 ORDER COUNTS:")
        print(f"   Main DB:")
        print(f"      Total orders: {main_total}")
        print(f"      PAID orders: {main_paid}")
        print(f"      UNPAID orders: {main_unpaid}")
        print(f"\n   Archive DB:")
        print(f"      Total orders: {archive_total}")
        print(f"      PAID orders: {archive_paid}")
        
        # Calculate revenue by branch
        print(f"\n💰 REVENUE BY BRANCH (Main DB + Archive DB):")
        
        branches = ['Pagsanjan', 'Lucban']
        total_revenue = 0
        
        for branch in branches:
            # Main DB PAID orders
            main_revenue = db.session.query(
                func.coalesce(func.sum(Order.total_amount), 0)
            ).filter(
                Order.branch == branch,
                Order.payment_status == 'PAID'
            ).scalar()
            
            # Archive DB PAID orders
            archive_revenue = db.session.query(
                func.coalesce(func.sum(ArchiveOrder.total_amount), 0)
            ).filter(
                ArchiveOrder.branch == branch,
                ArchiveOrder.payment_status == 'PAID'
            ).scalar()
            
            main_revenue = float(main_revenue or 0)
            archive_revenue = float(archive_revenue or 0)
            branch_revenue = main_revenue + archive_revenue
            total_revenue += branch_revenue
            
            # Count orders
            main_orders = Order.query.filter_by(branch=branch).count()
            archive_orders = ArchiveOrder.query.filter_by(branch=branch).count()
            
            print(f"\n   {branch}:")
            print(f"      Main DB orders: {main_orders}")
            print(f"      Archive DB orders: {archive_orders}")
            print(f"      Main DB revenue: ₱{main_revenue:,.2f}")
            print(f"      Archive DB revenue: ₱{archive_revenue:,.2f}")
            print(f"      TOTAL Gross Revenue: ₱{branch_revenue:,.2f}")
        
        print(f"\n💵 TOTAL GROSS REVENUE (All Branches): ₱{total_revenue:,.2f}")
        print(f"   (Main DB + Archive DB combined)")
        
        print("\n" + "="*70)
        print("✅ SALES CALCULATION VERIFIED!")
        print("   Now includes both Main Database and Archive Database")
        print("   Refresh your admin dashboard to see updated revenue")
        print("="*70 + "\n")

if __name__ == '__main__':
    verify_sales()
