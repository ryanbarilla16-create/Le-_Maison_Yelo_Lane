import sqlite3
conn = sqlite3.connect('instance/lemaisondb.db')
try:
    rows = conn.execute('SELECT id, dining_option, status, delivery_status, rider_id, branch FROM "order" WHERE dining_option = "DELIVERY" ORDER BY id DESC').fetchall()
    for row in rows:
        print(row)
    if not rows:
        print("No DELIVERY orders found in the database.")
except Exception as e:
    print(f"Error: {e}")
