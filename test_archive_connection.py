#!/usr/bin/env python3
"""
Test script to verify archive database connection and schema.
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import OperationalError

load_dotenv()

def test_archive_connection():
    """Test the archive database connection and schema."""
    
    # Get database URLs
    main_db_url = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL")
    archive_db_url = os.environ.get("ARCHIVE_DATABASE_URL")
    
    if not main_db_url:
        print("❌ No DATABASE_URL or NEON_DATABASE_URL found in environment")
        return False
    
    # Fix postgres:// to postgresql://
    if main_db_url.startswith("postgres://"):
        main_db_url = main_db_url.replace("postgres://", "postgresql://", 1)
    
    # Add SSL mode if needed
    if "postgresql" in main_db_url and "sslmode" not in main_db_url:
        main_db_url += ("&" if "?" in main_db_url else "?") + "sslmode=require"
    
    print(f"📊 Main DB URL: {main_db_url[:50]}...")
    
    # Determine archive strategy
    if archive_db_url:
        print(f"📦 Archive DB URL: {archive_db_url[:50]}... (separate database)")
        test_url = archive_db_url
        use_schema = False
    elif "postgresql" in main_db_url:
        print("📦 Archive strategy: Using 'archive' schema on main database")
        test_url = main_db_url
        use_schema = True
    else:
        print("📦 Archive strategy: SQLite separate file")
        test_url = "sqlite:///lemaison_archive.db"
        use_schema = False
    
    # Test connection
    try:
        engine = create_engine(
            test_url,
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args={
                "connect_timeout": 10,
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5,
            } if "postgresql" in test_url else {}
        )
        
        with engine.connect() as conn:
            print("✅ Database connection successful")
            
            # Test basic query
            result = conn.execute(text("SELECT 1"))
            print("✅ Basic query successful")
            
            # Check if archive schema exists (for PostgreSQL)
            if use_schema:
                result = conn.execute(text(
                    "SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'archive'"
                ))
                schema_exists = result.fetchone() is not None
                
                if schema_exists:
                    print("✅ Archive schema exists")
                    
                    # List tables in archive schema
                    result = conn.execute(text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'archive' ORDER BY table_name"
                    ))
                    tables = [row[0] for row in result.fetchall()]
                    
                    if tables:
                        print(f"✅ Found {len(tables)} tables in archive schema:")
                        for table in tables:
                            print(f"   - {table}")
                    else:
                        print("⚠️  Archive schema exists but no tables found")
                else:
                    print("⚠️  Archive schema does not exist - will be created on first run")
            
            # Check archive_run table
            inspector = inspect(engine)
            if use_schema:
                tables = inspector.get_table_names(schema='archive')
                if 'archive_run' in tables:
                    print("✅ archive_run table exists")
                    
                    # Count records
                    result = conn.execute(text("SELECT COUNT(*) FROM archive.archive_run"))
                    count = result.scalar()
                    print(f"   Found {count} archive run records")
                else:
                    print("⚠️  archive_run table not found")
            else:
                tables = inspector.get_table_names()
                if 'archive_run' in tables:
                    print("✅ archive_run table exists")
                    result = conn.execute(text("SELECT COUNT(*) FROM archive_run"))
                    count = result.scalar()
                    print(f"   Found {count} archive run records")
                else:
                    print("⚠️  archive_run table not found")
        
        print("\n✅ All connection tests passed!")
        return True
        
    except OperationalError as e:
        print(f"\n❌ Connection error: {e}")
        print("\nTroubleshooting tips:")
        print("1. Check if your database server is running")
        print("2. Verify your DATABASE_URL is correct")
        print("3. Check if SSL/TLS settings are correct")
        print("4. Ensure your IP is whitelisted (for cloud databases)")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Archive Database Connection Test")
    print("=" * 60)
    print()
    
    success = test_archive_connection()
    
    print()
    print("=" * 60)
    if success:
        print("✅ Test completed successfully")
    else:
        print("❌ Test failed - please check the errors above")
    print("=" * 60)
