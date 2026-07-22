import sqlite3
conn = sqlite3.connect('instance/lemaisondb.db')
conn.execute('INSERT INTO "order" (dining_option, status, delivery_status, rider_id, total_amount) VALUES ("DELIVERY", "PENDING", NULL, NULL, 100.0)')
conn.commit()
print(conn.execute('SELECT id, dining_option, status, delivery_status, rider_id FROM "order" ORDER BY id DESC LIMIT 1').fetchone())
