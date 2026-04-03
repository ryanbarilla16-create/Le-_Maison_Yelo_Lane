from app import app
from models import db
from sqlalchemy import text

def update_db():
    with app.app_context():
        # Create new tables
        try:
            db.create_all()
            print("Created all missing tables.")
        except Exception as e:
            print("Error creating tables:", e)

        # Alter User
        try:
            db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN wallet_balance NUMERIC(10, 2) DEFAULT 0;"))
            db.session.commit()
            print("Added wallet_balance to user table.")
        except Exception as e:
            print("Error altering user:", e)

        # Alter Order
        try:
            db.session.execute(text("ALTER TABLE \"order\" ADD COLUMN delivery_fee NUMERIC(10, 2) DEFAULT 0;"))
            db.session.commit()
            print("Added delivery_fee to order table.")
        except Exception as e:
            print("Error altering order (delivery_fee):", e)

        try:
            db.session.execute(text("ALTER TABLE \"order\" ADD COLUMN proof_of_delivery_url VARCHAR(255);"))
            db.session.commit()
            print("Added proof_of_delivery_url to order table.")
        except Exception as e:
            print("Error altering order (proof):", e)

        # Alter Ingredient
        try:
            db.session.execute(text("ALTER TABLE ingredient ADD COLUMN expiration_date DATE;"))
            db.session.commit()
            print("Added expiration_date to ingredient table.")
        except Exception as e:
            print("Error altering ingredient:", e)

if __name__ == "__main__":
    update_db()
