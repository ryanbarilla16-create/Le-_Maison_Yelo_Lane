from app import app, db
import sqlalchemy
try:
    with app.app_context():
        db.session.execute(sqlalchemy.text('ALTER TABLE reservation ADD COLUMN duration INTEGER DEFAULT 2;'))
        db.session.commit()
        print('SUCCESS')
except Exception as e:
    print(e)
