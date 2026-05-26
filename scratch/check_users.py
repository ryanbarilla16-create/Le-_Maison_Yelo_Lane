from app import app
from models import User

with app.app_context():
    users = User.query.filter(User.first_name.ilike('%Ryan%')).all()
    for u in users:
        print(f"ID: {u.id}, Name: {u.first_name} {u.last_name}, Role: {u.role}, Status: {u.status}")
