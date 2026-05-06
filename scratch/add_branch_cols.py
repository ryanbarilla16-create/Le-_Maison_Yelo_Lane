import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        db.session.execute(text("ALTER TABLE ingredient ADD COLUMN branch VARCHAR(50) DEFAULT 'Pagsanjan'"))
        db.session.commit()
        print('Added branch to ingredient')
    except Exception as e:
        print('Error ingredient:', e)
        db.session.rollback()
        
    try:
        db.session.execute(text("ALTER TABLE menu_item ADD COLUMN branch VARCHAR(50) DEFAULT 'Pagsanjan'"))
        db.session.commit()
        print('Added branch to menu_item')
    except Exception as e:
        print('Error menu_item:', e)
        db.session.rollback()
