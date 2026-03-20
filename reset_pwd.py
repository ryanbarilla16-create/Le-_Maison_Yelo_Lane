from app import app, db
from models import User

with app.app_context():
    admin = User.query.filter_by(email='ryan.admin@gmail.com').first()
    if admin:
        admin.set_password('admin123')
        db.session.commit()
        print(f"Password for {admin.email} successfully reset to: admin123")
    else:
        print("Admin user ryan.admin@gmail.com not found!")
