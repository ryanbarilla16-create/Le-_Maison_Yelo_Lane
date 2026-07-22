import sqlite3
conn = sqlite3.connect('instance/app.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
for row in c.fetchall():
    print(row)
