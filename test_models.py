from app import app
from models import db, MenuItem, Reservation, Order, Review, User
with app.app_context():
    try:
        # Check all models that are queried in the index route
        MenuItem.query.limit(1).all()
        Reservation.query.limit(1).all()
        Order.query.limit(1).all()
        Review.query.limit(1).all()
        User.query.limit(1).all()
        print("Model queries successful.")
    except Exception as e:
        print(f"Model query failed: {e}")
