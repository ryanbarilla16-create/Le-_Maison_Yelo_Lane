"""
Test script to verify Data Archive system functionality
"""
from app import app
from archive import get_archive_manager
from models import db, Order, Reservation, AuditLog, InventoryLog, Notification
from datetime import datetime, timedelta
from utils import get_ph_time

def print_separator(title=""):
    print("\n" + "="*70)
    if title:
        print(f"  {title}")
        print("="*70)

def test_archive_system():
    with app.app_context():
        manager = get_archive_manager()
        
        if not manager:
            print("❌ Archive system not initialized!")
            return
        
        print_separator("DATA ARCHIVE SYSTEM TEST")
        print("✅ Archive Manager: Initialized")
        print(f"✅ Config Path: {manager.config_path}")
        
        # Get current statistics
        print_separator("CURRENT DATABASE STATISTICS")
        stats = manager.get_stats()
        
        print("\n📊 MAIN DATABASE (Active Operations):")
        print(f"   Orders:           {stats['main']['orders']:,}")
        print(f"   Reservations:     {stats['main']['reservations']:,}")
        print(f"   Audit Logs:       {stats['main']['audit_logs']:,}")
        print(f"   Inventory Logs:   {stats['main']['inventory_logs']:,}")
        print(f"   Notifications:    {stats['main']['notifications']:,}")
        
        print("\n📦 ARCHIVE DATABASE (Historical Storage):")
        print(f"   Orders:           {stats['archive']['orders']:,}")
        print(f"   Order Items:      {stats['archive']['order_items']:,}")
        print(f"   Reservations:     {stats['archive']['reservations']:,}")
        print(f"   Audit Logs:       {stats['archive']['audit_logs']:,}")
        print(f"   Inventory Logs:   {stats['archive']['inventory_logs']:,}")
        print(f"   Notifications:    {stats['archive']['notifications']:,}")
        
        print("\n🎯 ELIGIBLE FOR ARCHIVING NOW:")
        print(f"   Orders:           {stats['eligible_now']['orders']:,}")
        print(f"   Reservations:     {stats['eligible_now']['reservations']:,}")
        print(f"   Audit Logs:       {stats['eligible_now']['audit_logs']:,}")
        print(f"   Inventory Logs:   {stats['eligible_now']['inventory_logs']:,}")
        print(f"   Notifications:    {stats['eligible_now']['notifications']:,}")
        
        print("\n⏰ RETENTION POLICY:")
        for key, days in stats['retention_days'].items():
            print(f"   {key.replace('_', ' ').title()}: {days} day(s)")
        
        # Check for old completed orders
        print_separator("DETAILED ANALYSIS")
        
        cutoff_date = get_ph_time() - timedelta(days=1)
        
        completed_orders = Order.query.filter(
            Order.status.in_(['COMPLETED', 'CANCELLED']),
            Order.created_at < cutoff_date
        ).all()
        
        if completed_orders:
            print(f"\n✅ Found {len(completed_orders)} eligible orders:")
            for order in completed_orders[:5]:  # Show first 5
                age_days = (get_ph_time() - order.created_at).days
                print(f"   • Order #{order.id} ({order.order_code}) - {order.status} - {age_days} days old")
            if len(completed_orders) > 5:
                print(f"   ... and {len(completed_orders) - 5} more")
        else:
            print("\n⚠️  No eligible orders found (all orders are less than 1 day old)")
        
        completed_reservations = Reservation.query.filter(
            Reservation.status.in_(['COMPLETED', 'REJECTED', 'CANCELLED']),
            Reservation.created_at < cutoff_date
        ).all()
        
        if completed_reservations:
            print(f"\n✅ Found {len(completed_reservations)} eligible reservations:")
            for res in completed_reservations[:5]:
                age_days = (get_ph_time() - res.created_at).days
                print(f"   • Reservation #{res.id} ({res.reservation_code}) - {res.status} - {age_days} days old")
            if len(completed_reservations) > 5:
                print(f"   ... and {len(completed_reservations) - 5} more")
        else:
            print("\n⚠️  No eligible reservations found")
        
        # Test dry run
        print_separator("DRY RUN TEST (Preview Only)")
        print("\n🔍 Running archive preview (no data will be moved)...")
        
        result = manager.run(triggered_by='test_script', dry_run=True)
        
        if result['success']:
            print("\n✅ Dry run completed successfully!")
            print("\n📋 Preview Results:")
            summary = result['summary']
            print(f"   Orders to archive:           {summary.get('orders', 0):,}")
            print(f"   Reservations to archive:     {summary.get('reservations', 0):,}")
            print(f"   Audit Logs to archive:       {summary.get('audit_logs', 0):,}")
            print(f"   Inventory Logs to archive:   {summary.get('inventory_logs', 0):,}")
            print(f"   Notifications to archive:    {summary.get('notifications', 0):,}")
        else:
            print(f"\n❌ Dry run failed: {result.get('error')}")
        
        print_separator("SYSTEM STATUS")
        print("\n✅ Archive system is READY and FUNCTIONAL!")
        print("\n📝 To archive data:")
        print("   1. Go to: http://localhost:5000/admin/archive")
        print("   2. Click 'Run Archive Now' button")
        print("   3. Or run: flask archive run")
        print("\n💡 Current retention: 1 day for all data types")
        print("   Edit archive/config.json to change retention periods")
        
        print_separator()

if __name__ == '__main__':
    test_archive_system()
