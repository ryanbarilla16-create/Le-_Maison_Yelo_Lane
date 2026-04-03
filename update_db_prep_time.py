import sqlite3
import os

db_path = 'instance/database.db'
if not os.path.exists(db_path):
    print("Database not found.")
    exit()

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE 'order' ADD COLUMN prep_start_at DATETIME")
    print("Added prep_start_at to Order table.")
except sqlite3.OperationalError:
    print("prep_start_at already exists or error.")

try:
    cursor.execute("ALTER TABLE 'order' ADD COLUMN prep_end_at DATETIME")
    print("Added prep_end_at to Order table.")
except sqlite3.OperationalError:
    print("prep_end_at already exists or error.")

conn.commit()
conn.close()
print("Migration completed.")
