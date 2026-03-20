from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from utils import get_ph_time

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    middle_name = db.Column(db.String(50), nullable=True)
    phone_number = db.Column(db.String(15), nullable=True)
    last_name = db.Column(db.String(50), nullable=False)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    birthday = db.Column(db.Date, nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    profile_picture_url = db.Column(db.String(500), nullable=True)
    
    # Status and Roles
    status = db.Column(db.String(20), default='PENDING') # PENDING, ACTIVE, REJECTED
    role = db.Column(db.String(20), default='USER') # USER, ADMIN, CASHIER, INVENTORY_STAFF, RIDER
    
    # Email Verification
    is_verified = db.Column(db.Boolean, default=False)
    otp_code = db.Column(db.String(6), nullable=True)
    otp_created_at = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    guest_count = db.Column(db.Integer, nullable=False)
    occasion = db.Column(db.String(50), nullable=True)
    booking_type = db.Column(db.String(20), nullable=False) # REGULAR, EXCLUSIVE
    
    status = db.Column(db.String(20), default='PENDING') # PENDING, CONFIRMED, REJECTED, COMPLETED
    created_at = db.Column(db.DateTime, default=get_ph_time)

    user = db.relationship('User', backref=db.backref('reservations', lazy=True))

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    image_url = db.Column(db.String(255), nullable=True)
    is_available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_ph_time)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    customer_name = db.Column(db.String(100), nullable=True)  # For walk-in customers
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default='PENDING') # PENDING, PREPARING, COMPLETED, CANCELLED
    payment_status = db.Column(db.String(20), default='UNPAID') # UNPAID, PAID
    dining_option = db.Column(db.String(20), default='DINE_IN') # DINE_IN, TAKE_OUT, DELIVERY
    payment_method = db.Column(db.String(20), default='COUNTER') # COUNTER, ONLINE
    amount_tendered = db.Column(db.Numeric(10, 2), nullable=True)
    change_amount = db.Column(db.Numeric(10, 2), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    delivery_address = db.Column(db.Text, nullable=True)
    delivery_status = db.Column(db.String(20), nullable=True)  # WAITING, PICKED_UP, ON_THE_WAY, DELIVERED
    rider_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    xendit_invoice_id = db.Column(db.String(255), nullable=True)
    xendit_invoice_url = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=get_ph_time)

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('orders', lazy=True))
    rider = db.relationship('User', foreign_keys=[rider_id], backref=db.backref('deliveries', lazy=True))
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price_at_time = db.Column(db.Numeric(10, 2), nullable=False)

    menu_item = db.relationship('MenuItem')

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=True) # Reference to the specific order being reviewed
    rating = db.Column(db.Integer, nullable=False) # 1 to 5
    comment = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='PENDING') # PENDING, APPROVED, REJECTED
    created_at = db.Column(db.DateTime, default=get_ph_time)

    user = db.relationship('User', backref=db.backref('reviews', lazy=True))

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(30), default='SYSTEM')  # ORDER, RESERVATION, DELIVERY, SYSTEM
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=get_ph_time)

    user = db.relationship('User', backref=db.backref('notifications', lazy=True, order_by='Notification.created_at.desc()'))
