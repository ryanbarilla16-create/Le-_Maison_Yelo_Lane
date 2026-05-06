"""Quick migration: Add branch columns to existing PostgreSQL tables."""
from app import app, db
from sqlalchemy import text

with app.app_context():
    stmts = [
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS branch VARCHAR(50) DEFAULT NULL',
        "ALTER TABLE \"order\" ADD COLUMN IF NOT EXISTS branch VARCHAR(50) DEFAULT 'Pagsanjan'",
        "ALTER TABLE reservation ADD COLUMN IF NOT EXISTS branch VARCHAR(50) DEFAULT 'Pagsanjan'",
    ]
    for s in stmts:
        try:
            db.session.execute(text(s))
            print(f"  [OK] {s[:60]}...")
        except Exception as e:
            print(f"  [SKIP] {e}")
    db.session.commit()
    print("\n[DONE] Branch columns migration complete!")
