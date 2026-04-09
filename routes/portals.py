from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, current_user
from models import User

cashier_bp = Blueprint('cashier_portal', __name__, url_prefix='/cashier')
kitchen_bp = Blueprint('kitchen_portal', __name__, url_prefix='/kitchen')
inventory_bp = Blueprint('inventory_portal', __name__, url_prefix='/inventory')

def _authenticate_portal(email, password, allowed_roles):
    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password) and user.status == 'ACTIVE' and user.role and user.role.upper() in allowed_roles:
        return user
    return None

# ── Cashier Portal ────────────────────────────────────────────────
@cashier_bp.route('/login', methods=['GET', 'POST'])
def cashier_login():
    if current_user.is_authenticated and current_user.role in ['CASHIER', 'STAFF', 'ADMIN']:
        return redirect(url_for('admin.orders'))
        
    if request.method == 'POST':
        user = _authenticate_portal(request.form.get('email'), request.form.get('password'), ['CASHIER', 'STAFF', 'ADMIN'])
        if user:
            login_user(user)
            return redirect(url_for('admin.orders'))
        flash('Invalid credentials or insufficient permissions for Cashier Portal.', 'error')
    return render_template('cashier/login.html')

@cashier_bp.route('/dashboard')
def cashier_dashboard():
    return redirect(url_for('admin.orders'))

@cashier_bp.route('/logout')
def cashier_logout():
    return redirect(url_for('admin.admin_logout'))

# ── Kitchen Portal ────────────────────────────────────────────────
@kitchen_bp.route('/login', methods=['GET', 'POST'])
def kitchen_login():
    if current_user.is_authenticated and current_user.role in ['KITCHEN', 'ADMIN', 'CASHIER']:
        return redirect(url_for('admin.kitchen_view'))
        
    if request.method == 'POST':
        user = _authenticate_portal(request.form.get('email'), request.form.get('password'), ['KITCHEN', 'ADMIN', 'CASHIER'])
        if user:
            login_user(user)
            return redirect(url_for('admin.kitchen_view'))
        flash('Invalid credentials or insufficient permissions for Kitchen Portal.', 'error')
    return render_template('kitchen view/login.html')

@kitchen_bp.route('/dashboard')
def kitchen_dashboard():
    return redirect(url_for('admin.kitchen_view'))

@kitchen_bp.route('/logout')
def kitchen_logout():
    return redirect(url_for('admin.admin_logout'))

# ── Inventory Portal ──────────────────────────────────────────────
@inventory_bp.route('/login', methods=['GET', 'POST'])
def inventory_login():
    if current_user.is_authenticated and current_user.role in ['INVENTORY_STAFF', 'INVENTORY', 'ADMIN']:
        return redirect(url_for('admin.inventory'))
        
    if request.method == 'POST':
        user = _authenticate_portal(request.form.get('email'), request.form.get('password'), ['INVENTORY_STAFF', 'INVENTORY', 'ADMIN'])
        if user:
            login_user(user)
            return redirect(url_for('admin.inventory'))
        flash('Invalid credentials or insufficient permissions for Inventory Portal.', 'error')
    return render_template('inventory/login.html')

@inventory_bp.route('/dashboard')
def inventory_dashboard():
    return redirect(url_for('admin.inventory'))

@inventory_bp.route('/logout')
def inventory_logout():
    return redirect(url_for('admin.admin_logout'))
