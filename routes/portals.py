from flask import Blueprint, render_template

cashier_bp = Blueprint('cashier_portal', __name__, url_prefix='/cashier')
kitchen_bp = Blueprint('kitchen_portal', __name__, url_prefix='/kitchen')
inventory_bp = Blueprint('inventory_portal', __name__, url_prefix='/inventory')

@cashier_bp.route('/login')
def login():
    return render_template('cashier/login.html')

@cashier_bp.route('/dashboard')
def dashboard():
    return render_template('cashier/dashboard.html')

@kitchen_bp.route('/login')
def login():
    return render_template('kitchen/login.html')

@kitchen_bp.route('/dashboard')
def dashboard():
    return render_template('kitchen/dashboard.html')

@inventory_bp.route('/login')
def login():
    return render_template('inventory/login.html')

@inventory_bp.route('/dashboard')
def dashboard():
    return render_template('inventory/dashboard.html')
