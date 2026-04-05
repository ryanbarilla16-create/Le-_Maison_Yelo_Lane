"""
Migration: Add reservation_id column to order table
Run once to update the existing database schema.
"""
from app import app, db
import sqlalchemy as sa

with app.app_context():
    with db.engine.connect() as conn:
        # Check if column already exists
        inspector = sa.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('order')]
        
        if 'reservation_id' not in columns:
            conn.execute(sa.text('ALTER TABLE "order" ADD COLUMN reservation_id INTEGER REFERENCES reservation(id)'))
            conn.commit()
            print("✅ reservation_id column added to order table.")
        else:
            print("ℹ️  reservation_id column already exists. No changes made.")
