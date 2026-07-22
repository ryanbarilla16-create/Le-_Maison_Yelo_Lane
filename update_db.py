import sqlite3
conn = sqlite3.connect('instance/lemaisondb.db')
conn.execute('UPDATE "order" SET branch = "Magdalena" WHERE id = 1')
conn.commit()
