import sqlite3
import os

db_path = 'lemaisondb.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT email, role, status FROM user")
        users = cursor.fetchall()
        print("Users in database:")
        for user in users:
            print(f"Email: {user[0]}, Role: {user[1]}, Status: {user[2]}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()
else:
    print("Database file not found.")
