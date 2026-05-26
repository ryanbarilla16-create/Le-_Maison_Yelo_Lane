import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

db_url = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL")
print("Connecting to database URL:", db_url)

if not db_url:
    print("No database URL set in environment!")
else:
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        # Check tables
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        tables = [r[0] for r in cur.fetchall()]
        print("Tables in public schema:", tables)
        
        # Count suppliers
        if 'supplier' in tables:
            cur.execute("SELECT COUNT(*) FROM supplier")
            count = cur.fetchone()[0]
            print("Suppliers count:", count)
            
            # Fetch all suppliers and their categories
            cur.execute("SELECT id, name, category FROM supplier ORDER BY name")
            for row in cur.fetchall():
                print(f"  Supplier ID={row[0]} | Name={row[1]} | Category={row[2]}")
        else:
            print("No supplier table found!")
            
        cur.close()
        conn.close()
    except Exception as e:
        print("Error connecting/querying database:", e)
