import sqlite3
import os

db_path = os.path.join('instance', 'lemaisondb.db')
try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("ALTER TABLE delivery_area ADD COLUMN branch VARCHAR(50) DEFAULT 'Pagsanjan'")
    conn.commit()
    conn.close()
    print("Successfully added 'branch' column to 'delivery_area' table.")
except Exception as e:
    print(f"Error or column already exists: {e}")
