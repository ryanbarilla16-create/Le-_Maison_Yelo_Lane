import sqlite3, os

for path in [
    r'instance\lemaisondb.db',
    r'instance\lemaison.db',
    r'lemaisondb.db',
]:
    if os.path.exists(path):
        c = sqlite3.connect(path)
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        size = os.path.getsize(path)
        print(f"DB: {path}  size={size}  tables={tables}")
        c.close()
    else:
        print(f"NOT FOUND: {path}")
