#!/usr/bin/env python3
"""
Monitor archive database health in real-time.
"""

import os
import time
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

load_dotenv()

def get_connection_stats(engine):
    """Get connection pool statistics."""
    pool = engine.pool
    return {
        'size': pool.size(),
        'checked_in': pool.checkedin(),
        'checked_out': pool.checkedout(),
        'overflow': pool.overflow(),
        'total': pool.size() + pool.overflow(),
    }

def monitor_health(interval=5, duration=60):
    """Monitor database health for a specified duration."""
    
    main_db_url = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL")
    
    if not main_db_url:
        print("❌ No DATABASE_URL found")
        return
    
    # Fix URL
    if main_db_url.startswith("postgres://"):
        main_db_url = main_db_url.replace("postgres://", "postgresql://", 1)
    
    if "postgresql" in main_db_url and "sslmode" not in main_db_url:
        main_db_url += ("&" if "?" in main_db_url else "?") + "sslmode=require"
    
    print(f"📊 Monitoring database health...")
    print(f"⏱️  Interval: {interval}s, Duration: {duration}s")
    print(f"🔗 Database: {main_db_url[:50]}...")
    print()
    
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
    
    start_time = time.time()
    iteration = 0
    errors = 0
    
    print("Time      | Status | Pool Stats (Size/In/Out/Overflow) | Query Time")
    print("-" * 80)
    
    while time.time() - start_time < duration:
        iteration += 1
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        try:
            # Test query with timing
            query_start = time.time()
            with engine.connect() as conn:
                # Test main database
                conn.execute(text("SELECT 1"))
                
                # Test archive schema
                result = conn.execute(text(
                    "SELECT COUNT(*) FROM archive.archive_run"
                ))
                count = result.scalar()
                
            query_time = (time.time() - query_start) * 1000  # Convert to ms
            
            # Get pool stats
            stats = get_connection_stats(engine)
            
            status = "✅ OK"
            pool_info = f"{stats['size']}/{stats['checked_in']}/{stats['checked_out']}/{stats['overflow']}"
            
            print(f"{timestamp} | {status:6} | {pool_info:33} | {query_time:6.2f}ms")
            
        except OperationalError as e:
            errors += 1
            print(f"{timestamp} | ❌ ERR | Connection failed | {str(e)[:40]}")
        except Exception as e:
            errors += 1
            print(f"{timestamp} | ⚠️  ERR | Unexpected error | {str(e)[:40]}")
        
        time.sleep(interval)
    
    print("-" * 80)
    print(f"\n📊 Summary:")
    print(f"   Total checks: {iteration}")
    print(f"   Successful: {iteration - errors}")
    print(f"   Failed: {errors}")
    print(f"   Success rate: {((iteration - errors) / iteration * 100):.1f}%")
    
    if errors == 0:
        print("\n✅ All health checks passed!")
    elif errors < iteration * 0.1:
        print(f"\n⚠️  Some errors detected ({errors}/{iteration})")
    else:
        print(f"\n❌ High error rate detected ({errors}/{iteration})")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Monitor archive database health')
    parser.add_argument('--interval', type=int, default=5, help='Check interval in seconds (default: 5)')
    parser.add_argument('--duration', type=int, default=60, help='Total duration in seconds (default: 60)')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("Archive Database Health Monitor")
    print("=" * 80)
    print()
    
    try:
        monitor_health(interval=args.interval, duration=args.duration)
    except KeyboardInterrupt:
        print("\n\n⏹️  Monitoring stopped by user")
    
    print()
    print("=" * 80)
