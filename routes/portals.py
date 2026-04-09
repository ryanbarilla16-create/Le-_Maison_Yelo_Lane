from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from functools import wraps
from models import db, User, Order, Ingredient, OrderItem

cashier_bp  = Blueprint('cashier_portal',   __name__, url_prefix='/cashier')
kitchen_bp  = Blueprint('kitchen_portal',   __name__, url_prefix='/kitchen')
inventory_bp = Blueprint('inventory_portal', __name__, url_prefix='/inventory')

# ── Portal auth helpers ───────────────────────────────────────────

def _portal_login_required(role_key, login_endpoint):
    """Decorator: ensure the session has the required portal role."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if session.get('portal_role') != role_key:
                return redirect(url_for(login_endpoint))
            return f(*args, **kwargs)
        return wrapped
    return decorator

def _authenticate_portal(email, password, required_role):
    """Validate credentials and role; return User or None."""
    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password) and user.role == required_role and user.status == 'ACTIVE':
        return user
    return None

# ── Cashier Portal ────────────────────────────────────────────────

@cashier_bp.route('/login', methods=['GET', 'POST'])
def cashier_login():
    if request.method == 'POST':
        user = _authenticate_portal(request.form.get('email'), request.form.get('password'), 'CASHIER')
        if user:
            session['portal_role']    = 'CASHIER'
            session['portal_user_id'] = user.id
            session['portal_name']    = f"{user.first_name} {user.last_name}"
            return redirect(url_for('cashier_portal.cashier_dashboard'))
        flash('Invalid credentials or insufficient permissions.', 'error')
    return render_template('cashier/login.html')

@cashier_bp.route('/dashboard')
def cashier_dashboard():
    if session.get('portal_role') != 'CASHIER':
        return redirect(url_for('cashier_portal.cashier_login'))
    active   = Order.query.filter(Order.status.in_(['PENDING','PREPARING'])).count()
    done_today = Order.query.filter_by(status='COMPLETED').count()
    unpaid   = Order.query.filter_by(payment_status='UNPAID').count()
    orders   = Order.query.filter(Order.status.in_(['PENDING','PREPARING'])).order_by(Order.created_at.desc()).limit(20).all()
    return render_template('cashier/dashboard.html',
                           active_orders=active,
                           completed_today=done_today,
                           unpaid_orders=unpaid,
                           orders=orders,
                           portal_name=session.get('portal_name', 'Cashier'))

@cashier_bp.route('/logout')
def cashier_logout():
    session.pop('portal_role', None)
    session.pop('portal_user_id', None)
    session.pop('portal_name', None)
    return redirect(url_for('cashier_portal.cashier_login'))

# ── Kitchen Portal ────────────────────────────────────────────────

@kitchen_bp.route('/login', methods=['GET', 'POST'])
def kitchen_login():
    if request.method == 'POST':
        # Kitchen staff may have role ADMIN (chef) — be flexible: accept ADMIN too
        user = User.query.filter_by(email=request.form.get('email')).first()
        if user and user.check_password(request.form.get('password')) and user.status == 'ACTIVE' \
                and user.role in ('ADMIN', 'KITCHEN', 'CASHIER'):
            session['portal_role']    = 'KITCHEN'
            session['portal_user_id'] = user.id
            session['portal_name']    = f"{user.first_name} {user.last_name}"
            return redirect(url_for('kitchen_portal.kitchen_dashboard'))
        flash('Invalid credentials or insufficient permissions.', 'error')
    return render_template('kitchen/login.html')

@kitchen_bp.route('/dashboard')
def kitchen_dashboard():
    if session.get('portal_role') != 'KITCHEN':
        return redirect(url_for('kitchen_portal.kitchen_login'))
    pending   = Order.query.filter_by(status='PENDING').order_by(Order.created_at.asc()).all()
    preparing = Order.query.filter_by(status='PREPARING').order_by(Order.created_at.asc()).all()
    ready     = Order.query.filter_by(status='READY').order_by(Order.created_at.desc()).limit(10).all()
    return render_template('kitchen/dashboard.html',
                           pending_orders=pending,
                           preparing_orders=preparing,
                           ready_orders=ready,
                           portal_name=session.get('portal_name', 'Chef'))

@kitchen_bp.route('/order/<int:order_id>/status', methods=['POST'])
def kitchen_update_order(order_id):
    if session.get('portal_role') != 'KITCHEN':
        return redirect(url_for('kitchen_portal.kitchen_login'))
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    if new_status in ('PREPARING', 'READY', 'COMPLETED'):
        order.status = new_status
        db.session.commit()
    return redirect(url_for('kitchen_portal.kitchen_dashboard'))

@kitchen_bp.route('/logout')
def kitchen_logout():
    session.pop('portal_role', None)
    session.pop('portal_user_id', None)
    session.pop('portal_name', None)
    return redirect(url_for('kitchen_portal.kitchen_login'))

# ── Inventory Portal ──────────────────────────────────────────────

@inventory_bp.route('/login', methods=['GET', 'POST'])
def inventory_login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email')).first()
        if user and user.check_password(request.form.get('password')) and user.status == 'ACTIVE' \
                and user.role in ('ADMIN', 'INVENTORY_STAFF'):
            session['portal_role']    = 'INVENTORY'
            session['portal_user_id'] = user.id
            session['portal_name']    = f"{user.first_name} {user.last_name}"
            return redirect(url_for('inventory_portal.inventory_dashboard'))
        flash('Invalid credentials or insufficient permissions.', 'error')
    return render_template('inventory/login.html')

@inventory_bp.route('/dashboard')
def inventory_dashboard():
    if session.get('portal_role') != 'INVENTORY':
        return redirect(url_for('inventory_portal.inventory_login'))
    total_items  = Ingredient.query.count()
    low_stock    = Ingredient.query.filter(
        Ingredient.stock_qty <= Ingredient.reorder_level
    ).count()
    ingredients  = Ingredient.query.order_by(Ingredient.stock_qty.asc()).limit(30).all()
    return render_template('inventory/dashboard.html',
                           total_items=total_items,
                           low_stock=low_stock,
                           ingredients=ingredients,
                           portal_name=session.get('portal_name', 'Manager'))

@inventory_bp.route('/logout')
def inventory_logout():
    session.pop('portal_role', None)
    session.pop('portal_user_id', None)
    session.pop('portal_name', None)
    return redirect(url_for('inventory_portal.inventory_login'))
