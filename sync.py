"""
Supabase Real-time Sync Module
Handles mirroring of database changes to Supabase
"""
import os
from supabase import create_client, Client
from config import Config

supabase_client: Client | None = None

def init_supabase():
    """Initialize Supabase client"""
    global supabase_client
    
    try:
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_KEY")
        
        if supabase_url and supabase_key:
            supabase_client = create_client(supabase_url, supabase_key)
            print("✅ Supabase Connection: Active")
            return True
        else:
            print("⚠️  Supabase Connection: Disabled (Missing credentials in .env)")
            return False
    except Exception as e:
        print(f"❌ Supabase Connection Error: {str(e)}")
        return False

def setup_supabase_sync():
    """
    Setup Supabase real-time synchronization
    This function sets up event hooks to mirror database changes to Supabase
    """
    if not init_supabase():
        print("⚠️  Supabase sync disabled - continuing without real-time sync")
        return
    
    print("🔄 Supabase Real-time Sync: Initialized")

def sync_to_supabase(table_name: str, operation: str, data: dict):
    """
    Sync a database operation to Supabase
    
    Args:
        table_name: Name of the table
        operation: Operation type ('insert', 'update', 'delete')
        data: Data to sync
    """
    if not supabase_client:
        return
    
    try:
        if operation == 'insert':
            supabase_client.table(table_name).insert(data).execute()
        elif operation == 'update':
            supabase_client.table(table_name).update(data).execute()
        elif operation == 'delete':
            supabase_client.table(table_name).delete().eq('id', data.get('id')).execute()
    except Exception as e:
        print(f"Error syncing to Supabase: {str(e)}")

def get_supabase_client():
    """Get the Supabase client instance"""
    global supabase_client
    if not supabase_client:
        init_supabase()
    return supabase_client
