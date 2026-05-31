"""
Execute archive job to move eligible data from Main DB to Archive DB
"""
from app import app
from archive import get_archive_manager

def run_archive():
    with app.app_context():
        manager = get_archive_manager()
        
        if not manager:
            print("❌ Archive system not initialized!")
            return
        
        print("\n" + "="*70)
        print("  RUNNING ARCHIVE JOB")
        print("="*70)
        print("\n🚀 Starting archive process...")
        print("   This will COPY eligible records to Archive DB")
        print("   and REMOVE them from Main DB\n")
        
        # Get stats before
        stats_before = manager.get_stats()
        print("📊 BEFORE ARCHIVING:")
        print(f"   Main DB - Inventory Logs: {stats_before['main']['inventory_logs']}")
        print(f"   Main DB - Notifications: {stats_before['main']['notifications']}")
        print(f"   Archive DB - Inventory Logs: {stats_before['archive']['inventory_logs']}")
        print(f"   Archive DB - Notifications: {stats_before['archive']['notifications']}")
        
        print(f"\n🎯 ELIGIBLE TO ARCHIVE:")
        print(f"   Inventory Logs: {stats_before['eligible_now']['inventory_logs']}")
        print(f"   Notifications: {stats_before['eligible_now']['notifications']}")
        
        # Run the archive job
        print("\n⏳ Processing...")
        result = manager.run(triggered_by='manual_script', user_id=None, dry_run=False)
        
        if result['success']:
            print("\n✅ ARCHIVE COMPLETED SUCCESSFULLY!")
            print("\n📋 Summary:")
            summary = result['summary']
            print(f"   Orders archived:           {summary.get('orders', 0)}")
            print(f"   Reservations archived:     {summary.get('reservations', 0)}")
            print(f"   Audit Logs archived:       {summary.get('audit_logs', 0)}")
            print(f"   Inventory Logs archived:   {summary.get('inventory_logs', 0)}")
            print(f"   Notifications archived:    {summary.get('notifications', 0)}")
            
            # Get stats after
            stats_after = manager.get_stats()
            print("\n📊 AFTER ARCHIVING:")
            print(f"   Main DB - Inventory Logs: {stats_after['main']['inventory_logs']}")
            print(f"   Main DB - Notifications: {stats_after['main']['notifications']}")
            print(f"   Archive DB - Inventory Logs: {stats_after['archive']['inventory_logs']}")
            print(f"   Archive DB - Notifications: {stats_after['archive']['notifications']}")
            
            print("\n💾 Data successfully moved to Archive Database!")
            print("   Staff will no longer see these old records in their dashboards")
            print("   But they are safely stored in the Archive Database for history")
            
        else:
            print(f"\n❌ ARCHIVE FAILED: {result.get('error')}")
        
        print("\n" + "="*70)

if __name__ == '__main__':
    run_archive()
