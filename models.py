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
    role = db.Column(db.String(20), default='USER', index=True) # USER, ADMIN, CASHIER, INVENTORY_STAFF, RIDER
    
    # Email Verification
    is_verified = db.Column(db.Boolean, default=False)
    otp_code = db.Column(db.String(6), nullable=True)
    otp_created_at = db.Column(db.DateTime, nullable=True)
    wallet_balance = db.Column(db.Numeric(10, 2), default=0)

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
    duration = db.Column(db.Integer, default=2) # duration in hours
    
    status = db.Column(db.String(20), default='PENDING', index=True) # PENDING, CONFIRMED, REJECTED, COMPLETED
    table_number = db.Column(db.String(20), nullable=True) # Assigned by admin
    cancellation_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=get_ph_time, index=True)

    user = db.relationship('User', backref=db.backref('reservations', lazy=True))

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    category = db.Column(db.String(50), nullable=False, index=True)
    image_url = db.Column(db.String(255), nullable=True)
    is_available = db.Column(db.Boolean, default=True, index=True)
    is_deleted = db.Column(db.Boolean, default=False, index=True) # Soft delete
    created_at = db.Column(db.DateTime, default=get_ph_time)
    
    @property
    def is_out_of_stock(self):
        """Checks if ingredients for this menu item are sufficient.
        Items with NO recipe defined are considered out of stock
        because the kitchen cannot prepare them without a recipe."""
        if not self.ingredients:
            # No recipe = cannot be prepared = out of stock
            return True
        for mi_ingredient in self.ingredients:
            if float(mi_ingredient.ingredient.stock_qty) < float(mi_ingredient.quantity_needed):
                return True
        return False

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    customer_name = db.Column(db.String(100), nullable=True)  # For walk-in customers
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default='PENDING', index=True) # PENDING, PREPARING, COMPLETED, CANCELLED
    payment_status = db.Column(db.String(20), default='UNPAID') # UNPAID, PAID
    dining_option = db.Column(db.String(20), default='DINE_IN', index=True) # DINE_IN, TAKE_OUT, DELIVERY
    payment_method = db.Column(db.String(20), default='COUNTER') # COUNTER, ONLINE
    amount_tendered = db.Column(db.Numeric(10, 2), nullable=True)
    change_amount = db.Column(db.Numeric(10, 2), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    delivery_address = db.Column(db.Text, nullable=True)
    delivery_status = db.Column(db.String(20), nullable=True)  # WAITING, PICKED_UP, ON_THE_WAY, DELIVERED
    rider_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    delivery_fee = db.Column(db.Numeric(10, 2), default=0)
    proof_of_delivery_url = db.Column(db.String(255), nullable=True)
    xendit_invoice_id = db.Column(db.String(255), nullable=True)
    xendit_invoice_url = db.Column(db.String(255), nullable=True)
    prep_start_at = db.Column(db.DateTime, nullable=True)
    prep_end_at = db.Column(db.DateTime, nullable=True)
    prep_duration = db.Column(db.Integer, nullable=True) # Prep time in seconds
    estimated_cost = db.Column(db.Numeric(10, 2), default=0) # Total cost of ingredients
    created_at = db.Column(db.DateTime, default=get_ph_time, index=True)
    processed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Cashier who processed
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservation.id'), nullable=True) # Linked reservation (if any)
    
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('orders', lazy=True))
    rider = db.relationship('User', foreign_keys=[rider_id], backref=db.backref('deliveries', lazy=True))
    processed_by = db.relationship('User', foreign_keys=[processed_by_id], backref=db.backref('handled_orders', lazy=True))
    reservation = db.relationship('Reservation', foreign_keys=[reservation_id], backref=db.backref('linked_order', uselist=False, lazy=True))
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price_at_time = db.Column(db.Numeric(10, 2), nullable=False)
    cost_at_time = db.Column(db.Numeric(10, 2), nullable=True) # Cost of ingredients at production

    menu_item = db.relationship('MenuItem')

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=True) # Reference to the specific order being reviewed
    rating = db.Column(db.Integer, nullable=False) # 1 to 5
    comment = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='PENDING', index=True) # PENDING, APPROVED, REJECTED
    created_at = db.Column(db.DateTime, default=get_ph_time, index=True)

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

class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    contact_person = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.Text, nullable=True)
    catalog_items = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=get_ph_time)

    ingredients = db.relationship('Ingredient', backref='supplier', lazy=True)

class Ingredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    unit = db.Column(db.String(30), nullable=False)  # e.g. grams, pieces, liters, kg
    stock_qty = db.Column(db.Numeric(10, 2), default=0) # Main Warehouse/Bodega
    kitchen_qty = db.Column(db.Numeric(10, 2), default=0) # On-hand at Kitchen
    reorder_level = db.Column(db.Numeric(10, 2), default=10)  # low-stock threshold
    cost_per_unit = db.Column(db.Numeric(10, 2), default=0)
    category = db.Column(db.String(50), nullable=True, default='General') # e.g. Protein, Dairy, Pantry
    expiration_date = db.Column(db.Date, nullable=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=get_ph_time)

    menu_items = db.relationship('MenuItemIngredient', backref='ingredient', lazy=True)

class MenuItemIngredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'), nullable=False)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id'), nullable=False)
    quantity_needed = db.Column(db.Numeric(10, 2), nullable=False)  # amount used per 1 serving

    menu_item = db.relationship('MenuItem', backref=db.backref('ingredients', lazy=True))

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sender = db.Column(db.String(20), nullable=False) # 'USER' or 'ADMIN'
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=get_ph_time)
    
    user = db.relationship('User', backref=db.backref('chat_messages', lazy=True, order_by='ChatMessage.created_at.asc()'))

class OrderChat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # Can be user or rider
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=get_ph_time)
    
    order = db.relationship('Order', backref=db.backref('chats', lazy=True, order_by='OrderChat.created_at.asc()'))
    sender = db.relationship('User', foreign_keys=[sender_id])

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(50), nullable=False)       # CREATE, UPDATE, DELETE, LOGIN, LOGOUT
    target_type = db.Column(db.String(50), nullable=False)   # e.g. MenuItem, Order, User, Reservation
    target_id = db.Column(db.Integer, nullable=True)
    description = db.Column(db.Text, nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=get_ph_time)

    user = db.relationship('User', backref=db.backref('audit_logs', lazy=True))

class Voucher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    discount_type = db.Column(db.String(10), nullable=False)    # PERCENT or FIXED
    discount_value = db.Column(db.Numeric(10, 2), nullable=False)
    min_order_amount = db.Column(db.Numeric(10, 2), default=0)
    max_uses = db.Column(db.Integer, default=100)
    times_used = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    valid_from = db.Column(db.DateTime, nullable=True)
    valid_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=get_ph_time)

class InventoryLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(20), nullable=False) # ADD, DEDUCT, EXPIRED, SPOILED
    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    previous_stock = db.Column(db.Numeric(10, 2), nullable=False)
    new_stock = db.Column(db.Numeric(10, 2), nullable=False)
    reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=get_ph_time)

    ingredient = db.relationship('Ingredient', backref=db.backref('logs', lazy=True))
    user = db.relationship('User', backref=db.backref('inventory_logs', lazy=True))

class FavoriteOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False) # "My Usual Breakfast"
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=get_ph_time)

    user = db.relationship('User', backref=db.backref('favorite_orders', lazy=True))
    items = db.relationship('FavoriteOrderItem', backref='favorite_order', lazy=True, cascade='all, delete-orphan')

class FavoriteOrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    favorite_order_id = db.Column(db.Integer, db.ForeignKey('favorite_order.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

    menu_item = db.relationship('MenuItem')

# ── WASTE MANAGEMENT ──────────────────────────────────────────────
class WasteRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id'), nullable=False)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    quantity_wasted = db.Column(db.Numeric(10, 2), nullable=False)
    reason = db.Column(db.String(100), nullable=False)  # SPOILED, EXPIRED, DROPPED, OTHER
    notes = db.Column(db.Text, nullable=True)
    cost_lost = db.Column(db.Numeric(10, 2), default=0)
    created_at = db.Column(db.DateTime, default=get_ph_time)

    ingredient = db.relationship('Ingredient', backref=db.backref('waste_records', lazy=True))
    recorded_by = db.relationship('User', backref=db.backref('waste_records', lazy=True))

# ── FIFO INGREDIENT BATCHES ───────────────────────────────────────
class IngredientBatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id'), nullable=False)
    batch_qty = db.Column(db.Numeric(10, 2), nullable=False)
    remaining_qty = db.Column(db.Numeric(10, 2), nullable=False)
    cost_per_unit = db.Column(db.Numeric(10, 2), default=0)
    purchase_date = db.Column(db.Date, nullable=False)
    expiration_date = db.Column(db.Date, nullable=True)
    is_exhausted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=get_ph_time)

    ingredient = db.relationship('Ingredient', backref=db.backref('batches', lazy=True))

# ── KITCHEN STOCK REQUESTS ────────────────────────────────────────
class StockRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id'), nullable=False)
    requested_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    fulfilled_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    quantity_requested = db.Column(db.Numeric(10, 2), nullable=False)
    quantity_fulfilled = db.Column(db.Numeric(10, 2), nullable=True)
    status = db.Column(db.String(20), default='PENDING')  # PENDING, APPROVED, REJECTED, FULFILLED
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=get_ph_time)
    updated_at = db.Column(db.DateTime, default=get_ph_time, onupdate=get_ph_time)

    ingredient = db.relationship('Ingredient', backref=db.backref('stock_requests', lazy=True))
    requested_by = db.relationship('User', foreign_keys=[requested_by_id], backref=db.backref('stock_requests_made', lazy=True))
    fulfilled_by = db.relationship('User', foreign_keys=[fulfilled_by_id], backref=db.backref('stock_requests_fulfilled', lazy=True))

