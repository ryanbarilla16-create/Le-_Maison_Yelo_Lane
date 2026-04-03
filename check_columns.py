from app import app
from models import db
from sqlalchemy import text

def check_order_table():
    with app.app_context():
        try:
            # Query one row to see columns
            result = db.session.execute(text("SELECT * FROM \"order\" LIMIT 1;"))
            print(f"Columns in 'order' table: {result.keys()}")
        except Exception as e:
            print(f"Error querying 'order': {e}")

if __name__ == "__main__":
    check_order_table()
