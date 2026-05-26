import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
db_url = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL")

conn = psycopg2.connect(db_url)
cur = conn.cursor()

# Search for any ingredient matching 'milk' case-insensitively
cur.execute("SELECT id, name, category, supplier_id FROM ingredient WHERE name ILIKE '%milk%'")
rows = cur.fetchall()
print("Matches for 'milk':")
for r in rows:
    print(r)
    
# Let's search for ingredients with NULL supplier_id
cur.execute("SELECT id, name, category FROM ingredient WHERE supplier_id IS NULL")
rows_null = cur.fetchall()
print("\nIngredients with NULL supplier_id:")
for r in rows_null:
    print(r)

cur.close()
conn.close()
