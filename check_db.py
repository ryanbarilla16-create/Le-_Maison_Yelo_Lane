import sqlite3
conn = sqlite3.connect('instance/lemaisondb.db')
rows = conn.execute('SELECT id, dining_option, status, delivery_status, rider_id FROM "order" ORDER BY id DESC LIMIT 5').fetchall()
print("ID | Dining Option | Status | Delivery Status | Rider ID | Branch")
for row in rows:
    print(row)
