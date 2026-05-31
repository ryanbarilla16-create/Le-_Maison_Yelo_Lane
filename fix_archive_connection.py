#!/usr/bin/env python3
"""
Fix archive database connection issues by recreating the schema and tables.
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

load_dotenv()

def fix_archive_connection():
    """Fix archive database connection by ensuring schema and tables exist."""
    
    # Get database URL
    main_db_url = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL")
    
    if not main_db_url:
        print("❌ No DATABASE_URL or NEON_DATABASE_URL found")
        return False
    
    # Fix postgres:// to postgresql://
    if main_db_url.startswith("postgres://"):
        main_db_url = main_db_url.replace("postgres://", "postgresql://", 1)
    
    # Add SSL mode if needed
    if "postgresql" in main_db_url and "sslmode" not in main_db_url:
        main_db_url += ("&" if "?" in main_db_url else "?") + "sslmode=require"
    
    print(f"📊 Connecting to: {main_db_url[:50]}...")
    
    try:
        engine = create_engine(
            main_db_url,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=10,
            max_overflow=20,
            connect_args={
                "connect_timeout": 10,
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5,
            }
        )
        
        with engine.connect() as conn:
            print("✅ Connected to database")
            
            # Create archive schema if it doesn't exist
            print("📦 Creating archive schema...")
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS archive"))
            conn.commit()
            print("✅ Archive schema ready")
            
            # Now initialize the app and create tables
            print("📋 Creating archive tables...")
            
        # Use Flask app context to create tables
        from app import app
        from models import db
        
        with app.app_context():
            # Create all archive tables
            db.create_all(bind_key='archive')
            print("✅ Archive tables created")
            
            # Verify tables exist
            from archive.models import ArchiveRun
            count = ArchiveRun.query.count()
            print(f"✅ Verified: Found {count} archive run records")
        
        print("\n✅ Archive database fixed successfully!")
        return True
        
    except OperationalError as e:
        print(f"\n❌ Connection error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Fix Archive Database Connection")
    print("=" * 60)
    print()
    
    success = fix_archive_connection()
    
    print()
    print("=" * 60)
    if success:
        print("✅ Fix completed successfully")
        print("You can now use the archive system")
    else:
        print("❌ Fix failed - please check the errors above")
    print("=" * 60)
