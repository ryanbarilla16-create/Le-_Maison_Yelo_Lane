from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user, login_user, logout_user
from flask_mail import Message
from models import db, User, Reservation, MenuItem, Order, OrderItem, Review, Notification, Supplier, Ingredient, MenuItemIngredient, ChatMessage, AuditLog, Voucher, InventoryLog, WasteRecord, IngredientBatch, StockRequest
from datetime import datetime, date, timedelta
from utils import get_ph_time, create_notification, validate_name, validate_email, validate_username, validate_password
from sqlalchemy import func
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import load_only, selectinload
from functools import wraps
import traceback
import time
import threading
from itertools import groupby
from sqlalchemy import text as sql_text
import random
from utils import get_ph_time, create_notification, validate_name, validate_email, validate_username, validate_password, safe_elapsed
from permissions import requires_permission, requires_branch_access

# Small TTL caches to make admin tabs feel snappy (especially on remote DBs)
_ADMIN_CACHE = {
    "suppliers": {"loaded_at": 0.0, "value": None},
    "ingredients_raw": {"loaded_at": 0.0, "value": None},
    "walkin_items": {"loaded_at": 0.0, "value": None},
}

def _ttl_cached(key: str, ttl_seconds: int, loader):
    now = time.monotonic()
    slot = _ADMIN_CACHE.get(key)
    if slot and slot["value"] is not None and (now - slot["loaded_at"]) < ttl_seconds:
        return slot["value"]
    val = loader()
    if key in _ADMIN_CACHE:
        _ADMIN_CACHE[key]["value"] = val
        _ADMIN_CACHE[key]["loaded_at"] = now
    return val

def _get_suppliers_cached():
    return _ttl_cached(
        "suppliers",
        15,
        lambda: Supplier.query.options(load_only(Supplier.id, Supplier.name)).order_by(Supplier.name).all(),
    )

def _get_all_ingredients_raw_cached():
    # Used for dropdowns/autocomplete; keep it light and cached
    return _ttl_cached(
        "ingredients_raw",
        15,
        lambda: Ingredient.query.options(load_only(Ingredient.id, Ingredient.name, Ingredient.unit)).order_by(Ingredient.name).all(),
    )

def _get_walkin_items_cached():
    return _ttl_cached(
        "walkin_items",
        10,
        lambda: MenuItem.query.options(
            load_only(MenuItem.id, MenuItem.name, MenuItem.price, MenuItem.category, MenuItem.image_url, MenuItem.is_available)
        ).filter_by(is_available=True, is_deleted=False).order_by(MenuItem.category, MenuItem.name).all(),
    )

def _create_web_notification(user_id, title, message, notif_type='SYSTEM', link=None):
    """Backwards compatible helper for admin routes"""
    return create_notification(user_id, title, message, notif_type, link)

def log_inventory_change(ingredient_id, action, quantity, previous_stock, reason=None):
    from models import InventoryLog
    new_stock = previous_stock
    if action == 'ADD':
        new_stock = previous_stock + quantity
    elif action in ['DEDUCT', 'EXPIRED', 'SPOILED', 'WASTE']:
        new_stock = previous_stock - quantity
    
    log = InventoryLog(
        ingredient_id=ingredient_id,
        user_id=current_user.id if current_user.is_authenticated else None,
        action=action,
        quantity=quantity,
        previous_stock=previous_stock,
        new_stock=new_stock,
        reason=reason
    )
    db.session.add(log)
    return log

def process_fifo_transaction(ingredient_id, action, quantity, cost_per_unit=None, expiration_date=None):
    """
    Centralized FIFO handler for ingredient batches.
    - ADD: Creates a new batch with a purchase date of today.
    - DEDUCT/WASTE: Consumes stock from the oldest available batches first (FIFO).
    """
    from models import IngredientBatch
    from datetime import date
    
    quantity = float(quantity)
    if quantity <= 0: return

    if action == 'ADD':
        # Create a new batch for the ingredient
        batch = IngredientBatch(
            ingredient_id=ingredient_id,
            batch_qty=quantity,
            remaining_qty=quantity,
            cost_per_unit=cost_per_unit if cost_per_unit is not None else 0,
            purchase_date=date.today(),
            expiration_date=expiration_date
        )
        db.session.add(batch)
    elif action in ['DEDUCT', 'SPOILED', 'EXPIRED', 'WASTE']:
        # Consume from batches starting with the oldest
        remaining_needed = quantity
        batches = IngredientBatch.query.filter_by(ingredient_id=ingredient_id, is_exhausted=False)\
                                       .order_by(IngredientBatch.purchase_date.asc(), IngredientBatch.id.asc()).all()
        
        for batch in batches:
            if remaining_needed <= 0: break
            batch_avail = float(batch.remaining_qty)
            
            if batch_avail <= remaining_needed:
                remaining_needed -= batch_avail
                batch.remaining_qty = 0
                batch.is_exhausted = True
            else:
                batch.remaining_qty = batch_avail - remaining_needed
                remaining_needed = 0

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def _send_flask_mail_worker(app, msg):
    """Background worker to send Flask-Mail messages without blocking the request thread."""
    with app.app_context():
        mail = app.extensions.get('mail')
        if not mail:
            return
        for attempt in range(1, 4):
            try:
                mail.send(msg)
                return
            except Exception as e:
                if attempt >= 3:
                    print(f"Async mail send failed (final): {e}")
                    traceback.print_exc()
                    return
                time.sleep(0.75 * attempt)

# Cache for admin review sentiment so repeated visits don't recompute CPU-heavy word counts.
# Keyed by (review_id, rating, hash(comment_text)).
_REVIEW_SENTIMENT_CACHE = {}  # {cache_key: (loaded_at_monotonic, (sentiment, icon, color))}
_REVIEW_SENTIMENT_CACHE_TTL_SECONDS = 600  # 10 minutes

def admin_required(f):
    """
    Admin access decorator - now powered by the permission system.
    Allows staff roles to access admin routes based on their permissions.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        allowed_roles = ['ADMIN', 'SUPER_ADMIN', 'CASHIER', 'INVENTORY_STAFF', 'INVENTORY', 'KITCHEN', 'STAFF', 'RIDER']
        if not current_user.is_authenticated or not current_user.role or current_user.role.upper() not in allowed_roles:
            flash("Access denied. Staff privileges required.", "danger")
            return redirect(url_for('admin.admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# ─── SYSTEM: DB INDEX CHECK ───────────────────────────
@admin_bp.route('/system/db-indexes', methods=['GET'])
@login_required
@admin_required
def system_db_indexes():
    """Admin-only: verify expected indexes exist (Postgres only)."""
    if current_user.role.upper() not in ('ADMIN', 'SUPER_ADMIN'):
        return jsonify({'success': False, 'message': 'Admin only.'}), 403

    try:
        dialect = db.engine.dialect.name
    except Exception:
        dialect = None
    if dialect not in ("postgresql", "postgres"):
        return jsonify({'success': True, 'dialect': dialect, 'indexes': [], 'missing': []}), 200

    expected = [
        "idx_reservation_date_status_booking_time",
        "idx_reservation_user_date_status",
        "idx_order_rider_delivery_status_id",
        "idx_order_user_created_at",
        "idx_review_status_created_at",
        "idx_menu_item_category_name",
        "idx_order_chat_order_id_created_at",
        "idx_order_item_order_menuitem",
        "idx_menu_item_ingredient_menuitem_ingredient",
    ]

    rows = db.session.execute(sql_text(
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
    )).fetchall()
    existing = sorted({r[0] for r in rows if r and r[0]})
    missing = [x for x in expected if x not in set(existing)]

    return jsonify({
        'success': True,
        'dialect': dialect,
        'expected': expected,
        'existing': existing,
        'missing': missing,
    }), 200

# ─── AUTH ─────────────────────────────────────────────
@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    allowed_roles = ['ADMIN', 'SUPER_ADMIN', 'CASHIER', 'INVENTORY_STAFF', 'INVENTORY', 'KITCHEN', 'STAFF', 'RIDER']
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if current_user.is_authenticated and current_user.role and current_user.role.upper() in allowed_roles:
        role_upper = current_user.role.upper()
        if role_upper == 'CASHIER':
            redirect_url = url_for('cashier_portal.cashier_dashboard')
        elif role_upper in ['INVENTORY_STAFF', 'INVENTORY']:
            redirect_url = url_for('inventory_portal.inventory_dashboard')
        elif role_upper == 'KITCHEN':
            redirect_url = url_for('admin.kitchen_view')
        elif role_upper == 'RIDER':
            redirect_url = url_for('admin.deliveries')
        else:
            redirect_url = url_for('admin.overview')
        if is_ajax:
            return jsonify({'success': True, 'redirect': redirect_url})
        return redirect(redirect_url)
        
    if request.method == 'POST':
        email = request.form.get('email')
        pwd = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(pwd) and user.role and user.role.upper() in allowed_roles:
            login_user(user)
            role_upper = user.role.upper()
            if role_upper == 'CASHIER':
                redirect_url = url_for('cashier_portal.cashier_dashboard')
            elif role_upper in ['INVENTORY_STAFF', 'INVENTORY']:
                redirect_url = url_for('inventory_portal.inventory_dashboard')
            elif role_upper == 'KITCHEN':
                redirect_url = url_for('admin.kitchen_view')
            elif role_upper == 'RIDER':
                redirect_url = url_for('admin.deliveries')
            else:
                redirect_url = url_for('admin.overview')
            if is_ajax:
                return jsonify({'success': True, 'redirect': redirect_url})
            return redirect(redirect_url)
            
        if is_ajax:
            return jsonify({'success': False, 'message': 'Invalid staff credentials or access denied.'}), 401
        flash("Invalid staff credentials or access denied.", "danger")
    return render_template('admin/login.html')

@admin_bp.route('/logout')
@login_required # wait, do we really need this? Yes.
def admin_logout():
    from flask import session
    portal = session.get('logged_in_portal')
    logout_user()
    
    if portal == 'kitchen':
        return redirect(url_for('kitchen_portal.kitchen_login'))
    elif portal == 'cashier':
        return redirect(url_for('cashier_portal.cashier_login'))
    elif portal == 'inventory':
        return redirect(url_for('inventory_portal.inventory_login'))
    elif portal == 'rider':
        return redirect(url_for('rider_portal.rider_login'))
        
    return redirect(url_for('admin.admin_login'))

# ─── ADMIN FORGOT PASSWORD ──────────────────────────
@admin_bp.route('/forgot-password', methods=['GET', 'POST'])
def admin_forgot_password():
    from flask import session
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        user = User.query.filter_by(email=email).first()
        
        # Security: Only allow staff roles to use this flow
        allowed_roles = ['ADMIN', 'CASHIER', 'INVENTORY_STAFF', 'INVENTORY', 'KITCHEN', 'STAFF', 'RIDER']
        if not user or not user.role or user.role.upper() not in allowed_roles:
            msg = f"If an account exists for {email}, a reset code has been sent."
            if is_ajax:
                return jsonify({'success': True, 'redirect': url_for('admin.admin_login'), 'message': msg})
            flash(msg, "info")
            return redirect(url_for('admin.admin_login'))
            
        if user.otp_created_at:
            elapsed = safe_elapsed(user.otp_created_at)
            if elapsed < 60:
                msg = f"Please wait {int(60 - elapsed)}s before requesting a new code."
                if is_ajax:
                    return jsonify({'success': False, 'message': msg})
                flash(msg, "warning")
                return redirect(url_for('admin.admin_verify_reset_otp', user_id=user.id))
        
        otp = f"{random.randint(100000, 999999)}"
        user.otp_code = otp
        user.otp_created_at = get_ph_time()
        db.session.commit()
        
        print(f"--- ADMIN FORGOT PASSWORD OTP FOR {email} IS: {otp} ---")
        
        html_msg = f"""
        <div style="background-color: #fcfaf8; padding: 40px 20px; font-family: 'Helvetica Neue', Arial, sans-serif;">
            <div style="max-width: 500px; margin: 0 auto; background: #ffffff; border-radius: 20px; border: 1px solid #eee; overflow: hidden; box-shadow: 0 10px 20px rgba(0,0,0,0.05);">
                <div style="background: #8b634b; padding: 30px; text-align: center;">
                    <h1 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 300;">Le Maison Admin</h1>
                </div>
                <div style="padding: 40px; color: #4a3b32; line-height: 1.6;">
                    <h2 style="margin-top: 0; font-size: 18px;">Staff Access Reset</h2>
                    <p>Hello <strong>{user.first_name}</strong>,</p>
                    <p>A password reset was requested for your staff account. Use the code below to proceed:</p>
                    <div style="text-align: center; margin: 30px 0; background: #fdfbf9; border: 1px dashed #8b634b; padding: 20px; border-radius: 12px;">
                        <span style="font-size: 32px; font-weight: 800; letter-spacing: 5px; color: #8b634b;">{otp}</span>
                    </div>
                    <p style="font-size: 13px; color: #8d6e63; text-align: center;">This code will expire in 5 minutes.</p>
                </div>
            </div>
        </div>
        """
        
        app_obj = current_app._get_current_object()
        threading.Thread(
            target=_send_flask_mail_worker,
            args=(app_obj, Message('Staff Password Reset - Le Maison', recipients=[email], html=html_msg)),
            daemon=True,
        ).start()
        
        session['admin_reset_user_id'] = user.id
        if is_ajax:
            return jsonify({'success': True, 'redirect': url_for('admin.admin_verify_reset_otp', user_id=user.id)})
        return redirect(url_for('admin.admin_verify_reset_otp', user_id=user.id))
        
    return render_template('admin/forgot_password.html')

@admin_bp.route('/verify-reset-otp/<int:user_id>', methods=['GET', 'POST'])
def admin_verify_reset_otp(user_id):
    from flask import session
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if session.get('admin_reset_user_id') != user_id:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Invalid session.'}), 400
        flash("Invalid session.", "danger")
        return redirect(url_for('admin.admin_forgot_password'))
        
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        otp_input = request.form.get('otp', '').strip()
        if user.otp_created_at and safe_elapsed(user.otp_created_at) > 300:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Code expired. Please request a new one.'}), 400
            flash("Code expired. Please request a new one.", "danger")
            return redirect(url_for('admin.admin_forgot_password'))
                
        if user.otp_code == otp_input:
            session['admin_reset_verified_id'] = user.id
            if is_ajax:
                return jsonify({'success': True, 'redirect': url_for('admin.admin_reset_password')})
            flash("Code verified. Set your new password.", "success")
            return redirect(url_for('admin.admin_reset_password'))
        else:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Invalid code.'}), 400
            flash("Invalid code.", "danger")
            
    cooldown = 0
    if user.otp_created_at:
        cooldown = max(0, int(60 - safe_elapsed(user.otp_created_at)))
        
    return render_template('admin/verify_reset_otp.html', user=user, cooldown_remaining=cooldown)

@admin_bp.route('/resend-reset-otp/<int:user_id>', methods=['POST'])
def admin_resend_reset_otp(user_id):
    from flask import session
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if session.get('admin_reset_user_id') != user_id:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Invalid session.'}), 400
        return redirect(url_for('admin.admin_forgot_password'))
    
    user = User.query.get_or_404(user_id)
    if user.otp_created_at and safe_elapsed(user.otp_created_at) < 60:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Please wait before resending.'}), 400
        return redirect(url_for('admin.admin_verify_reset_otp', user_id=user.id))
        
    otp = f"{random.randint(100000, 999999)}"
    user.otp_code = otp
    user.otp_created_at = get_ph_time()
    db.session.commit()
    
    html_msg = f"<p>Your new staff reset code is: <strong>{otp}</strong></p>"
    app_obj = current_app._get_current_object()
    threading.Thread(
        target=_send_flask_mail_worker,
        args=(app_obj, Message('New Staff Reset Code', recipients=[user.email], html=html_msg)),
        daemon=True,
    ).start()
    
    if is_ajax:
        return jsonify({'success': True, 'message': 'New code sent.', 'cooldown_remaining': 60})
    flash("New code sent.", "success")
    return redirect(url_for('admin.admin_verify_reset_otp', user_id=user.id))

@admin_bp.route('/reset-password', methods=['GET', 'POST'])
def admin_reset_password():
    from flask import session
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    user_id = session.get('admin_reset_verified_id')
    if not user_id:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Session expired.'}), 400
        return redirect(url_for('admin.admin_forgot_password'))
        
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        err = validate_password(new_password, confirm_password)
        if err:
            if is_ajax:
                return jsonify({'success': False, 'message': err}), 400
            flash(err, "danger")
            return render_template('admin/reset_password.html')
            
        user.set_password(new_password)
        user.otp_code = None
        user.otp_created_at = None
        db.session.commit()
        
        session.pop('admin_reset_user_id', None)
        session.pop('admin_reset_verified_id', None)
        
        if is_ajax:
            return jsonify({'success': True, 'redirect': url_for('admin.admin_login')})
        flash("Password updated successfully. Please log in.", "success")
        return redirect(url_for('admin.admin_login'))
        
    return render_template('admin/reset_password.html')

# ─── MAIN: OVERVIEW ─────────────────────────────────
@admin_bp.route('/')
@admin_bp.route('/overview')
@login_required
@admin_required
def overview():
    # If SUPER_ADMIN, redirect to the dedicated super admin dashboard
    if current_user.role and current_user.role.upper() == 'SUPER_ADMIN':
        return redirect(url_for('admin.super_admin_overview'))

    import json as _json
    today = date.today()

    # Determine branch filter for this admin
    user_branch = getattr(current_user, 'branch', None)

    # ── CUSTOMER STATS (global - customers are not branch-specific) ──
    users_stats = db.session.query(User.role, User.status, func.count(User.id)).group_by(User.role, User.status).all()
    total_customers = sum(c for r, s, c in users_stats if r == 'USER')
    pending_users = sum(c for r, s, c in users_stats if r == 'USER' and s == 'PENDING')

    # ── RESERVATION STATS (branch-filtered) ──
    res_query = db.session.query(Reservation.status, func.count(Reservation.id))
    if user_branch and user_branch != 'ALL':
        res_query = res_query.filter(Reservation.branch == user_branch)
    res_stats = res_query.group_by(Reservation.status).all()
    total_reservations = sum(c for s, c in res_stats)
    pending_reservations = sum(c for s, c in res_stats if s == 'PENDING')
    confirmed_reservations = sum(c for s, c in res_stats if s == 'CONFIRMED')

    # ── MENU STATS (shared across branches for now) ──
    total_menu = MenuItem.query.count()
    low_stock_items = MenuItem.query.filter_by(is_available=False).limit(200).all()

    # ── STOCK & INVENTORY (global for now - inventory is shared) ──
    pending_stock_requests = 0
    low_ingredients_count = 0
    if not user_branch or user_branch in ('ALL', 'Pagsanjan'):
        pending_stock_requests = StockRequest.query.filter_by(status='PENDING').count()
        low_ingredients_count = Ingredient.query.filter(Ingredient.stock_qty <= Ingredient.reorder_level).count()

    # ── RECENT RESERVATIONS (branch-filtered) ──
    recent_res_query = Reservation.query
    if user_branch and user_branch != 'ALL':
        recent_res_query = recent_res_query.filter_by(branch=user_branch)
    recent_reservations = recent_res_query.order_by(Reservation.created_at.desc()).limit(5).all()

    # ── REVENUE & ORDER TRENDS (branch-filtered, last 7 days) ──
    week_ago = today - timedelta(days=6)
    date_col = func.date(Order.created_at)
    trend_query = db.session.query(
        date_col.label('d'),
        func.count(Order.id).label('cnt'),
        func.sum(Order.total_amount).label('rev')
    ).filter(date_col >= week_ago)
    if user_branch and user_branch != 'ALL':
        trend_query = trend_query.filter(Order.branch == user_branch)
    trend_stats = trend_query.group_by(date_col).all()

    trend_map = {row.d: (int(row.cnt or 0), float(row.rev or 0)) for row in trend_stats}

    revenue_trend_labels, revenue_trend_data = [], []
    daily_orders_labels, daily_orders_data = [], []

    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        lbl = d.strftime('%b %d')
        revenue_trend_labels.append(lbl)
        daily_orders_labels.append(lbl)

        stat = trend_map.get(d, (0, 0.0))
        daily_orders_data.append(stat[0])
        revenue_trend_data.append(stat[1])

    # ── BUSY TIMES (branch-filtered) ──
    hour_col = func.extract('hour', Order.created_at)
    busy_query = db.session.query(hour_col.label('hr'), func.count(Order.id))
    if user_branch and user_branch != 'ALL':
        busy_query = busy_query.filter(Order.branch == user_branch)
    busy_hours_raw = busy_query.group_by(hour_col).order_by(hour_col).all()
    busy_map = {}
    for h, c in busy_hours_raw:
        if h is not None:
            try:
                busy_map[int(h)] = int(c or 0)
            except (ValueError, TypeError):
                pass
    busy_times_labels = [f'{h:02d}:00' for h in range(24)]
    busy_times_data = [busy_map.get(h, 0) for h in range(24)]

    # ── ORDER STATUS DONUT (branch-filtered) ──
    status_query = db.session.query(Order.status, func.count(Order.id))
    if user_branch and user_branch != 'ALL':
        status_query = status_query.filter(Order.branch == user_branch)
    order_status_rows = status_query.group_by(Order.status).all()
    order_status_labels = [r[0] for r in order_status_rows] if order_status_rows else ['No Data']
    order_status_data = [r[1] for r in order_status_rows] if order_status_rows else [1]

    # ── TOTAL REVENUE (branch-filtered) ──
    from models import SupplierPayment
    rev_query = db.session.query(func.coalesce(func.sum(Order.total_amount), 0))
    if user_branch and user_branch != 'ALL':
        rev_query = rev_query.filter(Order.branch == user_branch)
    order_rev = float(rev_query.scalar())
    
    expense_query = db.session.query(func.coalesce(func.sum(SupplierPayment.amount), 0))
    if user_branch and user_branch != 'ALL':
        expense_query = expense_query.filter(SupplierPayment.branch == user_branch)
    total_expenses = float(expense_query.scalar())
    
    total_revenue = order_rev - total_expenses

    return render_template('admin/overview.html',
        total_customers=total_customers,
        pending_users=pending_users,
        total_menu=total_menu,
        total_reservations=total_reservations,
        pending_reservations=pending_reservations,
        confirmed_reservations=confirmed_reservations,
        recent_reservations=recent_reservations,
        low_stock_items=low_stock_items,
        pending_stock_requests=pending_stock_requests,
        low_ingredients_count=low_ingredients_count,
        total_revenue=total_revenue,
        revenue_trend_labels=_json.dumps(revenue_trend_labels),
        revenue_trend_data=_json.dumps(revenue_trend_data),
        daily_orders_labels=_json.dumps(daily_orders_labels),
        daily_orders_data=_json.dumps(daily_orders_data),
        busy_times_labels=_json.dumps(busy_times_labels),
        busy_times_data=_json.dumps(busy_times_data),
        order_status_labels=_json.dumps(order_status_labels),
        order_status_data=_json.dumps(order_status_data)
    )

# ─── SUPER ADMIN: MULTI-BRANCH OVERVIEW ──────────────
@admin_bp.route('/super-overview')
@login_required
@admin_required
def super_admin_overview():
    if not current_user.role or current_user.role.upper() != 'SUPER_ADMIN':
        flash("Access denied. Super Admin only.", "danger")
        return redirect(url_for('admin.overview'))

    import json as _json
    today = date.today()
    week_ago = today - timedelta(days=6)
    branches = ['Pagsanjan', 'Lucban']

    # ── GLOBAL STATS ──
    total_customers = User.query.filter_by(role='USER').count()
    total_staff = User.query.filter(User.role.in_(['ADMIN', 'CASHIER', 'KITCHEN', 'INVENTORY_STAFF', 'INVENTORY', 'STAFF', 'RIDER'])).count()
    total_menu = MenuItem.query.filter_by(is_deleted=False).count()
    from models import SupplierPayment
    
    # Get ALL PAID orders revenue (Main DB + Archive DB)
    from archive.models import ArchiveOrder
    try:
        main_db_revenue = float(db.session.query(func.coalesce(func.sum(Order.total_amount), 0)).filter(
            Order.payment_status == 'PAID'
        ).scalar())
    except OperationalError:
        db.session.rollback()
        main_db_revenue = 0.0
    try:
        archive_db_revenue = float(db.session.query(func.coalesce(func.sum(ArchiveOrder.total_amount), 0)).filter(
            ArchiveOrder.payment_status == 'PAID'
        ).scalar())
    except OperationalError:
        db.session.rollback()
        archive_db_revenue = 0.0
    total_order_revenue = main_db_revenue + archive_db_revenue

    try:
        total_expenses = float(db.session.query(func.coalesce(func.sum(SupplierPayment.amount), 0)).scalar())
    except OperationalError:
        db.session.rollback()
        total_expenses = 0.0
    total_revenue = total_order_revenue  # GROSS only - expenses shown separately per branch
    try:
        total_orders = Order.query.count()
        total_reservations = Reservation.query.count()
        pending_orders = Order.query.filter_by(status='PENDING').count()
    except OperationalError:
        db.session.rollback()
        total_orders = total_reservations = pending_orders = 0

    # ── PER-BRANCH STATS ──
    from archive.models import ArchiveOrder
    branch_data = {}
    for br in branches:
        # Get ALL PAID orders revenue (Main DB + Archive DB)
        try:
            main_db_revenue = float(db.session.query(func.coalesce(func.sum(Order.total_amount), 0)).filter(
                Order.branch == br,
                Order.payment_status == 'PAID'
            ).scalar())
        except OperationalError:
            db.session.rollback()
            main_db_revenue = 0.0

        try:
            archive_db_revenue = float(db.session.query(func.coalesce(func.sum(ArchiveOrder.total_amount), 0)).filter(
                ArchiveOrder.branch == br,
                ArchiveOrder.payment_status == 'PAID'
            ).scalar())
        except OperationalError:
            db.session.rollback()
            archive_db_revenue = 0.0
        br_order_revenue = main_db_revenue + archive_db_revenue

        try:
            br_expenses = float(db.session.query(func.coalesce(func.sum(SupplierPayment.amount), 0)).filter(SupplierPayment.branch == br).scalar())
        except OperationalError:
            db.session.rollback()
            br_expenses = 0.0

        try:
            br_expense_count = db.session.query(func.count(SupplierPayment.id)).filter(SupplierPayment.branch == br).scalar() or 0
        except OperationalError:
            db.session.rollback()
            br_expense_count = 0

        br_net_revenue = br_order_revenue - br_expenses  # After supplier deductions

        # Count orders (Main DB only for active operations)
        try:
            br_orders = Order.query.filter_by(branch=br).count()
            br_pending = Order.query.filter_by(branch=br, status='PENDING').count()
            br_completed = Order.query.filter_by(branch=br, status='COMPLETED').count()
        except OperationalError:
            db.session.rollback()
            br_orders = br_pending = br_completed = 0

        try:
            br_reservations = Reservation.query.filter_by(branch=br).count()
        except OperationalError:
            db.session.rollback()
            br_reservations = 0

        try:
            br_staff = User.query.filter(
                User.branch == br,
                User.role.in_(['ADMIN', 'CASHIER', 'KITCHEN', 'INVENTORY_STAFF', 'INVENTORY', 'STAFF', 'RIDER'])
            ).count()
        except OperationalError:
            db.session.rollback()
            br_staff = 0

        # Revenue trend per branch (last 7 days)
        try:
            _d_col = func.date(Order.created_at).label('d')
            br_trend = db.session.query(
                _d_col,
                func.sum(Order.total_amount).label('rev')
            ).filter(func.date(Order.created_at) >= week_ago, Order.branch == br).group_by(_d_col).all()
            br_trend_map = {row.d: float(row.rev or 0) for row in br_trend}
        except OperationalError:
            db.session.rollback()
            br_trend_map = {}

        br_rev_data = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            br_rev_data.append(br_trend_map.get(d, 0.0))

        # Expense trend per branch (last 7 days)
        try:
            _exp_d_col = func.date(SupplierPayment.created_at).label('d')
            br_exp_trend = db.session.query(
                _exp_d_col,
                func.sum(SupplierPayment.amount).label('exp')
            ).filter(func.date(SupplierPayment.created_at) >= week_ago, SupplierPayment.branch == br).group_by(_exp_d_col).all()
            br_exp_trend_map = {row.d: float(row.exp or 0) for row in br_exp_trend}
        except OperationalError:
            db.session.rollback()
            br_exp_trend_map = {}

        br_exp_data = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            br_exp_data.append(br_exp_trend_map.get(d, 0.0))

        # Order status breakdown per branch
        try:
            br_status_rows = db.session.query(Order.status, func.count(Order.id)).filter(Order.branch == br).group_by(Order.status).all()
            br_status_labels = [r[0] for r in br_status_rows] if br_status_rows else ['No Data']
            br_status_data = [r[1] for r in br_status_rows] if br_status_rows else [0]
        except OperationalError:
            db.session.rollback()
            br_status_labels = ['No Data']
            br_status_data = [0]

        # Recent supplier payments per branch (last 5)
        try:
            br_recent_payments = SupplierPayment.query.filter_by(branch=br).order_by(SupplierPayment.created_at.desc()).limit(5).all()
        except OperationalError:
            db.session.rollback()
            br_recent_payments = []

        branch_data[br] = {
            'gross_revenue': br_order_revenue,
            'expenses': br_expenses,
            'expense_count': br_expense_count,
            'net_revenue': br_net_revenue,
            'revenue': br_net_revenue,  # keep for backward compat in template
            'orders': br_orders,
            'pending': br_pending,
            'completed': br_completed,
            'reservations': br_reservations,
            'staff_count': br_staff,
            'revenue_trend': br_rev_data,
            'expense_trend': br_exp_data,
            'status_labels': br_status_labels,
            'status_data': br_status_data,
            'recent_payments': br_recent_payments,
        }

    # Revenue trend labels (shared)
    rev_labels = []
    for i in range(6, -1, -1):
        rev_labels.append((today - timedelta(days=i)).strftime('%b %d'))

    # ── CRITICAL ALERTS (Inventory & Kitchen) ──
    try:
        low_ingredients_all = Ingredient.query.filter(Ingredient.stock_qty <= Ingredient.reorder_level).order_by(Ingredient.stock_qty.asc()).limit(20).all()
    except OperationalError:
        db.session.rollback()
        low_ingredients_all = []
    try:
        out_of_stock_menu_all = MenuItem.query.filter_by(is_available=False).limit(20).all()
    except OperationalError:
        db.session.rollback()
        out_of_stock_menu_all = []

    low_ingredients = {'Pagsanjan': [], 'Lucban': []}
    for item in low_ingredients_all:
        b = item.branch or 'Pagsanjan'
        if b in low_ingredients:
            low_ingredients[b].append(item)

    out_of_stock_menu = {'Pagsanjan': [], 'Lucban': []}
    for item in out_of_stock_menu_all:
        b = item.branch or 'Pagsanjan'
        if b in out_of_stock_menu:
            out_of_stock_menu[b].append(item)

    try:
        recent_expenses = SupplierPayment.query.order_by(SupplierPayment.created_at.desc()).limit(10).all()
    except OperationalError:
        db.session.rollback()
        recent_expenses = []

    return render_template('admin/super_overview.html',
        total_customers=total_customers,
        total_staff=total_staff,
        total_menu=total_menu,
        total_revenue=total_revenue,
        total_expenses=total_expenses,
        total_orders=total_orders,
        total_reservations=total_reservations,
        pending_orders=pending_orders,
        branches=branches,
        branch_data=branch_data,
        low_ingredients=low_ingredients,
        out_of_stock_menu=out_of_stock_menu,
        get_ph_time=get_ph_time,
        rev_labels=_json.dumps(rev_labels),
        pagsanjan_rev=_json.dumps(branch_data['Pagsanjan']['revenue_trend']),
        lucban_rev=_json.dumps(branch_data['Lucban']['revenue_trend']),
        pagsanjan_exp=_json.dumps(branch_data['Pagsanjan']['expense_trend']),
        lucban_exp=_json.dumps(branch_data['Lucban']['expense_trend']),
        pagsanjan_status_labels=_json.dumps(branch_data['Pagsanjan']['status_labels']),
        pagsanjan_status_data=_json.dumps(branch_data['Pagsanjan']['status_data']),
        lucban_status_labels=_json.dumps(branch_data['Lucban']['status_labels']),
        lucban_status_data=_json.dumps(branch_data['Lucban']['status_data']),
        recent_expenses=recent_expenses,
    )

# ─── STAFF PERFORMANCE ────────────────────────────────
@admin_bp.route('/staff-performance')
@login_required
@admin_required
def staff_performance():
    if current_user.role.upper() != 'SUPER_ADMIN':
        flash("Access denied. Admin Boss only.", "danger")
        return redirect(url_for('admin.overview'))
    from models import InventoryLog
    import json as _json

    # ── CASHIER STATS ──
    cashiers_q = User.query.filter(db.func.upper(User.role).in_(['CASHIER', 'STAFF']))
    user_branch = getattr(current_user, 'branch', None)
    if user_branch and user_branch != 'ALL':
        cashiers_q = cashiers_q.filter(User.branch == user_branch)
    cashiers = cashiers_q.all()
    cashier_stats = []
    cashier_ids = [c.id for c in cashiers]
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    cashier_agg = {}
    cashier_today = {}
    if cashier_ids:
        rows = (
            db.session.query(
                Order.processed_by_id,
                func.count(Order.id),
                func.coalesce(func.sum(Order.total_amount), 0),
            )
            .filter(Order.processed_by_id.in_(cashier_ids))
            .group_by(Order.processed_by_id)
            .all()
        )
        cashier_agg = {pid: (int(cnt or 0), float(total or 0)) for pid, cnt, total in rows}

        rows_today = (
            db.session.query(Order.processed_by_id, func.count(Order.id))
            .filter(Order.processed_by_id.in_(cashier_ids), Order.created_at >= today_start)
            .group_by(Order.processed_by_id)
            .all()
        )
        cashier_today = {pid: int(cnt or 0) for pid, cnt in rows_today}

    for c in cashiers:
        orders_count, total_sales = cashier_agg.get(c.id, (0, 0.0))
        avg_order_value = (float(total_sales) / orders_count) if orders_count > 0 else 0.0
        cashier_stats.append({
            'name': f"{c.first_name} {c.last_name}",
            'count': orders_count,
            'sales': float(total_sales),
            'avg_order': round(avg_order_value, 2),
            'today_orders': cashier_today.get(c.id, 0),
        })

    # ── RIDER STATS ──
    riders_q = User.query.filter(db.func.upper(User.role) == 'RIDER')
    if user_branch and user_branch != 'ALL':
        riders_q = riders_q.filter(User.branch == user_branch)
    riders = riders_q.all()
    rider_stats = []
    rider_ids = [r.id for r in riders]
    rider_total = {}
    rider_delivered = {}
    rider_pending = {}
    rider_earnings = {}
    if rider_ids:
        # total assigned
        rows_total = (
            db.session.query(Order.rider_id, func.count(Order.id))
            .filter(Order.rider_id.in_(rider_ids))
            .group_by(Order.rider_id)
            .all()
        )
        rider_total = {rid: int(cnt or 0) for rid, cnt in rows_total}

        # delivered count + earnings
        rows_del = (
            db.session.query(
                Order.rider_id,
                func.count(Order.id),
                func.coalesce(func.sum(Order.delivery_fee), 0),
            )
            .filter(Order.rider_id.in_(rider_ids), Order.delivery_status == 'DELIVERED')
            .group_by(Order.rider_id)
            .all()
        )
        rider_delivered = {rid: int(cnt or 0) for rid, cnt, _ in rows_del}
        rider_earnings = {rid: float(total or 0) for rid, _, total in rows_del}

        # pending deliveries
        rows_pending = (
            db.session.query(Order.rider_id, func.count(Order.id))
            .filter(
                Order.rider_id.in_(rider_ids),
                Order.delivery_status.in_(['WAITING', 'PICKED_UP', 'ON_THE_WAY'])
            )
            .group_by(Order.rider_id)
            .all()
        )
        rider_pending = {rid: int(cnt or 0) for rid, cnt in rows_pending}

    for r in riders:
        delivered_count = rider_delivered.get(r.id, 0)
        total_assigned = rider_total.get(r.id, 0)
        pending_deliveries = rider_pending.get(r.id, 0)
        delivery_earnings = rider_earnings.get(r.id, 0.0)
        rider_stats.append({
            'name': f"{r.first_name} {r.last_name}",
            'count': delivered_count,
            'total_assigned': total_assigned,
            'earnings': float(delivery_earnings),
            'pending': pending_deliveries,
            'success_rate': round((delivered_count / total_assigned * 100), 1) if total_assigned > 0 else 0,
        })

    # ── INVENTORY STAFF STATS ──
    inv_staff = User.query.filter(db.func.upper(User.role).in_(['INVENTORY_STAFF', 'INVENTORY'])).all()
    inventory_stats = []
    inv_ids = [s.id for s in inv_staff]
    inv_total = {}
    inv_by_action = {}
    inv_items_managed = {}
    if inv_ids:
        rows_total = (
            db.session.query(InventoryLog.user_id, func.count(InventoryLog.id))
            .filter(InventoryLog.user_id.in_(inv_ids))
            .group_by(InventoryLog.user_id)
            .all()
        )
        inv_total = {uid: int(cnt or 0) for uid, cnt in rows_total}

        rows_actions = (
            db.session.query(InventoryLog.user_id, InventoryLog.action, func.count(InventoryLog.id))
            .filter(InventoryLog.user_id.in_(inv_ids))
            .group_by(InventoryLog.user_id, InventoryLog.action)
            .all()
        )
        inv_by_action = {}
        for uid, action, cnt in rows_actions:
            inv_by_action.setdefault(uid, {})[action] = int(cnt or 0)

        rows_items = (
            db.session.query(InventoryLog.user_id, func.count(func.distinct(InventoryLog.ingredient_id)))
            .filter(InventoryLog.user_id.in_(inv_ids))
            .group_by(InventoryLog.user_id)
            .all()
        )
        inv_items_managed = {uid: int(cnt or 0) for uid, cnt in rows_items}

    for s in inv_staff:
        by_action = inv_by_action.get(s.id, {})
        adds = by_action.get('ADD', 0)
        deducts = by_action.get('DEDUCT', 0)
        spoiled = by_action.get('EXPIRED', 0) + by_action.get('SPOILED', 0)
        inventory_stats.append({
            'name': f"{s.first_name} {s.last_name}",
            'total_actions': inv_total.get(s.id, 0),
            'adds': adds,
            'deducts': deducts,
            'spoiled': spoiled,
            'items_managed': inv_items_managed.get(s.id, 0),
        })

    # ── KITCHEN STAFF STATS ──
    kitchen_staff_q = User.query.filter(db.func.upper(User.role) == 'KITCHEN')
    if user_branch and user_branch != 'ALL':
        kitchen_staff_q = kitchen_staff_q.filter(User.branch == user_branch)
    kitchen_staff = kitchen_staff_q.all()
    kitchen_stats = []
    # General kitchen metrics
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    kitchen_completed_today = Order.query.filter(Order.status == 'COMPLETED', Order.prep_end_at >= today_start).count()
    kitchen_preparing_now = Order.query.filter(Order.status == 'PREPARING').count()

    # Compute avg prep time in SQL (avoid loading all rows).
    avg_secs = (
        db.session.query(
            func.avg(func.extract('epoch', Order.prep_end_at - Order.prep_start_at))
        )
        .filter(
            Order.status == 'COMPLETED',
            Order.prep_start_at.isnot(None),
            Order.prep_end_at.isnot(None),
        )
        .scalar()
    )
    avg_prep_minutes = round((float(avg_secs or 0) / 60.0), 1) if avg_secs else 0

    for k in kitchen_staff:
        kitchen_stats.append({
            'name': f"{k.first_name} {k.last_name}",
        })

    # ── SUMMARY STATS ──
    total_staff = len(cashiers) + len(riders) + len(inv_staff) + len(kitchen_staff)
    total_orders_processed = sum(c['count'] for c in cashier_stats)
    total_deliveries_completed = sum(r['count'] for r in rider_stats)
    total_revenue_generated = sum(c['sales'] for c in cashier_stats)
    total_inv_actions = sum(s['total_actions'] for s in inventory_stats)

    # ── CHART DATA: Orders by Cashier ──
    cashier_chart_labels = [c['name'] for c in cashier_stats] if cashier_stats else ['No Cashiers']
    cashier_chart_data = [c['count'] for c in cashier_stats] if cashier_stats else [0]
    cashier_sales_data = [c['sales'] for c in cashier_stats] if cashier_stats else [0]

    # ── CHART DATA: Deliveries by Rider ──
    rider_chart_labels = [r['name'] for r in rider_stats] if rider_stats else ['No Riders']
    rider_chart_data = [r['count'] for r in rider_stats] if rider_stats else [0]

    # ── CHART DATA: Staff Role Distribution ──
    role_dist_labels = []
    role_dist_data = []
    if cashiers: role_dist_labels.append('Cashier'); role_dist_data.append(len(cashiers))
    if riders: role_dist_labels.append('Rider'); role_dist_data.append(len(riders))
    if inv_staff: role_dist_labels.append('Inventory'); role_dist_data.append(len(inv_staff))
    if kitchen_staff: role_dist_labels.append('Kitchen'); role_dist_data.append(len(kitchen_staff))
    if not role_dist_labels: role_dist_labels = ['No Staff']; role_dist_data = [0]

    return render_template('admin/staff_performance.html',
        cashier_stats=cashier_stats,
        rider_stats=rider_stats,
        inventory_stats=inventory_stats,
        kitchen_stats=kitchen_stats,
        total_staff=total_staff,
        total_orders_processed=total_orders_processed,
        total_deliveries_completed=total_deliveries_completed,
        total_revenue_generated=total_revenue_generated,
        total_inv_actions=total_inv_actions,
        kitchen_completed_today=kitchen_completed_today,
        kitchen_preparing_now=kitchen_preparing_now,
        avg_prep_minutes=avg_prep_minutes,
        cashier_chart_labels=_json.dumps(cashier_chart_labels),
        cashier_chart_data=_json.dumps(cashier_chart_data),
        cashier_sales_data=_json.dumps(cashier_sales_data),
        rider_chart_labels=_json.dumps(rider_chart_labels),
        rider_chart_data=_json.dumps(rider_chart_data),
        role_dist_labels=_json.dumps(role_dist_labels),
        role_dist_data=_json.dumps(role_dist_data),
    )

# ─── MAIN: ANALYTICS ────────────────────────────────
@admin_bp.route('/analytics')
@login_required
@admin_required
def analytics():
    if current_user.role.upper() not in ('ADMIN', 'SUPER_ADMIN'):
        flash("Access denied. Admin only.", "danger")
        return redirect(url_for('admin.overview'))

    import json as _json
    today = get_ph_time().date()
    total_customers = User.query.filter_by(role='USER').count()

    date_filter = request.args.get('date_filter', 'ALL').upper()
    if date_filter not in ['TODAY', 'WEEK', 'MONTH', 'ALL']:
        date_filter = 'ALL'

    start_date = None
    end_date = None
    start_dt = None
    end_dt = None

    if date_filter == 'TODAY':
        start_date = today
        end_date = today
    elif date_filter == 'WEEK':
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    elif date_filter == 'MONTH':
        start_date = today.replace(day=1)
        next_month = today.month + 1
        year = today.year
        if next_month > 12:
            next_month = 1
            year += 1
        end_date = date(year, next_month, 1) - timedelta(days=1)

    if start_date and end_date:
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

    # Previous period boundaries calculation for comparisons
    prev_start_date = None
    prev_end_date = None
    prev_start_dt = None
    prev_end_dt = None

    if date_filter == 'TODAY':
        prev_start_date = today - timedelta(days=1)
        prev_end_date = today - timedelta(days=1)
    elif date_filter == 'WEEK':
        current_week_start = today - timedelta(days=today.weekday())
        prev_start_date = current_week_start - timedelta(days=7)
        prev_end_date = current_week_start - timedelta(days=1)
    elif date_filter == 'MONTH':
        first_of_this_month = today.replace(day=1)
        prev_end_date = first_of_this_month - timedelta(days=1)
        prev_start_date = prev_end_date.replace(day=1)

    if prev_start_date and prev_end_date:
        prev_start_dt = datetime.combine(prev_start_date, datetime.min.time())
        prev_end_dt = datetime.combine(prev_end_date, datetime.max.time())

    def get_prev_period_stats(br):
        if not prev_start_date or not prev_end_date:
            return None
            
        # Prev Revenue
        prev_rev_q = db.session.query(func.coalesce(func.sum(Order.total_amount), 0))
        if br != 'ALL':
            prev_rev_q = prev_rev_q.filter(Order.branch == br)
        prev_rev_q = prev_rev_q.filter(Order.created_at >= prev_start_dt, Order.created_at <= prev_end_dt)
        prev_rev = float(prev_rev_q.scalar())
        
        # Prev COGS
        prev_cogs_q = db.session.query(
            func.sum(OrderItem.quantity * MenuItemIngredient.quantity_needed * Ingredient.cost_per_unit)
        ).select_from(OrderItem)\
         .join(Order, Order.id == OrderItem.order_id)\
         .join(MenuItem, MenuItem.id == OrderItem.menu_item_id)\
         .join(MenuItemIngredient, MenuItemIngredient.menu_item_id == MenuItem.id)\
         .join(Ingredient, Ingredient.id == MenuItemIngredient.ingredient_id)\
         .filter(Order.status == 'COMPLETED')
        if br != 'ALL':
            prev_cogs_q = prev_cogs_q.filter(Order.branch == br)
        prev_cogs_q = prev_cogs_q.filter(Order.created_at >= prev_start_dt, Order.created_at <= prev_end_dt)
        prev_cogs = float(prev_cogs_q.scalar() or 0.0)
        
        prev_profit = prev_rev - prev_cogs
        return {
            'revenue': prev_rev,
            'cogs': prev_cogs,
            'profit': prev_profit
        }

    def get_branch_data(br):
        # Reservation counts by type
        res_q = Reservation.query
        if br != 'ALL':
            res_q = res_q.filter_by(branch=br)
        if start_date and end_date:
            res_q = res_q.filter(Reservation.date >= start_date, Reservation.date <= end_date)
        exclusive_count = res_q.filter_by(booking_type='EXCLUSIVE').count()
        regular_count = res_q.filter_by(booking_type='REGULAR').count()
        total_reservations = res_q.count()

        # Menu items
        menu_q = MenuItem.query.filter_by(is_deleted=False)
        if br != 'ALL':
            menu_q = menu_q.filter_by(branch=br)
        total_menu_items = menu_q.count()

        # 1) Revenue Trend & 3) Daily Orders (OPTIMIZED 1-QUERY AGGREGATION)
        revenue_trend_labels = []
        revenue_trend_data = []
        daily_orders_data = []

        if date_filter == 'TODAY':
            revenue_trend_labels = [f'{h:02d}:00' for h in range(9, 23)]
            h_col = func.extract('hour', Order.created_at)
            hq = db.session.query(
                h_col.label('hr'),
                func.coalesce(func.sum(Order.total_amount), 0).label('rev'),
                func.count(Order.id).label('cnt')
            ).filter(func.date(Order.created_at) == today)
            if br != 'ALL': hq = hq.filter(Order.branch == br)
            h_rows = hq.group_by(h_col).all()
            h_map = {int(r.hr): (float(r.rev or 0), int(r.cnt or 0)) for r in h_rows if r.hr is not None}
            for h in range(9, 23):
                stat = h_map.get(h, (0.0, 0))
                revenue_trend_data.append(stat[0])
                daily_orders_data.append(stat[1])
        else:
            dates = []
            if date_filter == 'WEEK':
                week_start = today - timedelta(days=today.weekday())
                for i in range(7):
                    d = week_start + timedelta(days=i)
                    dates.append(d)
                    revenue_trend_labels.append(d.strftime('%a (%b %d)'))
            elif date_filter == 'MONTH':
                month_start = today.replace(day=1)
                next_month = month_start.month + 1
                year = month_start.year
                if next_month > 12: next_month = 1; year += 1
                days_in_month = (date(year, next_month, 1) - month_start).days
                for i in range(days_in_month):
                    d = month_start + timedelta(days=i)
                    dates.append(d)
                    revenue_trend_labels.append(d.strftime('%d'))
            else: # ALL
                for i in range(6, -1, -1):
                    d = today - timedelta(days=i)
                    dates.append(d)
                    revenue_trend_labels.append(d.strftime('%b %d'))

            if dates:
                d_col = func.date(Order.created_at)
                dq = db.session.query(
                    d_col.label('d'),
                    func.coalesce(func.sum(Order.total_amount), 0).label('rev'),
                    func.count(Order.id).label('cnt')
                ).filter(d_col >= min(dates), d_col <= max(dates))
                if br != 'ALL': dq = dq.filter(Order.branch == br)
                d_rows = dq.group_by(d_col).all()
                d_map = {r.d: (float(r.rev or 0), int(r.cnt or 0)) for r in d_rows if r.d}
                for d in dates:
                    stat = d_map.get(d, (0.0, 0))
                    revenue_trend_data.append(stat[0])
                    daily_orders_data.append(stat[1])

        # 2) Order Status
        status_q = db.session.query(Order.status, func.count(Order.id))
        if br != 'ALL':
            status_q = status_q.filter(Order.branch == br)
        if start_date and end_date:
            status_q = status_q.filter(Order.created_at >= start_dt, Order.created_at <= end_dt)
        order_status_rows = status_q.group_by(Order.status).all()
        order_status_labels = [r[0] for r in order_status_rows] if order_status_rows else ['No Data']
        order_status_data = [r[1] for r in order_status_rows] if order_status_rows else [1]

        daily_orders_labels = list(revenue_trend_labels)

        # 4) Busy Times
        hour_col = func.extract('hour', Order.created_at)
        busy_q = db.session.query(
            hour_col.label('hr'),
            func.count(Order.id)
        )
        if br != 'ALL':
            busy_q = busy_q.filter(Order.branch == br)
        if start_date and end_date:
            busy_q = busy_q.filter(Order.created_at >= start_dt, Order.created_at <= end_dt)
        busy_hours_raw = busy_q.group_by(hour_col).order_by(hour_col).all()
        busy_map = {}
        for h, c in busy_hours_raw:
            if h is not None:
                try:
                    busy_map[int(h)] = int(c or 0)
                except (ValueError, TypeError):
                    pass
        busy_times_labels = [f'{h:02d}:00' for h in range(24)]
        busy_times_data = [busy_map.get(h, 0) for h in range(24)]

        # 5) Top Selling Dishes
        top_dishes_q = db.session.query(
            MenuItem.name,
            func.sum(OrderItem.quantity).label('total_qty')
        ).join(OrderItem, OrderItem.menu_item_id == MenuItem.id)\
         .join(Order, Order.id == OrderItem.order_id)
        if br != 'ALL':
            top_dishes_q = top_dishes_q.filter(Order.branch == br)
        if start_date and end_date:
            top_dishes_q = top_dishes_q.filter(Order.created_at >= start_dt, Order.created_at <= end_dt)
        top_dishes_raw = top_dishes_q.group_by(MenuItem.name)\
         .order_by(func.sum(OrderItem.quantity).desc())\
         .limit(5).all()
        top_dishes_labels = [r[0] for r in top_dishes_raw] if top_dishes_raw else ['No Data']
        top_dishes_data = [int(r[1]) for r in top_dishes_raw] if top_dishes_raw else [0]

        # 6) Monthly Revenue
        monthly_rev_labels = []
        monthly_rev_data = []
        for i in range(5, -1, -1):
            first_of_month = today.replace(day=1)
            m = first_of_month.month - i
            y = first_of_month.year
            while m <= 0:
                m += 12
                y -= 1
            month_start = date(y, m, 1)
            if m == 12:
                month_end = date(y + 1, 1, 1)
            else:
                month_end = date(y, m + 1, 1)
            monthly_rev_labels.append(month_start.strftime('%b %Y'))
            mrev_q = db.session.query(func.coalesce(func.sum(Order.total_amount), 0))\
                .filter(Order.created_at >= datetime.combine(month_start, datetime.min.time()),
                        Order.created_at < datetime.combine(month_end, datetime.min.time()))
            if br != 'ALL':
                mrev_q = mrev_q.filter(Order.branch == br)
            rev = mrev_q.scalar()
            monthly_rev_data.append(float(rev))

        # 7) Customer Loyalty
        order_counts_sub_q = db.session.query(
            Order.user_id,
            func.count(Order.id).label('order_count')
        )
        if br != 'ALL':
            order_counts_sub_q = order_counts_sub_q.filter(Order.branch == br)
        if start_date and end_date:
            order_counts_sub_q = order_counts_sub_q.filter(Order.created_at >= start_dt, Order.created_at <= end_dt)
        order_counts_sub = order_counts_sub_q.group_by(Order.user_id).subquery()
        repeat_customers = db.session.query(func.count()).filter(order_counts_sub.c.order_count > 1).scalar() or 0
        onetime_customers = db.session.query(func.count()).filter(order_counts_sub.c.order_count == 1).scalar() or 0
        loyalty_labels = ['Repeat Customers', 'One-time Customers']
        loyalty_data = [repeat_customers, onetime_customers]
        if repeat_customers == 0 and onetime_customers == 0:
            loyalty_labels = ['No Orders Yet']
            loyalty_data = [1]

        # Total revenue
        trev_q = db.session.query(func.coalesce(func.sum(Order.total_amount), 0))
        if br != 'ALL':
            trev_q = trev_q.filter(Order.branch == br)
        if start_date and end_date:
            trev_q = trev_q.filter(Order.created_at >= start_dt, Order.created_at <= end_dt)
        total_revenue_val = float(trev_q.scalar())

        # 8) Advanced P&L COGS
        cogs_query = db.session.query(
            func.sum(OrderItem.quantity * MenuItemIngredient.quantity_needed * Ingredient.cost_per_unit)
        ).select_from(OrderItem)\
         .join(Order, Order.id == OrderItem.order_id)\
         .join(MenuItem, MenuItem.id == OrderItem.menu_item_id)\
         .join(MenuItemIngredient, MenuItemIngredient.menu_item_id == MenuItem.id)\
         .join(Ingredient, Ingredient.id == MenuItemIngredient.ingredient_id)\
         .filter(Order.status == 'COMPLETED')
        if br != 'ALL':
            cogs_query = cogs_query.filter(Order.branch == br)
        if start_date and end_date:
            cogs_query = cogs_query.filter(Order.created_at >= start_dt, Order.created_at <= end_dt)
        total_cogs = float(cogs_query.scalar() or 0.0)
        net_profit = total_revenue_val - total_cogs

        # 9) Sales Forecast — Linear Regression on last 30 days (OPTIMIZED 1 QUERY)
        thirty_days_ago = today - timedelta(days=29)
        d_col = func.date(Order.created_at)
        fc_q = db.session.query(
            d_col.label('d'),
            func.coalesce(func.sum(Order.total_amount), 0).label('rev')
        ).filter(
            d_col >= thirty_days_ago,
            Order.status == 'COMPLETED'
        )
        if br != 'ALL':
            fc_q = fc_q.filter(Order.branch == br)
        fc_rows = fc_q.group_by(d_col).all()
        fc_map = {r.d: float(r.rev or 0) for r in fc_rows if r.d}
        daily_rev = [fc_map.get(today - timedelta(days=i), 0.0) for i in range(29, -1, -1)]

        n = len(daily_rev)  # 30
        x_mean = (n - 1) / 2.0
        y_mean = sum(daily_rev) / n if n else 0
        numerator   = sum((i - x_mean) * (daily_rev[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope     = numerator / denominator if denominator != 0 else 0
        intercept = y_mean - slope * x_mean

        last_7 = daily_rev[-7:] if len(daily_rev) >= 7 else daily_rev
        sma_7   = sum(last_7) / len(last_7) if last_7 else 0
        avg_dev = sum(abs(v - sma_7) for v in last_7) / len(last_7) if last_7 else 0

        forecast_labels = []
        forecast_data   = []
        for i in range(1, 8):
            future_date  = today + timedelta(days=i)
            trend_val    = intercept + slope * (n - 1 + i)
            day_offset   = avg_dev * 0.3 * ((-1) ** i)
            projected    = max(0, round(trend_val + day_offset, 2))
            forecast_labels.append(future_date.strftime('%b %d'))
            forecast_data.append(projected)

        # 10) Booking Type Distribution
        bookings_dist_labels = ['Standard Bookings', 'Exclusive Bookings']
        bookings_dist_data = [regular_count, exclusive_count]

        # 11) Dining Options (Order Types)
        dining_q = db.session.query(Order.dining_option, func.count(Order.id))
        if br != 'ALL':
            dining_q = dining_q.filter(Order.branch == br)
        if start_date and end_date:
            dining_q = dining_q.filter(Order.created_at >= start_dt, Order.created_at <= end_dt)
        dining_rows = dining_q.group_by(Order.dining_option).all()
        dining_labels = [r[0].replace('_', ' ').title() for r in dining_rows] if dining_rows else ['No Data']
        dining_data = [r[1] for r in dining_rows] if dining_rows else [0]

        # 12) Payment Methods
        pay_q = db.session.query(Order.payment_method, func.count(Order.id))
        if br != 'ALL':
            pay_q = pay_q.filter(Order.branch == br)
        if start_date and end_date:
            pay_q = pay_q.filter(Order.created_at >= start_dt, Order.created_at <= end_dt)
        pay_rows = pay_q.group_by(Order.payment_method).all()
        pay_labels = [r[0].title() for r in pay_rows] if pay_rows else ['No Data']
        pay_data = [r[1] for r in pay_rows] if pay_rows else [0]

        # 13) Top Categories
        cat_q_main = db.session.query(MenuItem.category, func.sum(OrderItem.quantity))\
            .join(OrderItem, MenuItem.id == OrderItem.menu_item_id)\
            .join(Order, Order.id == OrderItem.order_id)\
            .filter(Order.status == 'COMPLETED')
        if br != 'ALL':
            cat_q_main = cat_q_main.filter(Order.branch == br)
        if start_date and end_date:
            cat_q_main = cat_q_main.filter(Order.created_at >= start_dt, Order.created_at <= end_dt)
        cat_rows_main = cat_q_main.group_by(MenuItem.category).order_by(func.sum(OrderItem.quantity).desc()).limit(5).all()
        top_categories_labels = [r[0].title() for r in cat_rows_main] if cat_rows_main else ['No Data']
        top_categories_data = [float(r[1]) for r in cat_rows_main] if cat_rows_main else [0]

        if date_filter == 'ALL':
            curr_30_start_dt = datetime.combine(today - timedelta(days=29), datetime.min.time())
            curr_30_end_dt = datetime.combine(today, datetime.max.time())
            prev_30_start_dt = datetime.combine(today - timedelta(days=59), datetime.min.time())
            prev_30_end_dt = datetime.combine(today - timedelta(days=30), datetime.max.time())
            
            def get_30_day_stats(br, start, end):
                rev_q = db.session.query(func.coalesce(func.sum(Order.total_amount), 0))
                if br != 'ALL':
                    rev_q = rev_q.filter(Order.branch == br)
                rev_q = rev_q.filter(Order.created_at >= start, Order.created_at <= end)
                rev = float(rev_q.scalar())
                
                cogs_q = db.session.query(
                    func.sum(OrderItem.quantity * MenuItemIngredient.quantity_needed * Ingredient.cost_per_unit)
                ).select_from(OrderItem)\
                 .join(Order, Order.id == OrderItem.order_id)\
                 .join(MenuItem, MenuItem.id == OrderItem.menu_item_id)\
                 .join(MenuItemIngredient, MenuItemIngredient.menu_item_id == MenuItem.id)\
                 .join(Ingredient, Ingredient.id == MenuItemIngredient.ingredient_id)\
                 .filter(Order.status == 'COMPLETED')
                if br != 'ALL':
                    cogs_q = cogs_q.filter(Order.branch == br)
                cogs_q = cogs_q.filter(Order.created_at >= start, Order.created_at <= end)
                cogs = float(cogs_q.scalar() or 0.0)
                
                profit = rev - cogs
                return {'revenue': rev, 'cogs': cogs, 'profit': profit}
                
            curr_30 = get_30_day_stats(br, curr_30_start_dt, curr_30_end_dt)
            prev_30 = get_30_day_stats(br, prev_30_start_dt, prev_30_end_dt)
            
            trends = {}
            for key in ['revenue', 'cogs', 'profit']:
                cur_val = curr_30[key]
                prev_val = prev_30[key]
                if prev_val > 0:
                    pct = ((cur_val - prev_val) / prev_val) * 100
                elif cur_val > 0:
                    pct = 100.0
                else:
                    pct = 0.0
                trends[key] = round(pct, 2)
            has_prev = True
        else:
            prev_stats = get_prev_period_stats(br)
            trends = {}
            if prev_stats:
                for key, cur_val in [('revenue', total_revenue_val), ('cogs', total_cogs), ('profit', net_profit)]:
                    prev_val = prev_stats[key]
                    if prev_val > 0:
                        pct = ((cur_val - prev_val) / prev_val) * 100
                    elif cur_val > 0:
                        pct = 100.0
                    else:
                        pct = 0.0
                    trends[key] = round(pct, 2)
                has_prev = True
            else:
                trends = {'revenue': 0.0, 'cogs': 0.0, 'profit': 0.0}
                has_prev = False

        # Precompute multi-timeframe data for interactive charts
        multi_timeframe_charts = {
            'bookings_dist': {},
            'dining_options': {},
            'payment_methods': {},
            'revenue_trend': {},
            'top_categories': {}
        }
        
        tf_bounds = {
            'TODAY': (datetime.combine(today, datetime.min.time()), datetime.combine(today, datetime.max.time())),
            'WEEK': (datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time()), datetime.combine(today - timedelta(days=today.weekday()) + timedelta(days=6), datetime.max.time())),
            'MONTH': (datetime.combine(today.replace(day=1), datetime.min.time()), datetime.combine(today, datetime.max.time())),
            'ALL': (None, None)
        }
        
        for tf_key, (st_dt, en_dt) in tf_bounds.items():
            reg_q = db.session.query(func.count(Reservation.id)).filter(Reservation.booking_type == 'REGULAR', Reservation.status != 'REJECTED')
            exc_q = db.session.query(func.count(Reservation.id)).filter(Reservation.booking_type == 'EXCLUSIVE', Reservation.status != 'REJECTED')
            din_q = db.session.query(Order.dining_option, func.count(Order.id))
            pay_q = db.session.query(Order.payment_method, func.count(Order.id))
            cat_q = db.session.query(MenuItem.category, func.sum(OrderItem.quantity)).join(OrderItem, MenuItem.id == OrderItem.menu_item_id).join(Order, Order.id == OrderItem.order_id).filter(Order.status == 'COMPLETED')
            
            if br != 'ALL':
                reg_q = reg_q.filter(Reservation.branch == br)
                exc_q = exc_q.filter(Reservation.branch == br)
                din_q = din_q.filter(Order.branch == br)
                pay_q = pay_q.filter(Order.branch == br)
                cat_q = cat_q.filter(Order.branch == br)
                
            if st_dt and en_dt:
                reg_q = reg_q.filter(Reservation.date >= st_dt.date(), Reservation.date <= en_dt.date())
                exc_q = exc_q.filter(Reservation.date >= st_dt.date(), Reservation.date <= en_dt.date())
                din_q = din_q.filter(Order.created_at >= st_dt, Order.created_at <= en_dt)
                pay_q = pay_q.filter(Order.created_at >= st_dt, Order.created_at <= en_dt)
                cat_q = cat_q.filter(Order.created_at >= st_dt, Order.created_at <= en_dt)
                
            multi_timeframe_charts['bookings_dist'][tf_key] = {
                'labels': ['Standard Bookings', 'Exclusive Bookings'],
                'data': [reg_q.scalar() or 0, exc_q.scalar() or 0]
            }
            
            din_rows = din_q.group_by(Order.dining_option).all()
            multi_timeframe_charts['dining_options'][tf_key] = {
                'labels': [r[0].replace('_', ' ').title() for r in din_rows] if din_rows else ['No Data'],
                'data': [r[1] for r in din_rows] if din_rows else [0]
            }
            
            pay_rows = pay_q.group_by(Order.payment_method).all()
            multi_timeframe_charts['payment_methods'][tf_key] = {
                'labels': [r[0].title() for r in pay_rows] if pay_rows else ['No Data'],
                'data': [r[1] for r in pay_rows] if pay_rows else [0]
            }
            
            cat_rows = cat_q.group_by(MenuItem.category).order_by(func.sum(OrderItem.quantity).desc()).limit(5).all()
            multi_timeframe_charts['top_categories'][tf_key] = {
                'labels': [r[0].title() for r in cat_rows] if cat_rows else ['No Data'],
                'data': [float(r[1]) for r in cat_rows] if cat_rows else [0]
            }
            
            tf_rev_labels = []
            tf_rev_data = []
            if tf_key == 'TODAY':
                tf_rev_labels = [f'{h:02d}:00' for h in range(9, 23)]
                h_col = func.extract('hour', Order.created_at)
                q = db.session.query(
                    h_col.label('hr'),
                    func.coalesce(func.sum(Order.total_amount), 0).label('rev')
                ).filter(func.date(Order.created_at) == today)
                if br != 'ALL': q = q.filter(Order.branch == br)
                h_rows = q.group_by(h_col).all()
                h_map = {int(r.hr): float(r.rev or 0) for r in h_rows if r.hr is not None}
                tf_rev_data = [h_map.get(h, 0.0) for h in range(9, 23)]
            else:
                tf_dates = []
                if tf_key == 'WEEK':
                    ws = today - timedelta(days=today.weekday())
                    for i in range(7):
                        d = ws + timedelta(days=i)
                        tf_dates.append(d)
                        tf_rev_labels.append(d.strftime('%a (%b %d)'))
                elif tf_key == 'MONTH':
                    ms = today.replace(day=1)
                    nm = ms.month + 1
                    yr = ms.year
                    if nm > 12: nm = 1; yr += 1
                    dim = (date(yr, nm, 1) - ms).days
                    for i in range(dim):
                        d = ms + timedelta(days=i)
                        tf_dates.append(d)
                        tf_rev_labels.append(d.strftime('%d'))
                elif tf_key == 'ALL':
                    for i in range(6, -1, -1):
                        d = today - timedelta(days=i)
                        tf_dates.append(d)
                        tf_rev_labels.append(d.strftime('%b %d'))

                if tf_dates:
                    d_col = func.date(Order.created_at)
                    q = db.session.query(
                        d_col.label('d'),
                        func.coalesce(func.sum(Order.total_amount), 0).label('rev')
                    ).filter(d_col >= min(tf_dates), d_col <= max(tf_dates))
                    if br != 'ALL': q = q.filter(Order.branch == br)
                    d_rows = q.group_by(d_col).all()
                    d_map = {r.d: float(r.rev or 0) for r in d_rows if r.d}
                    tf_rev_data = [d_map.get(d, 0.0) for d in tf_dates]
                    
            multi_timeframe_charts['revenue_trend'][tf_key] = {
                'labels': tf_rev_labels,
                'data': tf_rev_data
            }

        return {
            'stats': {
                'total_menu_items': total_menu_items,
                'exclusive_count': exclusive_count,
                'regular_count': regular_count,
                'total_reservations': total_reservations,
                'total_revenue': total_revenue_val,
                'total_cogs': total_cogs,
                'net_profit': net_profit,
                'trends': trends,
                'has_prev_period': has_prev
            },
            'charts': {
                'forecast': {'labels': forecast_labels, 'data': forecast_data},
                'revenue_trend': {'labels': revenue_trend_labels, 'data': revenue_trend_data},
                'order_status': {'labels': order_status_labels, 'data': order_status_data},
                'daily_orders': {'labels': daily_orders_labels, 'data': daily_orders_data},
                'busy_times': {'labels': busy_times_labels, 'data': busy_times_data},
                'top_dishes': {'labels': top_dishes_labels, 'data': top_dishes_data},
                'monthly_rev': {'labels': monthly_rev_labels, 'data': monthly_rev_data},
                'loyalty': {'labels': loyalty_labels, 'data': loyalty_data},
                'bookings_dist': {'labels': bookings_dist_labels, 'data': bookings_dist_data},
                'dining_options': {'labels': dining_labels, 'data': dining_data},
                'payment_methods': {'labels': pay_labels, 'data': pay_data},
                'top_categories': {'labels': top_categories_labels, 'data': top_categories_data},
            },
            'multi_timeframe_charts': multi_timeframe_charts
        }

    user_role = current_user.role.upper()
    selected_branch = 'ALL'
    branches_data = {}
    if user_role == 'SUPER_ADMIN':
        selected_branch = request.args.get('branch', 'ALL')
        if selected_branch not in ['ALL', 'Pagsanjan', 'Lucban']:
            selected_branch = 'ALL'
        branches_data['ALL'] = get_branch_data('ALL')
        if selected_branch != 'ALL':
            branches_data[selected_branch] = get_branch_data(selected_branch)
        for b in ['Pagsanjan', 'Lucban']:
            if b not in branches_data:
                branches_data[b] = get_branch_data(b)
    else:
        user_branch = getattr(current_user, 'branch', 'Pagsanjan')
        selected_branch = user_branch
        branches_data[user_branch] = get_branch_data(user_branch)

    current_data = branches_data[selected_branch]

    return render_template('admin/analytics.html',
        total_customers=total_customers,
        total_menu_items=current_data['stats']['total_menu_items'],
        exclusive_count=current_data['stats']['exclusive_count'],
        regular_count=current_data['stats']['regular_count'],
        total_reservations=current_data['stats']['total_reservations'],
        total_revenue=current_data['stats']['total_revenue'],
        total_cogs=current_data['stats']['total_cogs'],
        net_profit=current_data['stats']['net_profit'],
        forecast_labels=_json.dumps(current_data['charts']['forecast']['labels']),
        forecast_data=_json.dumps(current_data['charts']['forecast']['data']),
        revenue_trend_labels=_json.dumps(current_data['charts']['revenue_trend']['labels']),
        revenue_trend_data=_json.dumps(current_data['charts']['revenue_trend']['data']),
        order_status_labels=_json.dumps(current_data['charts']['order_status']['labels']),
        order_status_data=_json.dumps(current_data['charts']['order_status']['data']),
        daily_orders_labels=_json.dumps(current_data['charts']['daily_orders']['labels']),
        daily_orders_data=_json.dumps(current_data['charts']['daily_orders']['data']),
        busy_times_labels=_json.dumps(current_data['charts']['busy_times']['labels']),
        busy_times_data=_json.dumps(current_data['charts']['busy_times']['data']),
        top_dishes_labels=_json.dumps(current_data['charts']['top_dishes']['labels']),
        top_dishes_data=_json.dumps(current_data['charts']['top_dishes']['data']),
        monthly_rev_labels=_json.dumps(current_data['charts']['monthly_rev']['labels']),
        monthly_rev_data=_json.dumps(current_data['charts']['monthly_rev']['data']),
        loyalty_labels=_json.dumps(current_data['charts']['loyalty']['labels']),
        loyalty_data=_json.dumps(current_data['charts']['loyalty']['data']),
        bookings_dist_labels=_json.dumps(current_data['charts']['bookings_dist']['labels']),
        bookings_dist_data=_json.dumps(current_data['charts']['bookings_dist']['data']),
        dining_options_labels=_json.dumps(current_data['charts']['dining_options']['labels']),
        dining_options_data=_json.dumps(current_data['charts']['dining_options']['data']),
        payment_methods_labels=_json.dumps(current_data['charts']['payment_methods']['labels']),
        payment_methods_data=_json.dumps(current_data['charts']['payment_methods']['data']),
        top_categories_labels=_json.dumps(current_data['charts']['top_categories']['labels']),
        top_categories_data=_json.dumps(current_data['charts']['top_categories']['data']),
        get_ph_time=get_ph_time,
        selected_branch=selected_branch,
        all_branches_data_json=_json.dumps(branches_data),
        selected_date_filter=date_filter
    )

@admin_bp.route('/analytics/export')
@login_required
@admin_required
def analytics_export():
    if current_user.role.upper() not in ('ADMIN', 'SUPER_ADMIN'):
        return "Access Denied", 403

    import csv
    from io import StringIO
    from flask import make_response

    branch = request.args.get('branch', 'ALL')
    date_filter = request.args.get('date_filter', 'ALL').upper()

    today = get_ph_time().date()
    start_date = None
    end_date = None
    start_dt = None
    end_dt = None

    if date_filter == 'TODAY':
        start_date = today
        end_date = today
    elif date_filter == 'WEEK':
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    elif date_filter == 'MONTH':
        start_date = today.replace(day=1)
        next_month = today.month + 1
        year = today.year
        if next_month > 12:
            next_month = 1
            year += 1
        end_date = date(year, next_month, 1) - timedelta(days=1)

    if start_date and end_date:
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

    orders_q = Order.query
    if branch != 'ALL':
        orders_q = orders_q.filter(Order.branch == branch)
    if start_date and end_date:
        orders_q = orders_q.filter(Order.created_at >= start_dt, Order.created_at <= end_dt)
    
    orders = orders_q.order_by(Order.created_at.desc()).all()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Order ID', 'Order Code', 'Branch', 'Customer Name', 'Date', 'Dining Option', 'Payment Method', 'Status', 'Total Amount'])
    for o in orders:
        cw.writerow([
            o.id,
            o.order_code or 'N/A',
            o.branch or 'N/A',
            o.customer_name or 'N/A',
            o.created_at.strftime('%Y-%m-%d %H:%M:%S') if o.created_at else 'N/A',
            o.dining_option or 'N/A',
            o.payment_method or 'N/A',
            o.status or 'N/A',
            float(o.total_amount)
        ])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=Le_Maison_Analytics_Report_{branch}_{date_filter}.csv"
    output.headers["Content-type"] = "text/csv"
    return output

MENU_CATEGORIES = [
    "All Day Breakfast",
    "Cakes & Pastries",
    "Cocktails",
    "Desserts",
    "Frappes",
    "Fruit Shakes & Yogurt Drinks",
    "Hand-Tossed Pizza",
    "Hot Coffee",
    "Iced Beverages",
    "Iced Coffee",
    "Milk Tea",
    "Milkshakes & Smoothies",
    "Pasta & Salads",
    "Rice Plates",
    "Starters & Sandwiches",
    "Steaks",
    "Sweet Breakfast",
    "Thin Crust Pizza",
]

# ─── MAIN: MENU ─────────────────────────────────────
@admin_bp.route('/menu')
@login_required
@requires_permission('menu.view')
def menu():
    # Fetch all items counts per category (excluding deleted)
    raw_counts = db.session.query(MenuItem.category, func.count(MenuItem.id))\
        .filter(MenuItem.is_deleted == False)\
        .group_by(MenuItem.category).all()
    counts_map = {cat: count for cat, count in raw_counts}
    
    # Fetch out of stock counts (excluding deleted)
    oos_raw = db.session.query(MenuItem.category, func.count(MenuItem.id))\
        .filter(MenuItem.is_available == False, MenuItem.is_deleted == False)\
        .group_by(MenuItem.category).all()
    oos_map = {cat: count for cat, count in oos_raw}
    
    enriched_categories = []
    for cat_name in MENU_CATEGORIES:
        enriched_categories.append({
            'name': cat_name,
            'item_count': counts_map.get(cat_name, 0),
            'oos_count': oos_map.get(cat_name, 0)
        })

    return render_template(
        'admin/menu.html',
        categories_list=enriched_categories,
    )

@admin_bp.route('/menu/item/<int:item_id>', methods=['GET'])
@login_required
@requires_permission('menu.view')
def menu_item_json(item_id):
    item = MenuItem.query.get_or_404(item_id)
    return jsonify({
        'id': item.id,
        'name': item.name,
        'description': item.description or '',
        'price': float(item.price or 0),
        'category': item.category,
        'image_url': item.image_url or '',
        'is_available': bool(item.is_available),
        'is_bestseller': bool(item.is_bestseller),
    })

@admin_bp.route('/menu/items', methods=['GET'])
@login_required
@requires_permission('menu.view')
def menu_items_json():
    """Lazy-load menu items per category (keeps /admin/menu page fast)."""
    category = (request.args.get('category') or '').strip()
    if category not in MENU_CATEGORIES:
        return jsonify({'success': False, 'message': 'Invalid category'}), 400

    limit = request.args.get('limit', 200, type=int)
    offset = request.args.get('offset', 0, type=int)
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    fetch_limit = limit + 1  # one extra to detect "has_more" without COUNT(*)
    items = (
        MenuItem.query.options(
            load_only(
                MenuItem.id,
                MenuItem.item_code,
                MenuItem.name,
                MenuItem.description,
                MenuItem.price,
                MenuItem.category,
                MenuItem.image_url,
                MenuItem.is_available,
                MenuItem.is_bestseller,
            )
        )
        .filter(MenuItem.category == category, MenuItem.is_deleted == False)
        .order_by(MenuItem.name.asc())
        .offset(offset)
        .limit(fetch_limit)
        .all()
    )

    has_more = len(items) > limit
    if has_more:
        items = items[:limit]

    return jsonify({
        'success': True,
        'offset': offset,
        'limit': limit,
        'has_more': has_more,
        'items': [{
            'id': i.id,
            'item_code': i.item_code or '',
            'name': i.name,
            'description': i.description or '',
            'price': float(i.price or 0),
            'category': i.category,
            'image_url': i.image_url or '',
            'is_available': bool(i.is_available),
            'is_bestseller': bool(i.is_bestseller),
        } for i in items],
    })

@admin_bp.route('/menu/add', methods=['POST'])
@login_required
@requires_permission('menu.create')
def menu_add():
    name = (request.form.get('name') or '').strip()[:50]
    description = request.form.get('description', '')[:255]
    category = request.form.get('category', '')
    is_bestseller = 'is_bestseller' in request.form
    image_url = (request.form.get('image_url') or '')[:255]

    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB upload limit
    image_file = request.files.get('image_file')
    if image_file and image_file.filename:
        import os, uuid
        from werkzeug.utils import secure_filename
        from utils import save_optimized_image
        
        image_file.seek(0, os.SEEK_END)
        file_size = image_file.tell()
        image_file.seek(0)
        if file_size > MAX_FILE_SIZE:
            flash("Image file size exceeds the 5MB limit. Please choose a file under 5MB.", "warning")
            return redirect(url_for('admin.menu', category=category))

        ext = os.path.splitext(secure_filename(image_file.filename))[1].lower() or '.jpg'
        filename = f"menu_{uuid.uuid4().hex[:10]}{ext}"
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'menu')
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, filename)
        if save_optimized_image(image_file, filepath, max_dim=(800, 800), quality=75):
            image_url = f"/static/uploads/menu/{filename}"

    try:
        price = float(request.form.get('price', 0))
        if price < 0 or price >= 100000:
            price = 0
    except (ValueError, TypeError):
        price = 0

    if not name:
        flash("Item name is required.", "danger")
        return redirect(url_for('admin.menu'))

    try:
        # Generate unique item code
        from utils import generate_menu_item_code
        item_code = generate_menu_item_code(category)
        
        item = MenuItem(
            item_code=item_code,
            name=name,
            description=description,
            price=price,
            category=category,
            image_url=image_url,
            is_available=False,  # Automatically false until ingredients are assigned
            is_bestseller=is_bestseller
        )
        db.session.add(item)
        db.session.commit()
        log_audit('CREATE', 'MenuItem', item.id, f'Added new menu item: {item.name} ({item_code})')
        flash(f"Menu item added successfully with code: {item_code}", "success")
        return redirect(url_for('admin.menu', category=item.category))
    except Exception as e:
        db.session.rollback()
        flash(f"Error adding item: {str(e)}", "danger")
        return redirect(url_for('admin.menu'))

@admin_bp.route('/menu/edit/<int:item_id>', methods=['POST'])
@login_required
@requires_permission('menu.edit')
def menu_edit(item_id):
    item = MenuItem.query.get_or_404(item_id)

    name = (request.form.get('name') or '').strip()[:50]
    description = request.form.get('description', '')[:255]
    category = request.form.get('category', '')
    is_bestseller = 'is_bestseller' in request.form

    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB upload limit
    image_file = request.files.get('image_file')
    if image_file and image_file.filename:
        import os, uuid
        from werkzeug.utils import secure_filename
        from utils import save_optimized_image

        image_file.seek(0, os.SEEK_END)
        file_size = image_file.tell()
        image_file.seek(0)
        if file_size > MAX_FILE_SIZE:
            flash("Image file size exceeds the 5MB limit. Please choose a file under 5MB.", "warning")
            return redirect(url_for('admin.menu', category=category))

        ext = os.path.splitext(secure_filename(image_file.filename))[1].lower() or '.jpg'
        filename = f"menu_{uuid.uuid4().hex[:10]}{ext}"
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'menu')
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, filename)
        if save_optimized_image(image_file, filepath, max_dim=(800, 800), quality=75):
            item.image_url = f"/static/uploads/menu/{filename}"
    elif request.form.get('image_url') is not None:
        item.image_url = (request.form.get('image_url') or '').strip()[:255]

    try:
        price = float(request.form.get('price', 0))
        if price < 0 or price >= 100000:
            price = float(item.price)
    except (ValueError, TypeError):
        price = float(item.price)

    if not name:
        flash("Item name is required.", "danger")
        return redirect(url_for('admin.menu', category=item.category))

    try:
        item.name = name
        item.description = description
        item.price = price
        item.category = category
        item.is_bestseller = is_bestseller
        # is_available is handled automatically by recipe sync logic now
        db.session.commit()
        log_audit('UPDATE', 'MenuItem', item.id, f'Updated menu item: {item.name}')
        flash("Menu item updated.", "success")
        return redirect(url_for('admin.menu', category=item.category))
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating item: {str(e)}", "danger")
        return redirect(url_for('admin.menu', category=item.category))

@admin_bp.route('/menu/delete/<int:item_id>', methods=['POST'])
@login_required
@requires_permission('menu.delete')
def menu_delete(item_id):
    item = MenuItem.query.get_or_404(item_id)
    category = item.category
    item.is_deleted = True
    db.session.commit()
    log_audit('DELETE', 'MenuItem', item_id, f'Trashed menu item: {item.name}')
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Item moved to trash.'})
        
    flash("Menu item moved to trash.", "success")
    return redirect(url_for('admin.menu', category=category))

@admin_bp.route('/menu/trash')
@login_required
@requires_permission('menu.view')
def menu_trash():
    """View items that have been moved to trash."""
    trashed_items = MenuItem.query.filter_by(is_deleted=True).order_by(MenuItem.created_at.desc()).all()
    return render_template('admin/menu_trash.html', items=trashed_items)

@admin_bp.route('/menu/restore/<int:item_id>', methods=['POST'])
@login_required
@requires_permission('menu.edit')
def menu_restore(item_id):
    """Restore a trashed menu item."""
    item = MenuItem.query.get_or_404(item_id)
    item.is_deleted = False
    db.session.commit()
    log_audit('RESTORE', 'MenuItem', item_id, f'Restored menu item: {item.name}')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if is_ajax:
        return jsonify({'success': True, 'message': f"Restored '{item.name}' successfully."})
    flash(f"Restored '{item.name}' successfully.", "success")
    return redirect(url_for('admin.menu_trash'))

# ─── MANAGEMENT: ACCOUNT APPROVALS ──────────────────
@admin_bp.route('/approvals')
@login_required
@admin_required
def approvals():
    if current_user.role.upper() not in ['ADMIN', 'SUPER_ADMIN']:
        flash("Access denied.", "danger")
        return redirect(url_for('admin.overview'))

    user_branch = getattr(current_user, 'branch', None)
    if current_user.role.upper() == 'ADMIN':
        if user_branch and user_branch != 'ALL':
            pending = User.query.filter_by(status='PENDING', role='USER', is_verified=True)\
                                .filter(User.branch == user_branch)\
                                .limit(300).all()
        else:
            pending = User.query.filter_by(status='PENDING', role='USER', is_verified=True).limit(300).all()
    else:
        pending = User.query.filter_by(status='PENDING', role='USER', is_verified=True).limit(300).all()

    return render_template('admin/approvals.html', pending=pending)

@admin_bp.route('/staff-approvals')
@login_required
@admin_required
def staff_approvals():
    if current_user.role.upper() not in ['ADMIN', 'SUPER_ADMIN']:
        flash("Access denied.", "danger")
        return redirect(url_for('admin.overview'))

    user_branch = getattr(current_user, 'branch', None)
    query = User.query.filter_by(status='PENDING', is_verified=True).filter(User.role != 'USER')
    
    if current_user.role.upper() == 'ADMIN':
        if user_branch and user_branch != 'ALL':
            query = query.filter(User.branch == user_branch)
            
    pending = query.limit(300).all()
    return render_template('admin/staff_approvals.html', pending=pending)

@admin_bp.route('/approve/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def approve_user(user_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    user = User.query.get_or_404(user_id)

    # Branch admin validation
    if current_user.role.upper() == 'ADMIN':
        user_branch = getattr(current_user, 'branch', None)
        if user_branch and user_branch != 'ALL' and user.branch != user_branch:
            msg = "You are not authorized to approve accounts from other branches."
            if is_ajax: return jsonify({'success': False, 'message': msg})
            flash(msg, "danger")
            return redirect(url_for('admin.approvals'))

    user.status = 'ACTIVE'
    db.session.commit()
    
    # Send approval email
    try:
        msg = Message(
            subject='Le Maison Yelo Lane - Account Approved! 🎉',
            sender=current_app.config['MAIL_USERNAME'],
            recipients=[user.email]
        )
        msg.html = f"""
        <div style="background-color: #f8f5f2; padding: 40px 20px; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; line-height: 1.6;">
            <div style="max-width: 550px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 30px rgba(93, 64, 55, 0.08); border: 1px solid #e8e0d8;">
                <div style="background-color: #5d4037; padding: 30px; text-align: center;">
                    <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 300; letter-spacing: 1px;">LE MAISON YELO LANE</h1>
                </div>
                <div style="padding: 40px 35px; color: #4e342e;">
                    <div style="text-align: center; margin-bottom: 25px;">
                        <span style="display: inline-block; background-color: #e8f5e9; color: #2e7d32; width: 60px; height: 60px; border-radius: 50%; line-height: 60px; font-size: 30px;">✓</span>
                    </div>
                    <h2 style="text-align: center; color: #2e7d32; font-size: 22px; margin-bottom: 20px;">Account Approved!</h2>
                    <p style="font-size: 16px; margin-bottom: 20px;">Hello <strong>{user.first_name}</strong>,</p>
                    <p style="font-size: 15px; color: #6d4c41;">Great news! Your account has been reviewed and approved by our team. You now have full access to everything Le Maison Yelo Lane has to offer:</p>
                    <div style="background-color: #fcfaf8; border-radius: 12px; padding: 20px; margin: 25px 0; border: 1px inset #efebe9;">
                        <ul style="margin: 0; padding: 0; list-style: none;">
                            <li style="margin-bottom: 12px; padding-left: 25px; position: relative;">
                                <span style="position: absolute; left: 0; color: #8d6e63;">☕</span> Browse and order from our menu
                            </li>
                            <li style="margin-bottom: 12px; padding-left: 25px; position: relative;">
                                <span style="position: absolute; left: 0; color: #8d6e63;">📅</span> Make table reservations
                            </li>
                            <li style="margin-bottom: 0; padding-left: 25px; position: relative;">
                                <span style="position: absolute; left: 0; color: #8d6e63;">⭐</span> Rate and review your favorite dishes
                            </li>
                        </ul>
                    </div>
                    <div style="text-align: center; margin: 35px 0;">
                        <a href="https://le-maison-yelo-lane.loca.lt/login" style="display: inline-block; background-color: #5d4037; color: #ffffff; font-weight: 600; text-decoration: none; padding: 15px 45px; border-radius: 30px; font-size: 16px; transition: background 0.3s;">Access My Account</a>
                    </div>
                    <hr style="border: 0; border-top: 1px solid #efebe9; margin: 30px 0;">
                    <p style="font-size: 13px; color: #a1887f; text-align: center; margin: 0;">We're excited to have you with us!<br><strong>Le Maison Yelo Lane</strong></p>
                </div>
            </div>
        </div>
        """
        app_obj = current_app._get_current_object()
        threading.Thread(
            target=_send_flask_mail_worker,
            args=(app_obj, msg),
            daemon=True
        ).start()
    except Exception as e:
        print(f"Approval email failed: {e}")
        traceback.print_exc()
    
    # Create in-app notification for user
    _create_web_notification(user.id, 'Account Approved! 🎉', 'Your account has been approved. You can now log in and enjoy all features!', 'SYSTEM')
    
    log_audit('UPDATE', 'User', user.id, f'Approved user registration for {user.username}')
    if is_ajax:
        return jsonify({'success': True, 'message': f'User {user.username} approved successfully.', 'user_id': user_id})
    flash(f"User {user.username} approved.", "success")
    return redirect(url_for('admin.staff_approvals'))

@admin_bp.route('/reject/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def reject_user(user_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    user = User.query.get_or_404(user_id)

    # Branch admin validation
    if current_user.role.upper() == 'ADMIN':
        user_branch = getattr(current_user, 'branch', None)
        if user_branch and user_branch != 'ALL' and user.branch != user_branch:
            msg = "You are not authorized to reject accounts from other branches."
            if is_ajax: return jsonify({'success': False, 'message': msg})
            flash(msg, "danger")
            return redirect(url_for('admin.staff_approvals'))

    user.status = 'REJECTED'
    db.session.commit()
    _create_web_notification(user.id, 'Account Update', 'Your account registration was not approved. Please contact us for more information.', 'SYSTEM')
    
    log_audit('UPDATE', 'User', user.id, f'Rejected user registration for {user.username}')
    if is_ajax:
        return jsonify({'success': True, 'message': f'User {user.username} rejected.', 'user_id': user_id})
    flash(f"User {user.username} rejected.", "warning")
    return redirect(url_for('admin.staff_approvals'))

# ─── MANAGEMENT: STAFF MANAGEMENT ────────────────────
@admin_bp.route('/staff')
@login_required
@admin_required
def staff_management():
    page = request.args.get('page', 1, type=int)
    role_filter = request.args.get('role', 'ALL')
    
    # Show active staff only
    query = User.query.filter(User.role != 'USER', User.status == 'ACTIVE')
    user_branch = getattr(current_user, 'branch', None)
    if user_branch and user_branch != 'ALL':
        query = query.filter(User.branch == user_branch)
        
    if role_filter != 'ALL':
        query = query.filter(User.role == role_filter)
        
    pagination = query.order_by(User.id.desc()).paginate(page=page, per_page=100, error_out=False)
    return render_template('admin/staff.html', users=pagination, role_filter=role_filter)

@admin_bp.route('/staff/<int:user_id>/update-role', methods=['POST'])
@login_required
@admin_required
def update_staff_role(user_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    user = User.query.get_or_404(user_id)
    
    if user.role == 'USER':
        msg = "Cannot change role for regular customers."
        if is_ajax: return jsonify({'success': False, 'message': msg})
        flash(msg, 'danger')
        return redirect(url_for('admin.staff_management'))

    new_role = request.form.get('role')
    valid_roles = ['ADMIN', 'SUPER_ADMIN', 'CASHIER', 'INVENTORY_STAFF', 'KITCHEN', 'RIDER']
    if not new_role or new_role not in valid_roles:
        msg = "Invalid role selected."
        if is_ajax: return jsonify({'success': False, 'message': msg})
        flash(msg, 'danger')
        return redirect(url_for('admin.staff_management'))
        
    old_role = user.role
    user.role = new_role
    db.session.commit()
    
    log_audit('UPDATE', 'User', user.id, f"Changed role of {user.username} from {old_role} to {new_role}")
    
    msg = f"Role updated for {user.username} to {new_role}."
    if is_ajax: return jsonify({'success': True, 'message': msg, 'new_role': new_role})
    flash(msg, "success")
    return redirect(url_for('admin.staff_management'))

@admin_bp.route('/staff/<int:user_id>/update-branch', methods=['POST'])
@login_required
@admin_required
def update_staff_branch(user_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    user = User.query.get_or_404(user_id)
    
    if user.role == 'USER':
        msg = "Cannot change branch for regular customers."
        if is_ajax: return jsonify({'success': False, 'message': msg})
        flash(msg, 'danger')
        return redirect(url_for('admin.staff_management'))

    new_branch = request.form.get('branch')
    if not new_branch or new_branch not in ['Pagsanjan', 'Lucban']:
        msg = "Invalid branch selected."
        if is_ajax: return jsonify({'success': False, 'message': msg})
        flash(msg, 'danger')
        return redirect(url_for('admin.staff_management'))
        
    old_branch = user.branch
    user.branch = new_branch
    db.session.commit()
    
    log_audit('UPDATE', 'User', user.id, f"Changed branch of {user.username} from {old_branch} to {new_branch}")
    
    msg = f"Branch updated for {user.username} to {new_branch}."
    if is_ajax: return jsonify({'success': True, 'message': msg, 'new_branch': new_branch})
    flash(msg, "success")
    return redirect(url_for('admin.staff_management'))

# ─── MANAGEMENT: USER MANAGEMENT ────────────────────
@admin_bp.route('/users')
@login_required
@admin_required
def users():
    if current_user.role.upper() != 'SUPER_ADMIN':
        flash("Access denied. Admin Boss only.", "danger")
        return redirect(url_for('admin.overview'))

    role_filter = request.args.get('role', 'ALL')
    page = request.args.get('page', 1, type=int)
    
    query = User.query
    user_branch = getattr(current_user, 'branch', None)
    if user_branch and user_branch != 'ALL':
        query = query.filter(User.branch == user_branch)
        
    if role_filter != 'ALL':
        query = query.filter(func.upper(User.role) == role_filter.upper())
    
    pagination = query.order_by(User.id.desc()).paginate(page=page, per_page=100, error_out=False)
    return render_template('admin/users.html', users=pagination, role_filter=role_filter, get_ph_time=get_ph_time)

@admin_bp.route('/users/update-role/<int:user_id>', methods=['POST'])
@login_required
@requires_permission('users.manage_branch')
def update_user_role(user_id):
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    old_role = user.role
    user.role = new_role
    db.session.commit()
    
    log_audit('UPDATE', 'User', user.id, f"Changed role of {user.username} from {old_role} to {new_role}")
    flash(f"Role updated for {user.username}.", "success")
    return redirect(url_for('admin.users'))

@admin_bp.route('/users/broadcast', methods=['POST'])
@login_required
@requires_permission('users.manage_branch')
def broadcast():
    user_ids = request.form.getlist('user_ids')
    message_content = request.form.get('message_content')
    
    if not user_ids or not message_content:
        flash("Message and target users are required.", "danger")
        return redirect(url_for('admin.users'))
        
    users_to_email = User.query.filter(User.id.in_(user_ids)).all()
    emails = [u.email for u in users_to_email if u.email]
    
    if emails:
        try:
            msg = Message(
                subject='Le Maison Yelo Lane - Broadcast Message',
                sender=current_app.config['MAIL_USERNAME'],
                bcc=emails
            )
            msg.html = f"""
            <div style="background-color: #f8f5f2; padding: 40px 20px; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; line-height: 1.6;">
                <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 30px rgba(93, 64, 55, 0.08); border: 1px solid #e8e0d8;">
                    <div style="background-color: #5d4037; padding: 30px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 300; letter-spacing: 1px;">LE MAISON YELO LANE</h1>
                    </div>
                    <div style="padding: 45px 40px; color: #4e342e;">
                        <p style="font-size: 16px; margin-bottom: 25px;">Hello,</p>
                        <div style="font-size: 15px; color: #4e342e; line-height: 1.8; background-color: #fcfaf8; padding: 25px; border-radius: 12px; border-left: 4px solid #8d6e63;">
                            {message_content.replace(chr(10), '<br>')}
                        </div>
                        <hr style="border: 0; border-top: 1px solid #efebe9; margin: 35px 0;">
                        <div style="text-align: center; color: #a1887f; font-size: 12px;">
                            <p style="margin-bottom: 5px;"><strong>Le Maison Yelo Lane</strong></p>
                            <p style="margin: 0;">Pagsanjan, Laguna · Philippines</p>
                        </div>
                    </div>
                </div>
            </div>
            """
            app_obj = current_app._get_current_object()
            threading.Thread(
                target=_send_flask_mail_worker,
                args=(app_obj, msg),
                daemon=True
            ).start()
            flash(f"Broadcast queued to {len(emails)} user(s).", "success")
        except Exception as e:
            flash(f"Failed to send broadcast: {str(e)}", "danger")
    else:
        flash("No valid emails found to broadcast.", "warning")
        
    return redirect(url_for('admin.users'))

@admin_bp.route('/api/users/<int:user_id>')
@login_required
@admin_required
def api_user_details(user_id):
    if current_user.role.upper() != 'SUPER_ADMIN':
        return jsonify({'error': 'Unauthorized'}), 403

    user = User.query.get_or_404(user_id)
    return jsonify({
        'id': user.id,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'username': user.username,
        'email': user.email,
        'phone': user.phone_number or 'Not provided',
        'status': user.status,
        'role': user.role,
        'joined': user.id # we don't have created_at on User so using id to get an approximation or just string
    })

# ─── MANAGEMENT: RESERVATIONS ────────────────────────
@admin_bp.route('/reservations')
@login_required
@requires_permission('reservations.manage_branch')
def reservations():
    """Admin reservations management page."""
    from datetime import datetime
    
    # Get filter parameters
    status_filter = request.args.get('status')
    type_filter = request.args.get('type')
    date_filter = request.args.get('date')
    page = request.args.get('page', 1, type=int)
    
    # Base query
    query = Reservation.query
    
    # Apply filters
    if status_filter:
        query = query.filter_by(status=status_filter.upper())
    if type_filter:
        query = query.filter_by(booking_type=type_filter.upper())
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            query = query.filter_by(date=filter_date)
        except ValueError:
            pass
    
    # Order by date and time, then paginate
    reservations_paginated = query.order_by(
        Reservation.date.desc(), 
        Reservation.time.desc()
    ).paginate(page=page, per_page=20, error_out=False)
    
    return render_template(
        'admin/reservations.html',
        reservations=reservations_paginated,
        current_filter=status_filter,
        type_filter=type_filter,
        date_filter=date_filter
    )

@admin_bp.route('/reservations/update/<int:res_id>', methods=['POST'])
@login_required
@admin_required
def update_reservation(res_id):
    res = Reservation.query.get_or_404(res_id)
    new_status = request.form.get('status')
    table_number = request.form.get('table_number')

    if new_status == 'CONFIRMED' and table_number:
        conflict = Reservation.query.filter(
            Reservation.id != res.id,
            Reservation.date == res.date,
            Reservation.time == res.time,
            Reservation.table_number == table_number,
            Reservation.status == 'CONFIRMED'
        ).first()

        if conflict:
            flash(f"{table_number} is already booked for this date and time.", "danger")
            return redirect(url_for('admin.reservations'))
    
    res.status = new_status
    if table_number:
        res.table_number = table_number

    db.session.commit()
    
    # Notify user about reservation status change
    status_msgs = {
        'CONFIRMED': f'Your reservation for {res.date.strftime("%b %d, %Y")} at {res.time.strftime("%I:%M %p")} has been confirmed! Assigned Table: {res.table_number or "To be assigned"}',
        'REJECTED': f'Your reservation for {res.date.strftime("%b %d, %Y")} has been declined. Please try a different date/time.',
        'COMPLETED': f'Your reservation for {res.date.strftime("%b %d, %Y")} has been marked as completed. Thank you for dining with us!',
    }
    if new_status in status_msgs:
        _create_web_notification(res.user_id, f'Reservation {new_status.capitalize()}', status_msgs[new_status], 'RESERVATION', link='/my-reservations')
    
    flash(f"Reservation #{res.id} updated to {new_status}.", "success")
    return redirect(url_for('admin.reservations'))

# REDUNDANT: Admin inventory is now handled via inventory_portal.inventory_dashboard
# @admin_bp.route('/inventory')
# @login_required
# @admin_required
# def inventory():
#     ...
#     cats_by_sup = defaultdict(list)
#     for s_id, cat in sup_mappings:
#         cats_by_sup[s_id].append(cat)
# 
#     for sup in all_suppliers:
#         sup.supplied_menu_categories = cats_by_sup.get(sup.id, [])
# 
#     return render_template('admin/inventory.html', 
#         grouped_items=grouped_items, 
#         total_items=total_items, 
#         out_of_stock=out_of_stock, 
#         ingredients=ingredients_paginated,
#         grouped_ingredients=grouped_ingredients,
#         suppliers=all_suppliers, 
#         menu_categories=menu_categories,
#         low_stock_count=low_stock_count,
#         expiring_soon_count=expiring_soon_count,
#         total_ingredients=total_ingredients,
#         all_ingredients_raw=all_ingredients_raw,
#         today=today)

#         pdf.ln(5)
#         
#     output = io.BytesIO()
#     pdf_out = pdf.output(dest='S')
#     output.write(pdf_out)
#     output.seek(0)
#     
#     from flask import send_file
#     return send_file(
#         output,
#         mimetype='application/pdf',
#         as_attachment=True,
#         download_name=f'Purchase_Order_{datetime.now().strftime("%Y%m%d")}.pdf'
#     )

@admin_bp.route('/inventory/toggle/<int:item_id>', methods=['POST'])
@login_required
@admin_required
def toggle_stock(item_id):
    # Restricted to staff roles (Allow Admin full control now)
    # Removing: if current_user.role.upper() in ['CASHIER', 'STAFF']: access denied

    item = MenuItem.query.get_or_404(item_id)
    item.is_available = not item.is_available
    db.session.commit()
    flash(f"Stock status toggled for {item.name}.", "success")
    return redirect(url_for('inventory_portal.inventory_dashboard'))

# ─── KITCHEN VIEW ─────────────────────────────────────
@admin_bp.route('/kitchen')
def kitchen_view():
    return redirect(url_for('kitchen_portal.kitchen_dashboard'))

@admin_bp.route('/kitchen/pantry')
def kitchen_pantry():
    return redirect(url_for('kitchen_portal.kitchen_dashboard'))

@admin_bp.route('/kitchen/pantry/update/<int:ing_id>', methods=['POST'])
def kitchen_pantry_update(ing_id):
    return redirect(url_for('kitchen_portal.kitchen_dashboard'))

@admin_bp.route('/kitchen/api/orders')
@login_required
@admin_required
def kitchen_api_orders():
    return jsonify({'error': 'Endpoint moved to staff portal'}), 301


@admin_bp.route('/kitchen/update/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def kitchen_update_order(order_id):
    # Allow Admin full control for Kitchen now

    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    if new_status in ['PENDING', 'PREPARING', 'COMPLETED', 'CANCELLED']:
        # ── PRE-CHECK: Block "Start" if kitchen stock is insufficient ──
        if new_status == 'PREPARING' and order.status != 'PREPARING':
            missing_items = _check_kitchen_stock_for_order(order)
            if missing_items:
                missing_text = ', '.join([f"{m['ingredient']} (need {m['needed']}, have {m['available']} {m['unit']})" for m in missing_items])
                flash(f'Cannot start Order #{order.id}: Insufficient kitchen stock — {missing_text}. Please restock first!', 'danger')
                return redirect(url_for('admin.kitchen_view'))
            order.prep_start_at = datetime.utcnow()
            _deduct_order_ingredients_fifo(order.id)
        
        if new_status == 'COMPLETED':
            order.prep_end_at = datetime.utcnow()
            # Safety: If it skipped PREPARING status, deduct now
            if order.status not in ['PREPARING', 'COMPLETED']:
                missing_items = _check_kitchen_stock_for_order(order)
                if missing_items:
                    missing_text = ', '.join([f"{m['ingredient']} (need {m['needed']}, have {m['available']} {m['unit']})" for m in missing_items])
                    flash(f'Cannot complete Order #{order.id}: Insufficient kitchen stock — {missing_text}.', 'danger')
                    return redirect(url_for('admin.kitchen_view'))
                _deduct_order_ingredients_fifo(order.id)
            
        order.status = new_status
        db.session.commit()
        
        # Real-time update
        from extensions import socketio
        socketio.emit('order_status_update', {'id': order.id, 'status': new_status}, namespace='/')
        
        log_audit('UPDATE', 'Order', order.id, f'Order #{order.id} status changed to {new_status}')
    return redirect(url_for('admin.kitchen_view'))


def _check_kitchen_stock_for_order(order):
    """
    Pre-flight check: returns a list of missing ingredients for the order.
    If the list is empty, the kitchen has enough stock to prepare.
    """
    missing = []
    for oi in order.items:
        recipe = MenuItemIngredient.query.filter_by(menu_item_id=oi.menu_item_id).all()
        for r in recipe:
            total_needed = float(r.quantity_needed) * oi.quantity
            ingredient = Ingredient.query.get(r.ingredient_id)
            if not ingredient:
                continue
            available = float(ingredient.kitchen_qty or 0)
            if available < total_needed:
                missing.append({
                    'ingredient': ingredient.name,
                    'needed': round(total_needed, 2),
                    'available': round(available, 2),
                    'unit': ingredient.unit
                })
    return missing

# ─── WALK-IN ORDERS ──────────────────────────────────
@admin_bp.route('/walkin-order', methods=['GET'])
@login_required
@admin_required
def walkin_order():
    items = _get_walkin_items_cached()
    categories = sorted(set(i.category for i in items))
    return render_template('admin/walkin_order.html', items=items, categories=categories)

@admin_bp.route('/walkin-order/submit', methods=['POST'])
@login_required
@admin_required
def walkin_order_submit():
    try:
        # Allow Admin full control for POS now
        customer_name = (request.form.get('customer_name') or 'Walk-in Customer').strip()
        dining_option = request.form.get('dining_option', 'DINE_IN')
        table_number = request.form.get('table_number')
        payment_method = request.form.get('payment_method', 'COUNTER')

        # Validate table selection for dine-in
        if dining_option == 'DINE_IN' and not table_number:
            flash("Please select a table for dine-in orders.", "danger")
            return redirect(url_for('admin.walkin_order'))

        # Allow add-on orders for occupied tables in POS

        # Parse items from form
        item_ids = request.form.getlist('item_id[]')
        quantities = request.form.getlist('quantity[]')

        if not item_ids:
            flash("Please add at least one item to the order.", "danger")
            return redirect(url_for('admin.walkin_order'))

        items_data = [{'menu_item_id': int(id), 'quantity': int(qty)} for id, qty in zip(item_ids, quantities)]
        from routes.orders import validate_order
        is_valid, msg, status_override = validate_order(items_data, dining_option, payment_method, is_pos=True, apply_lock=True)
        
        if not is_valid:
            db.session.rollback()
            flash(msg, "danger")
            return redirect(url_for('admin.walkin_order'))

        order_items = []
        total = 0
        for item_id, qty in zip(item_ids, quantities):
            qty = int(qty)
            if qty <= 0: continue
            menu_item = MenuItem.query.get(int(item_id))
            if menu_item:
                order_items.append(OrderItem(
                    menu_item_id=menu_item.id,
                    quantity=qty,
                    price_at_time=menu_item.price
                ))
                total += float(menu_item.price) * qty

        amount_tendered = None
        change_amount = None
        if payment_method == 'COUNTER':
            req_amount = request.form.get('amount_tendered')
            if req_amount:
                try:
                    amount_tendered = float(req_amount)
                    change_amount = amount_tendered - float(total)
                except ValueError: pass

        # Generate unique order code
        from utils import generate_order_code
        order_code = generate_order_code()
        
        order = Order(
            order_code=order_code,
            user_id=None,
            customer_name=customer_name,
            total_amount=total,
            status=status_override or 'PENDING',
            payment_status='PAID' if payment_method == 'COUNTER' else 'UNPAID',
            payment_method=payment_method,
            amount_tendered=amount_tendered,
            change_amount=change_amount,
            dining_option=dining_option,
            table_number=int(table_number) if table_number else None,
            table_status='OCCUPIED' if dining_option == 'DINE_IN' and table_number else None,
            notes='',
            items=order_items
        )
        db.session.add(order)
        db.session.commit()
        
        # Real-time update for Kitchen
        from extensions import socketio
        socketio.emit('new_order', {
            'id': order.id,
            'customer': customer_name,
            'dining_option': dining_option,
            'table_number': int(table_number) if table_number else None,
            'total_amount': float(total)
        }, namespace='/')
        
        if payment_method == 'ONLINE':
            import os, base64, requests
            xendit_secret_key = os.environ.get('XENDIT_SECRET_KEY')
            if xendit_secret_key and xendit_secret_key != 'add_your_xendit_secret_key_here':
                api_key_b64 = base64.b64encode(f"{xendit_secret_key}:".encode('utf-8')).decode('utf-8')
                headers = { 'Authorization': f'Basic {api_key_b64}', 'Content-Type': 'application/json' }
                payload = {
                    'external_id': f"order-walkin-{order.id}-{int(get_ph_time().timestamp())}",
                    'amount': float(total),
                    'payer_email': current_user.email,
                    'description': f"Walk-in Order #{order.id} for {customer_name}",
                    'success_redirect_url': url_for('cashier_portal.cashier_dashboard', _external=True),
                    'failure_redirect_url': url_for('cashier_portal.cashier_dashboard', _external=True),
                    'currency': 'PHP'
                }
                try:
                    resp = requests.post('https://api.xendit.co/v2/invoices', json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        order.xendit_invoice_id = data.get('id')
                        order.xendit_invoice_url = data.get('invoice_url')
                        db.session.commit()
                        flash("Walk-in order created. Please pay via Xendit invoice.", "success")
                        return redirect(order.xendit_invoice_url)
                except Exception as x: print(f"XENDIT ERROR: {str(x)}")
        
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        success_msg = f"Walk-in order submitted successfully! Table {table_number} is now occupied." if table_number else "Walk-in order submitted successfully!"
        if is_ajax:
            return jsonify({'success': True, 'message': success_msg, 'order_id': order.id, 'redirect': url_for('cashier_portal.cashier_dashboard')})
        flash(success_msg, "success")
        return redirect(url_for('cashier_portal.cashier_dashboard'))
    except Exception as e:
        db.session.rollback()
        print(f"WALKIN SUBMIT ERROR: {str(e)}")
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if is_ajax:
            return jsonify({'success': False, 'message': f'System Error: {str(e)}'}), 500
        flash(f"System Error: {str(e)}", "danger")
        return redirect(url_for('admin.walkin_order'))

@admin_bp.route('/walkin-order/table-status', methods=['GET'])
@login_required
def get_table_status():
    """Allow any logged-in staff (Admin, Cashier, etc.) to fetch live table statuses."""
    """Get status of all tables matching table management state."""
    try:
        from models import Reservation
        import datetime as py_datetime
        import re
        from routes.portals import TABLE_CONFIGS

        # Get active occupied tables (any non-archived occupied order)
        from models import User as UserModel
        occupied_rows = (
            db.session.query(Order.table_number, Order.id, Order.customer_name, UserModel.first_name, UserModel.last_name)
            .outerjoin(UserModel, Order.user_id == UserModel.id)
            .filter(
                Order.table_status == 'OCCUPIED',
                Order.table_number.isnot(None),
                Order.is_archived.is_(False)
            )
            .all()
        )
        occupied_map = {}
        for t_num, o_id, cust_name, fn, ln in occupied_rows:
            if t_num is not None:
                display_name = f"{fn} {ln}".strip() if fn else (cust_name or f'Order #{o_id}')
                occupied_map[int(t_num)] = display_name

        # Check today's active reservations
        current_dt = get_ph_time()
        today_reservations = Reservation.query.filter(
            Reservation.date == current_dt.date(),
            Reservation.status == 'CONFIRMED'
        ).all()

        reserved_set = set()
        for res in today_reservations:
            if not res.table_number:
                continue
            start_dt = py_datetime.datetime.combine(res.date, res.time)
            end_dt = start_dt + py_datetime.timedelta(hours=res.duration or 2)
            if start_dt <= current_dt <= end_dt:
                if "exclusive" in res.booking_type.lower() or "exclusive" in (res.table_number or '').lower():
                    reserved_set.update(TABLE_CONFIGS.keys())
                else:
                    nums = [int(n) for n in re.findall(r'\d+', res.table_number)]
                    reserved_set.update(nums)

        table_status = {}
        for i in sorted(TABLE_CONFIGS.keys()):
            if i in occupied_map:
                table_status[i] = {'status': 'OCCUPIED', 'customer': occupied_map[i]}
            elif i in reserved_set:
                table_status[i] = {'status': 'RESERVED'}
            else:
                table_status[i] = {'status': 'AVAILABLE'}

        return jsonify({'success': True, 'tables': table_status})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/orders/<int:order_id>/release-table', methods=['POST'])
@login_required
@admin_required
def release_table(order_id):
    """Release table after customer leaves — marks order COMPLETED so it exits the live queue."""
    try:
        order = Order.query.get_or_404(order_id)
        
        if not order.table_number:
            return jsonify({'success': False, 'error': 'This order has no table assigned'}), 400
        
        table_num = order.table_number
        order.table_status = 'AVAILABLE'
        
        # If order is READY and PAID, completing it is the correct business action:
        # customer has eaten, paid, and left — the order lifecycle is done.
        if order.status in ('READY', 'PREPARING', 'PENDING') and order.payment_status == 'PAID':
            order.status = 'COMPLETED'
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Table {table_num} is now available',
            'table_number': table_num
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500



# ─── DELIVERIES ───────────────────────────────────────
@admin_bp.route('/deliveries')
@login_required
@admin_required
def deliveries():
    status_filter = request.args.get('status', 'ALL')
    page = request.args.get('page', 1, type=int)
    
    query = Order.query.filter(Order.is_archived.is_(False)).filter_by(dining_option='DELIVERY')
    user_branch = getattr(current_user, 'branch', None)
    if user_branch and user_branch != 'ALL':
        query = query.filter_by(branch=user_branch)
        
    if status_filter != 'ALL':
        if status_filter == 'WAITING':
            query = query.filter((Order.delivery_status == None) | (Order.delivery_status == 'WAITING'))
        else:
            query = query.filter_by(delivery_status=status_filter)
            
    pagination = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/deliveries.html', orders=pagination, status_filter=status_filter)

# ─── ORDERS ──────────────────────────────────────────
@admin_bp.route('/orders')
@login_required
@requires_permission('orders.view_branch')
def orders():
    status_filter = request.args.get('status', 'ALL')
    page = request.args.get('page', 1, type=int)
    
    query = Order.query.filter(Order.is_archived.is_(False))
    user_branch = getattr(current_user, 'branch', None)
    if user_branch and user_branch != 'ALL':
        query = query.filter_by(branch=user_branch)
        
    if status_filter != 'ALL':
        query = query.filter_by(status=status_filter)
        
    pagination = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
        
    # Optimized Stats Calculation via SQL Group By
    today = get_ph_time().date()
    # 1 query for all today's stats
    today_stats_q = db.session.query(
        Order.status, 
        Order.payment_status,
        Order.payment_method,
        func.count(Order.id),
        func.sum(Order.total_amount)
    ).filter(func.date(Order.created_at) == today, Order.is_archived.is_(False))
    
    if user_branch and user_branch != 'ALL':
        today_stats_q = today_stats_q.filter(Order.branch == user_branch)
        
    today_stats_rows = today_stats_q.group_by(Order.status, Order.payment_status, Order.payment_method).all()
    
    total_sales_today = 0
    pending_count = 0
    completed_count = 0
    cash_sales = 0
    online_sales = 0
    
    for s, ps, pm, cnt, total in today_stats_rows:
        total = float(total or 0)
        cnt = int(cnt or 0)
        
        if s == 'COMPLETED' and ps == 'PAID':
            total_sales_today += total
            if pm == 'COUNTER': cash_sales += total
            if pm == 'ONLINE': online_sales += total
            
        if s == 'PENDING': pending_count += cnt
        if s == 'COMPLETED': completed_count += cnt

    return render_template('admin/orders.html', 
                           orders=pagination, 
                           status_filter=status_filter,
                           total_sales_today=total_sales_today,
                           pending_count=pending_count,
                           completed_count=completed_count,
                           cash_sales=cash_sales,
                           online_sales=online_sales)

@admin_bp.route('/billing')
@login_required
@requires_permission('orders.view_branch')
def billing():
    status_filter = request.args.get('status', 'UNPAID')
    page = request.args.get('page', 1, type=int)
    
    query = Order.query.filter(Order.is_archived.is_(False))
    if status_filter != 'ALL':
        query = query.filter_by(payment_status=status_filter)
        
    pagination = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
        
    # Stats Calculation optimized
    today = get_ph_time().date()
    stats = db.session.query(
        Order.payment_status,
        Order.payment_method,
        func.count(Order.id),
        func.sum(Order.total_amount)
    ).filter(func.date(Order.created_at) == today, Order.is_archived.is_(False)).group_by(Order.payment_status, Order.payment_method).all()
    
    total_sales_today = 0
    unpaid_count = 0
    cash_sales = 0
    online_sales = 0
    
    for ps, pm, cnt, total in stats:
        total_val = float(total or 0)
        if ps == 'PAID': 
            total_sales_today += total_val
            if pm == 'COUNTER': cash_sales += total_val
            if pm == 'ONLINE': online_sales += total_val
        if ps == 'UNPAID': unpaid_count += int(cnt or 0)
    
    return render_template('admin/billing.html', 
                           orders=pagination, 
                           status_filter=status_filter,
                           total_sales_today=total_sales_today,
                           unpaid_count=unpaid_count,
                           cash_sales=cash_sales,
                           online_sales=online_sales)

@admin_bp.route('/orders/<int:order_id>/receipt')
@login_required
@admin_required
def print_receipt(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('admin/receipt.html', order=order)

def _send_receipt_email_worker(app, order_id: int):
    """Background worker to send COMPLETED receipt emails without blocking admin requests."""
    with app.app_context():
        try:
            order = (
                Order.query.options(
                    selectinload(Order.items).selectinload(OrderItem.menu_item),
                    selectinload(Order.user),
                ).get(order_id)
            )
            if not order or not order.user:
                return

            user = order.user

            # Build order items table rows (HTML string construction is CPU-heavy).
            items_html = ""
            for item in order.items:
                item_total = float(item.price_at_time) * item.quantity
                items_html += f"""
                <tr>
                    <td style="padding: 10px 15px; border-bottom: 1px solid #f0e6d9; color: #333; font-size: 0.9rem;">{item.menu_item.name}</td>
                    <td style="padding: 10px 15px; border-bottom: 1px solid #f0e6d9; color: #555; text-align: center; font-size: 0.9rem;">{item.quantity}</td>
                    <td style="padding: 10px 15px; border-bottom: 1px solid #f0e6d9; color: #555; text-align: right; font-size: 0.9rem;">₱{float(item.price_at_time):,.2f}</td>
                    <td style="padding: 10px 15px; border-bottom: 1px solid #f0e6d9; color: #333; text-align: right; font-weight: 600; font-size: 0.9rem;">₱{item_total:,.2f}</td>
                </tr>
                """

            msg = Message(
                subject=f'Le Maison Yelo Lane - Order #{order.id} Receipt',
                sender=app.config['MAIL_USERNAME'],
                recipients=[user.email],
            )
            msg.html = f"""
            <div style="font-family: 'Georgia', serif; max-width: 550px; margin: 0 auto; padding: 40px 30px; background: #ffffff; border-radius: 12px; border: 1px solid #e0d5c7;">
                <div style="text-align: center; margin-bottom: 25px;">
                    <h1 style="color: #8B4513; margin: 0; font-size: 1.5rem;">☕ Le Maison Yelo Lane</h1>
                    <p style="color: #999; font-size: 0.85rem; margin-top: 5px;">Order Receipt</p>
                </div>
                
                <div style="background: linear-gradient(135deg, #8B4513, #A0522D); color: #fff; border-radius: 10px; padding: 20px; margin-bottom: 25px; text-align: center;">
                    <p style="margin: 0; font-size: 0.85rem; opacity: 0.8;">Order Number</p>
                    <h2 style="margin: 5px 0; font-size: 1.8rem; letter-spacing: 2px;">#{order.id}</h2>
                    <p style="margin: 0; font-size: 0.8rem; opacity: 0.7;">{order.created_at.strftime('%B %d, %Y at %I:%M %p')}</p>
                </div>
                
                <p style="color: #333; font-size: 1rem;">Hello <strong>{user.first_name}</strong>,</p>
                <p style="color: #555; font-size: 0.95rem;">Your order has been completed! Here is your receipt:</p>
                
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                    <thead>
                        <tr style="background: rgba(139,69,19,0.06);">
                            <th style="padding: 10px 15px; text-align: left; color: #8B4513; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px;">Item</th>
                            <th style="padding: 10px 15px; text-align: center; color: #8B4513; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px;">Qty</th>
                            <th style="padding: 10px 15px; text-align: right; color: #8B4513; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px;">Price</th>
                            <th style="padding: 10px 15px; text-align: right; color: #8B4513; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px;">Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items_html}
                    </tbody>
                </table>
                
                <div style="background: rgba(139,69,19,0.04); border-radius: 8px; padding: 15px 20px; margin: 20px 0;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 1.1rem; font-weight: bold; color: #333;">Total Amount</span>
                        <span style="font-size: 1.3rem; font-weight: bold; color: #8B4513;">₱{float(order.total_amount):,.2f}</span>
                    </div>
                </div>
                
                <div style="text-align: center; margin: 25px 0; padding: 15px; background: rgba(40,167,69,0.08); border-radius: 8px;">
                    <span style="color: #28a745; font-weight: bold; font-size: 0.9rem;">✓ COMPLETED</span>
                </div>
                
                <hr style="border: none; border-top: 1px solid #e0d5c7; margin: 25px 0;">
                <p style="color: #999; font-size: 0.8rem; text-align: center;">Thank you for dining with us! We hope you enjoyed your meal.</p>
                <p style="color: #bbb; font-size: 0.75rem; text-align: center;">Le Maison Yelo Lane · Pagsanjan, Laguna</p>
            </div>
            """

            mail = app.extensions['mail']
            mail.send(msg)
        except Exception as e:
            print(f"Receipt email async failed: {e}")
            traceback.print_exc()

@admin_bp.route('/orders/update/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def update_order(order_id):
    # Eager load to avoid extra queries during stock deduction + notification/email.
    order = Order.query.options(selectinload(Order.items), selectinload(Order.user)).get_or_404(order_id)
    new_status = request.form.get('status')
    
    # Auto-deduct ingredients when order moves to PREPARING
    if new_status == 'PREPARING' and order.status != 'PREPARING':
        _deduct_order_ingredients_fifo(order.id)
    
    order.status = new_status
    db.session.commit()
    
    # Notify user about order status change
    if order.user_id:
        order_status_msgs = {
            'PREPARING': f'Your order #{order.id} is now being prepared! 🍳',
            'COMPLETED': f'Your order #{order.id} is ready! Total: ₱{float(order.total_amount):,.2f}',
            'CANCELLED': f'Your order #{order.id} has been cancelled.',
        }
        if new_status in order_status_msgs:
            _create_web_notification(order.user_id, f'Order {new_status.capitalize()}', order_status_msgs[new_status], 'ORDER', link='/my-orders')
    
    # Send receipt email when order is COMPLETED.
    # This can be slow (SMTP + template rendering), so move it off the request thread.
    if new_status == 'COMPLETED' and order.user:
        try:
            app_obj = current_app._get_current_object()
            threading.Thread(
                target=lambda: _send_receipt_email_worker(app_obj, order_id),
                daemon=True
            ).start()
        except Exception as e:
            print(f"Failed to start receipt email thread: {e}")
            traceback.print_exc()
    
    flash(f"Order #{order.id} status updated to {new_status}.", "success")
    return redirect(url_for('admin.orders'))

@admin_bp.route('/orders/update_payment/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def update_payment_status(order_id):
    # ── BACKEND VALIDATION ──────────────────────────────────────
    # NEVER trust the amount_due from the frontend.
    # Always fetch the actual total from the database.
    order = Order.query.get_or_404(order_id)
    new_payment_status = request.form.get('payment_status')

    if new_payment_status not in ['PAID', 'UNPAID']:
        msg = "Invalid payment status."
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': msg}), 400
        flash(msg, "danger")
        return redirect(request.headers.get("Referer") or url_for('admin.orders'))

    if new_payment_status == 'PAID':
        amount_tendered_raw = request.form.get('amount_tendered', '').strip()

        # 1. Validate: must be a valid number
        try:
            amount_tendered = float(amount_tendered_raw)
        except (ValueError, TypeError):
            msg = "Invalid amount tendered. Please enter a valid number."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': msg}), 400
            flash(msg, "danger")
            return redirect(request.headers.get("Referer") or url_for('admin.orders'))

        # 2. Validate: must not be negative or zero
        if amount_tendered <= 0:
            msg = "Amount tendered must be greater than zero."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': msg}), 400
            flash(msg, "danger")
            return redirect(request.headers.get("Referer") or url_for('admin.orders'))

        # 3. Fetch ACTUAL amount due from DB (not from form)
        actual_due = float(order.total_amount)

        # 4. Validate: tendered must cover the actual due
        if amount_tendered < actual_due:
            msg = f"Amount tendered (₱{amount_tendered:,.2f}) is less than the bill amount (₱{actual_due:,.2f})."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': msg}), 400
            flash(msg, "danger")
            return redirect(request.headers.get("Referer") or url_for('admin.orders'))

        # 5. Validate: fat-finger guard — tendered must not exceed 10× the due
        if amount_tendered > actual_due * 10:
            msg = f"Amount tendered (₱{amount_tendered:,.2f}) seems too high for a ₱{actual_due:,.2f} bill. Please verify."
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': msg}), 400
            flash(msg, "danger")
            return redirect(request.headers.get("Referer") or url_for('admin.orders'))

        # 6. Re-calculate change server-side (never trust frontend change value)
        change_amount = round(amount_tendered - actual_due, 2)

        # 7. Atomic update — only mark PAID if all checks pass
        order.payment_status = 'PAID'
        order.amount_tendered = amount_tendered
        order.change_amount = change_amount
        
        # Auto-complete order if it's READY and not occupying an active table,
        # or if it's DINE_IN and the table is already released.
        if order.status == 'READY':
            if order.dining_option != 'DINE_IN' or order.table_status == 'AVAILABLE' or not order.table_number:
                order.status = 'COMPLETED'
        elif order.status in ('PENDING', 'PREPARING'):
            if order.dining_option == 'DINE_IN' and (order.table_status == 'AVAILABLE' or not order.table_number):
                order.status = 'COMPLETED'
                
        db.session.commit()

        flash(f"Order #{order.id} marked as PAID. Change: ₱{change_amount:,.2f}", "success")

    elif new_payment_status == 'UNPAID':
        order.payment_status = 'UNPAID'
        order.amount_tendered = None
        order.change_amount = None
        db.session.commit()
        flash(f"Order #{order.id} payment status marked as UNPAID.", "success")

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': f"Order #{order.id} marked as PAID. Change: ₱{change_amount:,.2f}"})

    referrer = request.headers.get("Referer")
    if referrer:
        return redirect(referrer)
    return redirect(url_for('admin.orders'))

@admin_bp.route('/orders/<int:order_id>/update-table', methods=['POST'])
@login_required
@admin_required
def update_order_table_number(order_id):
    """
    Update table number for a pending dine-in order.
    
    Request Body (JSON):
        {
            "table_number": <positive integer 1-17>
        }
    
    Returns:
        JSON response with success status and message
    """
    try:
        # Parse request data
        data = request.get_json()
        if not data or 'table_number' not in data:
            return jsonify({
                'success': False,
                'message': 'Missing table_number in request'
            }), 400
        
        new_table_number = data['table_number']
        
        # Validate table number is a positive integer
        try:
            new_table_number = int(new_table_number)
            if new_table_number < 1 or new_table_number > 17:
                return jsonify({
                    'success': False,
                    'message': 'Table number must be between 1 and 17'
                }), 400
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'message': 'Table number must be a valid integer'
            }), 400
        
        # Fetch the order
        order = Order.query.get(order_id)
        if not order:
            return jsonify({
                'success': False,
                'message': 'Order not found'
            }), 404
        
        # Validate order is dine-in
        if order.dining_option != 'DINE_IN':
            return jsonify({
                'success': False,
                'message': 'Table number can only be updated for dine-in orders'
            }), 400
        
        # Validate order status is PENDING
        if order.status != 'PENDING':
            return jsonify({
                'success': False,
                'message': 'Table number can only be updated for pending orders'
            }), 400
        
        # Check if the new table is already occupied (by a different order)
        if new_table_number != order.table_number:
            occupied_order = Order.query.filter(
                Order.id != order_id,
                Order.table_number == new_table_number,
                Order.table_status == 'OCCUPIED',
                Order.is_archived.is_(False)
            ).first()
            
            if occupied_order:
                return jsonify({
                    'success': False,
                    'message': f'Table {new_table_number} is already occupied by Order #{occupied_order.id}'
                }), 400
        
        # Update the table number
        old_table_number = order.table_number
        order.table_number = new_table_number
        order.table_status = 'OCCUPIED'  # Mark as occupied
        db.session.commit()
        
        # Return success response
        return jsonify({
            'success': True,
            'message': f'Table number updated from {old_table_number or "unset"} to {new_table_number}',
            'old_value': old_table_number,
            'new_value': new_table_number
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating table number for order {order_id}: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Internal server error'
        }), 500

@admin_bp.route('/orders/<int:order_id>/available-tables', methods=['GET'])
@login_required
@admin_required
def get_available_tables(order_id):
    """
    Get list of available tables (1-17) excluding occupied ones.
    
    Returns:
        JSON response with list of available table numbers
    """
    try:
        # Get all occupied tables (excluding the current order's table)
        occupied_tables = db.session.query(Order.table_number).filter(
            Order.id != order_id,
            Order.table_status == 'OCCUPIED',
            Order.table_number.isnot(None),
            Order.is_archived.is_(False)
        ).all()
        
        occupied_set = {t[0] for t in occupied_tables if t[0]}
        
        # All tables 1-17
        all_tables = list(range(1, 18))
        
        # Available tables
        available_tables = [t for t in all_tables if t not in occupied_set]
        
        return jsonify({
            'success': True,
            'available_tables': available_tables,
            'occupied_tables': list(occupied_set)
        }), 200
        
    except Exception as e:
        print(f"Error fetching available tables: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Internal server error'
        }), 500

@admin_bp.route('/orders/split/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def split_order(order_id):
    original_order = Order.query.get_or_404(order_id)
    split_item_ids = request.form.getlist('split_item_ids')
    
    if not split_item_ids:
        flash("No items selected to split.", "warning")
        return redirect(url_for('admin.orders'))

    # Check if we are trying to split ALL items (which doesn't make sense as a split)
    all_item_ids = [str(item.id) for item in original_order.items]
    if set(split_item_ids) == set(all_item_ids):
        flash("You cannot split all items. Use the whole order instead.", "warning")
        return redirect(url_for('admin.orders'))

    try:
        # Create new order as a shell copy
        # Generate unique order code
        from utils import generate_order_code
        order_code = generate_order_code()
        
        new_order = Order(
            order_code=order_code,
            user_id=original_order.user_id,
            customer_name=original_order.customer_name,
            total_amount=0,
            status=original_order.status,
            payment_status='UNPAID', # New split is usually unpaid initially
            dining_option=original_order.dining_option,
            payment_method=original_order.payment_method,
            notes=f"Split from Order #{original_order.id}",
            delivery_address=original_order.delivery_address,
            delivery_fee=0, # Typically 0 for splits unless delivery is split too
            processed_by_id=current_user.id
        )
        db.session.add(new_order)
        db.session.flush() # Get the new_order.id

        # Move selected items
        new_total = 0
        for item_id in split_item_ids:
            item = OrderItem.query.get(int(item_id))
            if item and item.order_id == original_order.id:
                item.order_id = new_order.id
                new_total += float(item.price_at_time) * item.quantity
        
        new_order.total_amount = new_total
        
        # Recalculate original order total
        original_total = 0
        for item in original_order.items:
            # Note: order.items relationship might still contain moved items until commit/refresh
            # But SQLAlchemy usually handles this if we use the session correctly.
            # To be safe, we recalculate manually from what remains.
            pass
        
        # Re-query remaining items to be absolutely sure
        remaining_items = OrderItem.query.filter_by(order_id=original_order.id).all()
        original_order.total_amount = sum(float(i.price_at_time) * i.quantity for i in remaining_items)

        db.session.commit()
        flash(f"Split successful! New Order #{new_order.id} created.", "success")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error splitting order: {str(e)}", "danger")
        print("Split Error:", e)
        traceback.print_exc()

    return redirect(url_for('admin.orders'))

# ─── REVIEWS ─────────────────────────────────────────
@admin_bp.route('/reviews')
@login_required
@admin_required
def reviews():
    if current_user.role.upper() != 'SUPER_ADMIN':
        flash("Unauthorized access. Super Admin role required.", "danger")
        return redirect(url_for('admin.overview'))
    limit = request.args.get('limit', 250, type=int)
    limit = max(1, min(limit, 500))
    
    rev_q = Review.query.options(selectinload(Review.user))
    user_branch = getattr(current_user, 'branch', None)
    if user_branch and user_branch != 'ALL':
        rev_q = rev_q.join(Order, Review.order_id == Order.id).filter(Order.branch == user_branch)
    all_reviews_for_stats = rev_q.order_by(Review.created_at.desc()).all()
    all_reviews = all_reviews_for_stats[:limit]
        
    # AI Sentiment Analysis (Dynamic Calculation to avoid DB Migrations)
    positive_words = ['good', 'great', 'excellent', 'amazing', 'best', 'delicious', 'love', 'perfect', 'nice', 'awesome', 'sarap', 'mabilis', 'ayos', 'sulit', 'outstanding', 'fantastic', 'superb', 'yummy', 'tasty']
    negative_words = ['bad', 'terrible', 'awful', 'worst', 'horrible', 'poor', 'slow', 'cold', 'disappointing', 'hate', 'pangit', 'panget', 'mabagal', 'matagal', 'bland', 'salty', 'late', 'matabang', 'maalat']

    # Prevent unbounded growth in long-running deployments.
    if len(_REVIEW_SENTIMENT_CACHE) > 2500:
        _REVIEW_SENTIMENT_CACHE.clear()

    now_mono = time.monotonic()

    def _compute_sentiment(text: str, rating: int):
        t = (text or '').lower()
        if not t:
            return ("NEUTRAL", "😐", "secondary")
        pos_count = sum(t.count(word) for word in positive_words)
        neg_count = sum(t.count(word) for word in negative_words)

        if rating >= 4: pos_count += 2
        elif rating <= 2: neg_count += 2

        if pos_count > neg_count: return ("POSITIVE", "😊", "success")
        if neg_count > pos_count: return ("NEGATIVE", "😠", "danger")
        if rating >= 4: return ("POSITIVE", "😊", "success")
        if rating <= 2: return ("NEGATIVE", "😠", "danger")
        return ("NEUTRAL", "😐", "secondary")

    # Pre-calculate sentiment synchronously for all loaded reviews for stats grouping
    for review in all_reviews_for_stats:
        comment_text = str(review.comment or '')
        if not comment_text.strip():
            review.ai_sentiment = "NEUTRAL"
            review.ai_sentiment_icon = "😐"
            review.ai_sentiment_color = "secondary"
            continue

        comment_key = hash(comment_text)
        cache_key = (review.id, review.rating, comment_key)
        cached = _REVIEW_SENTIMENT_CACHE.get(cache_key)
        if cached and (now_mono - cached[0]) < _REVIEW_SENTIMENT_CACHE_TTL_SECONDS:
            sentiment, icon, color = cached[1]
            review.ai_sentiment = sentiment
            review.ai_sentiment_icon = icon
            review.ai_sentiment_color = color
        else:
            sentiment, icon, color = _compute_sentiment(comment_text, review.rating)
            review.ai_sentiment = sentiment
            review.ai_sentiment_icon = icon
            review.ai_sentiment_color = color
            _REVIEW_SENTIMENT_CACHE[cache_key] = (now_mono, (sentiment, icon, color))

    # Timeframe calculation
    now_ph = get_ph_time()
    today_date = now_ph.date()
    
    from datetime import datetime, time as py_time, timedelta
    today_start = datetime.combine(today_date, py_time.min)
    weekly_start = today_start - timedelta(days=7)
    monthly_start = today_start - timedelta(days=30)
    
    def calc_stats(revs):
        total = len(revs)
        avg = sum(r.rating for r in revs) / total if total else 0.0
        featured = sum(1 for r in revs if r.is_featured_in_gallery and r.photo_url)
        pos_count = sum(1 for r in revs if getattr(r, 'ai_sentiment', 'NEUTRAL') == 'POSITIVE')
        pos_pct = round(pos_count / total * 100) if total else 100
        rating_dist = {i: sum(1 for r in revs if r.rating == i) for i in range(1, 6)}
        return {
            'total_reviews': total,
            'avg_rating': round(avg, 1),
            'featured_count': featured,
            'pos_pct': pos_pct,
            'rating_dist': rating_dist
        }
        
    daily_revs = []
    weekly_revs = []
    monthly_revs = []
    
    for r in all_reviews_for_stats:
        r_dt = r.created_at
        if r_dt and hasattr(r_dt, 'tzinfo') and r_dt.tzinfo is not None:
            r_dt = r_dt.replace(tzinfo=None)
        if r_dt >= today_start:
            daily_revs.append(r)
        if r_dt >= weekly_start:
            weekly_revs.append(r)
        if r_dt >= monthly_start:
            monthly_revs.append(r)
            
    timeframe_stats = {
        'daily': calc_stats(daily_revs),
        'weekly': calc_stats(weekly_revs),
        'monthly': calc_stats(monthly_revs),
        'all': calc_stats(all_reviews_for_stats)
    }

    # Group reviews by month for the last 6 months (grouped bar chart data)
    month_keys = []
    current = now_ph
    for _ in range(6):
        month_keys.append((current.year, current.month))
        # Move back one month
        first_of_this_month = current.replace(day=1)
        prev_month_end = first_of_this_month - timedelta(days=1)
        current = prev_month_end
        
    month_keys.reverse() # Chronological order
    
    chart_months = []
    chart_positive = []
    chart_negative = []
    
    for y, m in month_keys:
        month_name = datetime(y, m, 1).strftime('%B')
        chart_months.append(month_name)
        
        pos_count = 0
        neg_count = 0
        for r in all_reviews_for_stats:
            r_dt = r.created_at
            if r_dt and hasattr(r_dt, 'tzinfo') and r_dt.tzinfo is not None:
                r_dt = r_dt.replace(tzinfo=None)
            if r_dt.year == y and r_dt.month == m:
                if r.rating >= 4:
                    pos_count += 1
                elif r.rating <= 2:
                    neg_count += 1
        chart_positive.append(pos_count)
        chart_negative.append(neg_count)

    return render_template(
        'admin/reviews.html', 
        reviews=all_reviews,
        timeframe_stats=timeframe_stats,
        total_reviews=timeframe_stats['all']['total_reviews'],
        avg_rating=timeframe_stats['all']['avg_rating'],
        featured_count=timeframe_stats['all']['featured_count'],
        pos_pct=timeframe_stats['all']['pos_pct'],
        rating_dist=timeframe_stats['all']['rating_dist'],
        chart_months=chart_months,
        chart_positive=chart_positive,
        chart_negative=chart_negative
    )

@admin_bp.route('/reviews/update/<int:review_id>', methods=['POST'])
@login_required
@admin_required
def update_review(review_id):
    if current_user.role.upper() != 'SUPER_ADMIN':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Super Admin role required.'}), 403
        flash("Unauthorized access. Super Admin role required.", "danger")
        return redirect(url_for('admin.overview'))
    review = Review.query.get_or_404(review_id)
    new_status = request.form.get('status')
    
    if new_status not in ['PENDING', 'APPROVED', 'REJECTED']:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Invalid status value'}), 400
        flash("Invalid status value", "danger")
        return redirect(url_for('admin.reviews'))
        
    review.status = new_status
    db.session.commit()
    
    log_audit('UPDATE', 'Review', review.id, f"Admin updated review status to {new_status}")
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'message': f"Review status updated to {new_status}.",
            'status': new_status
        })
        
    flash(f"Review from {review.user.first_name} marked as {new_status}.", "success")
    return redirect(url_for('admin.reviews'))

@admin_bp.route('/reviews/edit-photo/<int:review_id>', methods=['POST'])
@login_required
@admin_required
def edit_review_photo(review_id):
    if current_user.role.upper() != 'SUPER_ADMIN':
        return jsonify({'success': False, 'message': 'Super Admin role required.'}), 403
    """Replace/upload a new photo for a review (e.g. for homepage gallery)"""
    review = Review.query.get_or_404(review_id)
    
    if 'photo' not in request.files:
        return jsonify({'success': False, 'message': 'No file part in request'}), 400
        
    file = request.files['photo']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'}), 400
        
    if file:
        import os
        from werkzeug.utils import secure_filename
        from flask import current_app
        from utils import get_ph_time
        
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in allowed_extensions:
            return jsonify({'success': False, 'message': 'Invalid image format. Allowed: PNG, JPG, JPEG, GIF, WEBP.'}), 400
            
        try:
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'reviews')
            os.makedirs(upload_folder, exist_ok=True)
            
            from utils import save_optimized_image
            filename = secure_filename(f"review_{review.id}_edited_{int(get_ph_time().timestamp())}.{ext}")
            filepath = os.path.join(upload_folder, filename)
            save_optimized_image(file, filepath, max_dim=(1000, 1000), quality=80)
            
            # Delete old file if it exists and was uploaded locally
            old_photo_url = review.photo_url
            if old_photo_url and old_photo_url.startswith('/static/uploads/'):
                try:
                    old_path = os.path.join(current_app.root_path, old_photo_url.lstrip('/'))
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except Exception as e:
                    print(f"Failed to delete old photo: {e}")
            
            # Update db
            review.photo_url = f"/static/uploads/reviews/{filename}"
            db.session.commit()
            
            log_audit('UPDATE', 'Review', review.id, f"Admin updated photo for review #{review.id}")
            
            return jsonify({
                'success': True,
                'message': 'Photo updated successfully',
                'photo_url': review.photo_url
            })
        except Exception as e:
            print(f"Error saving edited review photo: {str(e)}")
            return jsonify({'success': False, 'message': f'Failed to upload image: {str(e)}'}), 500
            
    return jsonify({'success': False, 'message': 'No file received'}), 400

@admin_bp.route('/reviews/toggle-gallery/<int:review_id>', methods=['POST'])
@login_required
@admin_required
def toggle_review_gallery(review_id):
    if current_user.role.upper() != 'SUPER_ADMIN':
        return jsonify({'success': False, 'message': 'Super Admin role required.'}), 403
    """Toggle whether a review photo is featured in homepage gallery"""
    review = Review.query.get_or_404(review_id)
    
    if not review.photo_url:
        return jsonify({'success': False, 'message': 'This review has no photo'}), 400
    
    # Toggle the gallery feature
    review.is_featured_in_gallery = not review.is_featured_in_gallery
    db.session.commit()
    
    status = 'added to' if review.is_featured_in_gallery else 'removed from'
    return jsonify({
        'success': True, 
        'message': f'Photo {status} gallery',
        'is_featured': review.is_featured_in_gallery
    })


# ─── SYSTEM: BRANCH MANAGEMENT ────────────────────────────────────
@admin_bp.route('/branches', methods=['GET'])
@login_required
def branches():
    if current_user.role.upper() != 'SUPER_ADMIN':
        flash("Access denied. Super Admin only.", "danger")
        return redirect(url_for('admin.overview'))
    from models import Branch, User, Order

    # Auto-seed hardcoded branches if missing
    _default_branches = [
        {
            'name': 'Pagsanjan',
            'address': 'Yelo Lane, General Taino Street',
            'city': 'Pagsanjan',
            'province': 'Laguna',
            'phone': '09988863566',
            'email': 'lemaisonyelolane9@gmail.com',
            'is_main': True,
            'is_active': True,
        },
        {
            'name': 'Lucban',
            'address': 'Fidel Rada St, Lucban',
            'city': 'Lucban',
            'province': 'Quezon',
            'phone': '09988863566',
            'email': '',
            'is_main': False,
            'is_active': True,
        },
        {
            'name': 'Lucena',
            'address': 'Lucena City',
            'city': 'Lucena City',
            'province': 'Quezon',
            'phone': '',
            'email': '',
            'is_main': False,
            'is_active': False,   # Coming Soon — inactive
        },
    ]
    # Always check each branch individually — add if missing
    seeded = False
    for b in _default_branches:
        if not Branch.query.filter_by(name=b['name']).first():
            db.session.add(Branch(**b))
            seeded = True
    if seeded:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    all_branches = Branch.query.order_by(Branch.is_main.desc(), Branch.created_at.asc()).all()

    # Build stats per branch
    branch_stats = {}
    for br in all_branches:
        staff_count = User.query.filter(
            User.branch == br.name,
            User.role.in_(['ADMIN', 'CASHIER', 'STAFF', 'KITCHEN', 'INVENTORY_STAFF', 'INVENTORY', 'RIDER'])
        ).count()
        total_orders = Order.query.filter_by(branch=br.name).count()
        pending_orders = Order.query.filter_by(branch=br.name, status='PENDING').count()
        branch_stats[br.id] = {
            'staff': staff_count,
            'orders': total_orders,
            'pending': pending_orders,
        }

    return render_template('admin/branches.html', branches=all_branches, branch_stats=branch_stats)

@admin_bp.route('/branches/add', methods=['POST'])
@login_required
def branch_add():
    if current_user.role.upper() != 'SUPER_ADMIN':
        return jsonify({'success': False, 'message': 'Access denied.'}), 403
    from models import Branch
    name     = (request.form.get('name') or '').strip()
    address  = (request.form.get('address') or '').strip()
    city     = (request.form.get('city') or '').strip()
    province = (request.form.get('province') or '').strip()
    phone    = (request.form.get('phone') or '').strip()
    email    = (request.form.get('email') or '').strip()
    is_main  = request.form.get('is_main') == '1'

    if not name:
        flash("Branch name is required.", "danger")
        return redirect(url_for('admin.branches'))

    if Branch.query.filter_by(name=name).first():
        flash(f"Branch '{name}' already exists.", "danger")
        return redirect(url_for('admin.branches'))

    # Only one main branch allowed
    if is_main:
        Branch.query.filter_by(is_main=True).update({'is_main': False})

    branch = Branch(
        name=name, address=address, city=city,
        province=province, phone=phone, email=email,
        is_main=is_main, is_active=True
    )
    db.session.add(branch)
    db.session.commit()
    flash(f"Branch '{name}' added successfully.", "success")
    return redirect(url_for('admin.branches', msg='added', branch_name=name))


@admin_bp.route('/branches/<int:branch_id>/edit', methods=['POST'])
@login_required
def branch_edit(branch_id):
    if current_user.role.upper() != 'SUPER_ADMIN':
        return jsonify({'success': False, 'message': 'Access denied.'}), 403
    from models import Branch
    branch = Branch.query.get_or_404(branch_id)
    branch.name     = (request.form.get('name') or branch.name).strip()
    branch.address  = (request.form.get('address') or '').strip()
    branch.city     = (request.form.get('city') or '').strip()
    branch.province = (request.form.get('province') or '').strip()
    branch.phone    = (request.form.get('phone') or '').strip()
    branch.email    = (request.form.get('email') or '').strip()
    branch.is_active = request.form.get('is_active') == '1'
    is_main = request.form.get('is_main') == '1'
    if is_main and not branch.is_main:
        Branch.query.filter_by(is_main=True).update({'is_main': False})
        branch.is_main = True
    elif not is_main:
        branch.is_main = False
    db.session.commit()
    flash(f"Branch '{branch.name}' updated.", "success")
    return redirect(url_for('admin.branches', msg='updated', branch_name=branch.name))


@admin_bp.route('/branches/<int:branch_id>/delete', methods=['POST'])
@login_required
def branch_delete(branch_id):
    if current_user.role.upper() != 'SUPER_ADMIN':
        return jsonify({'success': False, 'message': 'Access denied.'}), 403
    from models import Branch
    branch = Branch.query.get_or_404(branch_id)
    name = branch.name
    db.session.delete(branch)
    db.session.commit()
    flash(f"Branch '{name}' deleted.", "success")
    return redirect(url_for('admin.branches', msg='deleted', branch_name=name))


@admin_bp.route('/branches/<int:branch_id>/toggle', methods=['POST'])
@login_required
def branch_toggle(branch_id):
    if current_user.role.upper() != 'SUPER_ADMIN':
        return jsonify({'success': False}), 403
    from models import Branch
    branch = Branch.query.get_or_404(branch_id)
    branch.is_active = not branch.is_active
    db.session.commit()
    return jsonify({'success': True, 'is_active': branch.is_active})


# ─── SYSTEM: SETTINGS ────────────────────────────────
from utils import load_site_settings, save_site_settings
@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    user_role = current_user.role.upper().replace(' ', '_')
    if user_role != 'SUPER_ADMIN' and user_role != 'ADMIN':
        flash("Access denied. Admin Boss only.", "danger")
        return redirect(url_for('admin.overview'))
    
    site_settings = load_site_settings()
    if request.method == 'POST' and user_role == 'SUPER_ADMIN':
        # Handle form submission for homepage content
        # Update Hero 1
        site_settings['hero1']['title1'] = request.form.get('hero1_title1', site_settings['hero1']['title1'])
        site_settings['hero1']['title2'] = request.form.get('hero1_title2', site_settings['hero1']['title2'])
        site_settings['hero1']['description'] = request.form.get('hero1_desc', site_settings['hero1']['description'])
        site_settings['hero1']['image_url'] = request.form.get('hero1_img', site_settings['hero1']['image_url'])

        # Update Hero 2
        site_settings['hero2']['title1'] = request.form.get('hero2_title1', site_settings['hero2']['title1'])
        site_settings['hero2']['title2'] = request.form.get('hero2_title2', site_settings['hero2']['title2'])
        site_settings['hero2']['description'] = request.form.get('hero2_desc', site_settings['hero2']['description'])
        site_settings['hero2']['image_url'] = request.form.get('hero2_img', site_settings['hero2']['image_url'])

        # Update Hero 3
        site_settings['hero3']['title1'] = request.form.get('hero3_title1', site_settings['hero3']['title1'])
        site_settings['hero3']['title2'] = request.form.get('hero3_title2', site_settings['hero3']['title2'])
        site_settings['hero3']['description'] = request.form.get('hero3_desc', site_settings['hero3']['description'])
        site_settings['hero3']['image_url'] = request.form.get('hero3_img', site_settings['hero3']['image_url'])

        # Update Welcome Section
        site_settings['welcome']['title'] = request.form.get('welcome_title', site_settings['welcome']['title'])
        site_settings['welcome']['subtitle'] = request.form.get('welcome_subtitle', site_settings['welcome']['subtitle'])
        site_settings['welcome']['description1'] = request.form.get('welcome_desc1', site_settings['welcome']['description1'])
        site_settings['welcome']['description2'] = request.form.get('welcome_desc2', site_settings['welcome']['description2'])
        site_settings['welcome']['image_url'] = request.form.get('welcome_img', site_settings['welcome']['image_url'])
        
        # Update Card 1
        site_settings['card1']['title'] = request.form.get('c1_title', site_settings['card1']['title'])
        site_settings['card1']['description'] = request.form.get('c1_desc', site_settings['card1']['description'])
        site_settings['card1']['image_url'] = request.form.get('c1_img', site_settings['card1']['image_url'])

        # Update Card 2
        site_settings['card2']['title'] = request.form.get('c2_title', site_settings['card2']['title'])
        site_settings['card2']['description'] = request.form.get('c2_desc', site_settings['card2']['description'])
        site_settings['card2']['image_url'] = request.form.get('c2_img', site_settings['card2']['image_url'])

        # Update Footer
        site_settings['footer']['facebook_link'] = request.form.get('footer_fb', site_settings['footer']['facebook_link'])
        site_settings['footer']['instagram_link'] = request.form.get('footer_ig', site_settings['footer']['instagram_link'])
        site_settings['footer']['twitter_link'] = request.form.get('footer_tw', site_settings['footer']['twitter_link'])
        site_settings['footer']['youtube_link'] = request.form.get('footer_yt', site_settings['footer']['youtube_link'])
        site_settings['footer']['address_text'] = request.form.get('footer_address', site_settings['footer']['address_text'])
        site_settings['footer']['copyright_text'] = request.form.get('footer_copyright', site_settings['footer']['copyright_text'])

        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if save_site_settings(site_settings):
            if is_ajax:
                return jsonify({'success': True, 'message': 'Homepage content updated successfully.'})
            flash("Homepage content updated successfully.", "success")
        else:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Failed to save settings.'}), 500
            flash("Failed to save settings.", "danger")
        return redirect(url_for('admin.settings'))

    return render_template('admin/settings.html', site=site_settings)

@admin_bp.route('/settings/profile', methods=['POST'])
@login_required
def update_profile():
    first_name = request.form.get('admin_first_name', '').strip()
    middle_name = request.form.get('admin_middle_name', '').strip()
    last_name = request.form.get('admin_last_name', '').strip()
    username = request.form.get('admin_username', '').strip()
    email = request.form.get('admin_email', '').strip()
    phone_number = request.form.get('admin_phone_number', '').strip()
    
    current_password = request.form.get('admin_current_password', '')
    new_password = request.form.get('admin_new_password', '')
    confirm_new_password = request.form.get('admin_confirm_password', '')

    # Fallback redirect helper
    def redirect_back():
        ref = request.headers.get("Referer")
        return redirect(ref) if ref else redirect(url_for('admin.overview'))

    # --- VALIDATIONS ---
    if not all([first_name, last_name, username, email, phone_number]):
        flash("All profile fields are required.", "danger")
        return redirect_back()
    
    # Validate Names
    for name, label in [(first_name, 'First Name'), (last_name, 'Last Name')]:
        err = validate_name(name, label)
        if err: flash(err, "danger"); return redirect_back()
    if middle_name:
        err = validate_name(middle_name, 'Middle Name')
        if err: flash(err, "danger"); return redirect_back()

    # Validate Email
    err = validate_email(email)
    if err: flash(err, "danger"); return redirect_back()

    # Validate Username
    err = validate_username(username, first_name, last_name)
    if err: flash(err, "danger"); return redirect_back()

    # Conflicts
    if email != current_user.email and User.query.filter_by(email=email).first():
        flash("Email already registered.", "danger")
        return redirect_back()
    if username != current_user.username and User.query.filter_by(username=username).first():
        flash("Username already taken.", "danger")
        return redirect_back()
    
    # Password Change
    if new_password:
        if not current_password:
            flash("Current password is required to change password.", "danger")
            return redirect_back()
        if not current_user.check_password(current_password):
            flash("Incorrect current password.", "danger")
            return redirect_back()
        
        err = validate_password(new_password, confirm_new_password)
        if err: flash(err, "danger"); return redirect_back()
        
        current_user.set_password(new_password)
    
    # Update Fields
    current_user.first_name = first_name
    current_user.middle_name = middle_name
    current_user.last_name = last_name
    current_user.username = username
    current_user.email = email
    current_user.phone_number = phone_number
    
    db.session.commit()
    flash('Staff profile updated successfully!', 'success')
    return redirect_back()

# ─── ADMIN NOTIFICATIONS API ─────────────────────────
@admin_bp.route('/api/notifications')
@login_required
@admin_required
def admin_notifications():
    """Get recent notifications for the admin/staff user"""
    notifs_data = []

    # Get actual DB notifications assigned to the user
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(15).all()
    for n in notifs:
        notifs_data.append({
            'id': f'db_{n.id}', 'title': n.title, 'message': n.message,
            'type': n.type, 'is_read': n.is_read,
            'link': n.link,
            'created_at': n.created_at.strftime('%b %d, %I:%M %p') if n.created_at else '',
            'raw_date': n.created_at or get_ph_time()
        })

    # Add system-wide live notifications for admins
    if current_user.role and current_user.role.upper() == 'ADMIN':
        pend_users = User.query.filter_by(status='PENDING', is_verified=True).order_by(User.id.desc()).limit(5).all()
        for u in pend_users:
            notifs_data.append({
                'id': f'usr_{u.id}', 'title': 'Account Approval Needed',
                'message': f'{u.first_name} {u.last_name} is awaiting admin approval.',
                'type': 'SYSTEM', 'is_read': False, 'created_at': 'Pending', 'raw_date': get_ph_time(),
                'link': '/admin/approvals'
            })
            
        pend_res = Reservation.query.filter_by(status='PENDING').order_by(Reservation.created_at.desc()).limit(5).all()
        for r in pend_res:
            notifs_data.append({
                'id': f'res_{r.id}', 'title': 'New Reservation Need Confirmation',
                'message': f'{r.guest_count} guests for {r.date.strftime("%b %d")} at {r.time.strftime("%I:%M %p")}.',
                'type': 'RESERVATION', 'is_read': False,
                'created_at': r.created_at.strftime('%b %d, %I:%M %p') if r.created_at else 'Pending',
                'raw_date': r.created_at or get_ph_time(),
                'link': '/admin/reservations'
            })

    # Add order notifications for Staff/Admin
    if current_user.role and current_user.role.upper() in ['ADMIN', 'CASHIER', 'STAFF', 'KITCHEN']:
        pend_ords = Order.query.filter_by(status='PENDING').order_by(Order.created_at.desc()).limit(5).all()
        for o in pend_ords:
            notifs_data.append({
                'id': f'ord_{o.id}', 'title': f'New Order #{o.id}',
                'message': f'Amount: ₱{float(o.total_amount):,.2f} ({o.dining_option})',
                'type': 'ORDER', 'is_read': False,
                'created_at': o.created_at.strftime('%b %d, %I:%M %p') if o.created_at else '',
                'raw_date': o.created_at or get_ph_time(),
                'link': '/admin/kitchen' if o.dining_option != 'DELIVERY' else '/admin/deliveries'
            })

    # Sort manually by created_at (descending)
    notifs_data.sort(key=lambda x: x['raw_date'], reverse=True)

    return jsonify({
        'notifications': notifs_data[:30]
    })

@admin_bp.route('/api/notifications/unread-count')
@login_required
@admin_required
def admin_unread_count():
    """Get unread notification count for admin bell badge"""
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    
    # Also include system-wide counts for admins
    extras = {}
    if current_user.role and current_user.role.upper() == 'ADMIN':
        extras['pending_users'] = User.query.filter_by(status='PENDING', role='USER', is_verified=True).count()
        extras['pending_orders'] = Order.query.filter_by(status='PENDING').count()
        extras['pending_reservations'] = Reservation.query.filter_by(status='PENDING').count()
        extras['pending_reviews'] = Review.query.filter_by(status='PENDING').count()
    elif current_user.role and current_user.role.upper() in ['CASHIER', 'STAFF']:
        extras['pending_orders'] = Order.query.filter_by(status='PENDING').count()
    elif current_user.role and current_user.role.upper() == 'KITCHEN':
        extras['pending_orders'] = Order.query.filter_by(status='PENDING').count()
        extras['preparing_orders'] = Order.query.filter_by(status='PREPARING').count()
    elif current_user.role and current_user.role.upper() == 'RIDER':
        user_branch = getattr(current_user, 'branch', None)
        q = Order.query.filter_by(dining_option='DELIVERY', delivery_status='WAITING')
        if user_branch and user_branch != 'ALL':
            q = q.filter_by(branch=user_branch)
        extras['waiting_deliveries'] = q.count()
    
    return jsonify({'count': count, **extras})

@admin_bp.route('/api/notifications/mark-all-read', methods=['POST'])
@login_required
@admin_required
def admin_mark_all_read():
    """Mark all admin's notifications as read"""
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})

@admin_bp.route('/api/notifications/<notif_id>/read', methods=['POST'])
@login_required
@admin_required
def admin_mark_read(notif_id):
    """Mark a single notification as read. Handles both DB and synthetic IDs."""
    if notif_id.startswith('db_'):
        try:
            db_id = int(notif_id.split('_')[1])
            notif = Notification.query.get(db_id)
            if notif and notif.user_id == current_user.id:
                notif.is_read = True
                db.session.commit()
        except Exception:
            pass
    # Synthetic notifications (usr_, res_, ord_) are not stored as read state in DB for now
    return jsonify({'success': True})

# ─── USER WEB NOTIFICATIONS API ──────────────────────
@admin_bp.route('/web/notifications')
@login_required
def web_user_notifications():
    """Get notifications for logged-in user on the website"""
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(30).all()
    return jsonify({
        'notifications': [{
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'type': n.type,
            'is_read': n.is_read,
            'created_at': n.created_at.strftime('%b %d, %I:%M %p') if n.created_at else '',
        } for n in notifs]
    })

@admin_bp.route('/web/notifications/unread-count')
@login_required
def web_user_unread_count():
    """Get unread count for user notification bell"""
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({'count': count})

@admin_bp.route('/web/notifications/mark-all-read', methods=['POST'])
@login_required
def web_user_mark_all_read():
    """Mark all user web notifications as read"""
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})


def _deduct_order_ingredients_fifo(order_id):
    """
    Deducts ingredients for an order from the KITCHEN-SIDE inventory (kitchen_qty).
    Main inventory is not touched here; it was touched when stock was requested.
    """
    order = Order.query.get(order_id)
    if not order: return

    for oi in order.items:
        recipe = MenuItemIngredient.query.filter_by(menu_item_id=oi.menu_item_id).all()
        for r in recipe:
            total_to_deduct = float(r.quantity_needed) * oi.quantity
            ingredient = Ingredient.query.get(r.ingredient_id)
            if not ingredient: continue

            # 1. Update KITCHEN-SIDE stock
            prev_kitchen = float(ingredient.kitchen_qty or 0)
            ingredient.kitchen_qty = max(0, prev_kitchen - total_to_deduct)
            
            # Use action 'DEDUCT' but log that it was for kitchen use
            log_inventory_change(ingredient.id, 'DEDUCT', total_to_deduct, prev_kitchen, f"Kitchen Use (Order #{order_id})")

            # 2. Sync Availability (Auto-Disable/Enable)
            _sync_single_ingredient_availability(ingredient.id)

    db.session.commit()

def _sync_supplier_catalog(supplier_id):
    """Automatically update the catalog_items text field based on linked ingredients."""
    if not supplier_id: return
    sup = Supplier.query.get(supplier_id)
    if sup:
        names = [i.name for i in sup.ingredients]
        sup.catalog_items = ", ".join(sorted(names)) if names else ""
        db.session.commit()

# ─── INGREDIENT MANAGEMENT ──────────────────────────
@admin_bp.route('/ingredients/update/<int:ing_id>', methods=['POST'])
@login_required
@admin_required
def update_ingredient(ing_id):
    ing = Ingredient.query.get_or_404(ing_id)
    old_supplier_id = ing.supplier_id

    # Update basic fields from form
    name = request.form.get('name', '').strip()
    if name:
        ing.name = name
    unit = request.form.get('unit')
    if unit:
        ing.unit = unit
    category = request.form.get('category')
    if category:
        ing.category = category

    # Stock quantity (the key field for threshold testing)
    new_stock = request.form.get('stock_qty', type=float)
    if new_stock is not None:
        ing.stock_qty = new_stock

    reorder_level = request.form.get('reorder_level', type=float)
    if reorder_level is not None:
        ing.reorder_level = reorder_level

    cost_per_unit = request.form.get('cost_per_unit', type=float)
    if cost_per_unit is not None:
        ing.cost_per_unit = cost_per_unit

    supplier_id = request.form.get('supplier_id', type=int)
    ing.supplier_id = supplier_id if supplier_id else None

    expiration_date_str = request.form.get('expiration_date')
    if expiration_date_str:
        try:
            ing.expiration_date = datetime.strptime(expiration_date_str, '%Y-%m-%d')
        except (ValueError, TypeError):
            pass

    db.session.commit()

    # Sync supplier catalogs
    if supplier_id:
        _sync_supplier_catalog(supplier_id)
    if old_supplier_id and old_supplier_id != supplier_id:
        _sync_supplier_catalog(old_supplier_id)

    # If AJAX request, return JSON
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    log_audit('UPDATE', 'Ingredient', ing.id, f'Updated ingredient: {ing.name}')
    
    if is_ajax:
        supplier_name = ing.supplier.name if ing.supplier else None
        return jsonify({
            'success': True,
            'message': f'Ingredient "{ing.name}" updated!',
            'ingredient': {
                'id': ing.id,
                'name': ing.name,
                'unit': ing.unit,
                'stock_qty': float(ing.stock_qty),
                'reorder_level': float(ing.reorder_level),
                'cost_per_unit': float(ing.cost_per_unit),
                'category': ing.category,
                'supplier_name': supplier_name,
                'expiration_date': ing.expiration_date.strftime('%b %d, %Y') if ing.expiration_date else None,
                'ingredient_code': ing.ingredient_code or '',
            }
        })

    flash(f'Ingredient "{ing.name}" updated!', 'success')
    return redirect(url_for('inventory_portal.inventory_dashboard'))

# @admin_bp.route('/ingredients/delete/<int:ing_id>', methods=['POST'])
# ...

@admin_bp.route('/ingredients/bulk-delete', methods=['POST'])
@login_required
@admin_required
def bulk_delete_ingredients():
    item_ids = request.form.getlist('item_ids[]')
    if item_ids:
        # Collect affected supplier IDs
        affected_suppliers = db.session.query(Ingredient.supplier_id).filter(Ingredient.id.in_(item_ids)).distinct().all()
        supplier_ids = [s[0] for s in affected_suppliers if s[0]]
        
        Ingredient.query.filter(Ingredient.id.in_(item_ids)).delete(synchronize_session=False)
        MenuItemIngredient.query.filter(MenuItemIngredient.ingredient_id.in_(item_ids)).delete(synchronize_session=False)
        db.session.commit()
        
        # Sync all affected catalogs
        for sid in supplier_ids:
            _sync_supplier_catalog(sid)
            
        log_audit('DELETE', 'Ingredient', None, f'Bulk deleted {len(item_ids)} ingredients')
        flash(f'Deleted {len(item_ids)} ingredients.', 'success')
    return redirect(url_for('admin.inventory', tab='ingredients'))

@admin_bp.route('/ingredients/restock/<int:ing_id>', methods=['POST'])
@login_required
@admin_required
def restock_ingredient(ing_id):
    ing = Ingredient.query.get_or_404(ing_id)
    add_qty = request.form.get('add_qty', 0, type=float)
    reason = request.form.get('reason', 'Manual restock')
    if add_qty > 0:
        prev = float(ing.stock_qty)
        log_inventory_change(ing.id, 'ADD', add_qty, prev, reason)
        ing.stock_qty = prev + add_qty
        db.session.commit()

        # Re-enable menu items that use this ingredient AND have all other ingredients in stock
        menu_items_using_ing = MenuItemIngredient.query.filter_by(ingredient_id=ing.id).all()
        for mi_ing in menu_items_using_ing:
            mi = MenuItem.query.get(mi_ing.menu_item_id)
            if mi and not mi.is_available and mi.ingredients:
                can_enable = True
                for other in mi.ingredients:
                    if float(other.ingredient.stock_qty) < float(other.quantity_needed):
                        can_enable = False
                        break
                if can_enable:
                    mi.is_available = True
                    db.session.commit()

        # AJAX return
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            status = 'In Stock'
            if float(ing.stock_qty) <= 0: status = 'Out of Stock'
            elif float(ing.stock_qty) <= float(ing.reorder_level): status = 'Low Stock'
            
            return jsonify({
                'success': True,
                'message': f'Restocked {add_qty} {ing.unit} of "{ing.name}".',
                'new_stock': float(ing.stock_qty),
                'status': status
            })

        flash(f'Restocked {add_qty} {ing.unit} of "{ing.name}".', 'success')
    return redirect(url_for('admin.inventory', tab='ingredients'))

@admin_bp.route('/ingredients/waste/<int:ing_id>', methods=['POST'])
@login_required
@admin_required
def waste_ingredient(ing_id):
    ing = Ingredient.query.get_or_404(ing_id)
    qty = request.form.get('waste_qty', 0, type=float)
    action = request.form.get('action', 'SPOILED') # SPOILED or EXPIRED
    reason = request.form.get('reason', 'Inventory adjustment')
    
    if qty > 0 and qty <= float(ing.stock_qty):
        prev = float(ing.stock_qty)
        log_inventory_change(ing.id, action, qty, prev, reason)
        ing.stock_qty = prev - qty
        db.session.commit()

        # Disable menu items if this ingredient falls below required levels
        menu_items_using_ing = MenuItemIngredient.query.filter_by(ingredient_id=ing.id).all()
        for mi_ing in menu_items_using_ing:
            if float(ing.stock_qty) < float(mi_ing.quantity_needed):
                mi = MenuItem.query.get(mi_ing.menu_item_id)
                if mi and mi.is_available:
                    mi.is_available = False
                    db.session.commit()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            status = 'In Stock'
            if float(ing.stock_qty) <= 0: status = 'Out of Stock'
            elif float(ing.stock_qty) <= float(ing.reorder_level): status = 'Low Stock'
            
            return jsonify({
                'success': True,
                'message': f'Recorded {qty} {ing.unit} as waste.',
                'new_stock': float(ing.stock_qty),
                'status': status
            })

        flash(f'Recorded {qty} {ing.unit} as {action}.', 'warning')
    else:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Invalid quantity. Cannot exceed current stock.'})
        flash('Invalid quantity.', 'danger')
    return redirect(url_for('admin.inventory', tab='ingredients'))

# @admin_bp.route('/inventory/audit-logs')
# @login_required
# @admin_required
def inventory_audit_logs():
    page = request.args.get('page', 1, type=int)
    from models import InventoryLog
    pagination = InventoryLog.query.order_by(InventoryLog.created_at.desc()).paginate(page=page, per_page=50)
    return render_template('admin/inventory_logs.html', pagination=pagination)

# ─── RECIPE (MENU ITEM INGREDIENTS) ──────────────────
@admin_bp.route('/recipe/<int:item_id>', methods=['GET'])
@login_required
@admin_required
def get_recipe(item_id):
    links = MenuItemIngredient.query.filter_by(menu_item_id=item_id).all()
    ingredient_ids = [l.ingredient_id for l in links]
    if not ingredient_ids:
        return jsonify([])

    ingredients = Ingredient.query.filter(Ingredient.id.in_(ingredient_ids)).all()
    ingredients_by_id = {ing.id: ing for ing in ingredients}

    result = []
    for l in links:
        ing = ingredients_by_id.get(l.ingredient_id)
        if not ing:
            continue
        result.append({
            'id': l.id,
            'ingredient_id': ing.id,
            'name': ing.name,
            'unit': ing.unit,
            'quantity_needed': float(l.quantity_needed),
        })
    return jsonify(result)

@admin_bp.route('/recipe/<int:item_id>/add', methods=['POST'])
@login_required
@admin_required
def add_recipe_ingredient(item_id):
    ingredient_id = request.form.get('ingredient_id', type=int)
    quantity_needed = request.form.get('quantity_needed', type=float)
    if not ingredient_id or not quantity_needed:
        flash('Please select an ingredient and specify the quantity.', 'danger')
        return redirect(url_for('inventory_portal.inventory_dashboard'))
    existing = MenuItemIngredient.query.filter_by(menu_item_id=item_id, ingredient_id=ingredient_id).first()
    if existing:
        existing.quantity_needed = quantity_needed
    else:
        link = MenuItemIngredient(menu_item_id=item_id, ingredient_id=ingredient_id, quantity_needed=quantity_needed)
        db.session.add(link)
    db.session.commit()
    
    # Re-check availability after recipe change
    _sync_single_item_availability(item_id)
    
    flash('Recipe updated!', 'success')
    return redirect(url_for('inventory_portal.inventory_dashboard'))

@admin_bp.route('/recipe/remove/<int:link_id>', methods=['POST'])
@login_required
@admin_required
def remove_recipe_ingredient(link_id):
    link = MenuItemIngredient.query.get_or_404(link_id)
    menu_item_id = link.menu_item_id
    db.session.delete(link)
    db.session.commit()
    
    # Re-check availability after recipe change
    _sync_single_item_availability(menu_item_id)
    
    flash('Ingredient removed from recipe.', 'success')
    return redirect(url_for('inventory_portal.inventory_dashboard'))

# ─── AVAILABILITY SYNC HELPERS ───────────────────────
def _sync_single_item_availability(item_id):
    """Re-check and update is_available for a single menu item.
    Rules: No recipe = unavailable. Any ingredient below required qty = unavailable."""
    item = MenuItem.query.get(item_id)
    if not item:
        return
    recipe = MenuItemIngredient.query.filter_by(menu_item_id=item_id).all()
    if not recipe:
        # No recipe defined = cannot prepare = unavailable
        item.is_available = False
    else:
        can_make = True
        ingredient_ids = [r.ingredient_id for r in recipe]
        ingredients = Ingredient.query.filter(Ingredient.id.in_(ingredient_ids)).all()
        ing_by_id = {i.id: i for i in ingredients}
        for r in recipe:
            ing = ing_by_id.get(r.ingredient_id)
            if not ing or float(ing.stock_qty) < float(r.quantity_needed):
                can_make = False
                break
        item.is_available = can_make
    db.session.commit()

@admin_bp.route('/sync-availability', methods=['POST'])
@login_required
@admin_required
def sync_all_availability():
    """Bulk-sync is_available for ALL menu items based on recipe & stock."""
    items = MenuItem.query.filter_by(is_deleted=False).all()
    updated = 0
    for item in items:
        recipe = MenuItemIngredient.query.filter_by(menu_item_id=item.id).all()
        if not recipe:
            new_avail = False
        else:
            new_avail = True
            ingredient_ids = [r.ingredient_id for r in recipe]
            ingredients = Ingredient.query.filter(Ingredient.id.in_(ingredient_ids)).all()
            ing_by_id = {i.id: i for i in ingredients}
            for r in recipe:
                ing = ing_by_id.get(r.ingredient_id)
                if not ing or float(ing.stock_qty) < float(r.quantity_needed):
                    new_avail = False
                    break
        if item.is_available != new_avail:
            item.is_available = new_avail
            updated += 1
    db.session.commit()
    flash(f'Availability synced! {updated} item(s) updated.', 'success')
    return redirect(url_for('admin.inventory', tab='menu-items'))

# ─── SUPPLIER MANAGEMENT ────────────────────────────
@admin_bp.route('/suppliers/add', methods=['POST'])
@login_required
@admin_required
def add_supplier():
    name = request.form.get('name', '').strip()
    contact_person = request.form.get('contact_person', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    address = request.form.get('address', '').strip()
    if not name:
        flash('Supplier name is required.', 'danger')
        return redirect(url_for('admin.inventory', tab='suppliers'))
    sup = Supplier(name=name, contact_person=contact_person, phone=phone, email=email, address=address)
    db.session.add(sup)
    db.session.commit()
    
    # Auto-create ingredients from comma-separated input
    new_ingredients_str = request.form.get('new_ingredients', '').strip()
    if new_ingredients_str:
        sup.catalog_items = new_ingredients_str
        db.session.commit()
        
    log_audit('CREATE', 'Supplier', sup.id, f'Added new supplier: {name}')
    flash(f'Supplier "{name}" added successfully!', 'success')
    return redirect(url_for('admin.inventory', tab='suppliers'))

@admin_bp.route('/suppliers/update/<int:sup_id>', methods=['POST'])
@login_required
@admin_required
def update_supplier(sup_id):
    sup = Supplier.query.get_or_404(sup_id)
    sup.name = request.form.get('name', sup.name).strip()
    sup.contact_person = request.form.get('contact_person', '').strip()
    sup.phone = request.form.get('phone', '').strip()
    sup.email = request.form.get('email', '').strip()
    sup.address = request.form.get('address', '').strip()
    new_catalog = request.form.get('new_ingredients')
    if new_catalog is not None:
        sup.catalog_items = new_catalog.strip()
    db.session.commit()
    log_audit('UPDATE', 'Supplier', sup.id, f'Updated supplier: {sup.name}')
    flash(f'Supplier "{sup.name}" updated!', 'success')
    return redirect(url_for('admin.inventory', tab='suppliers'))

@admin_bp.route('/suppliers/delete/<int:sup_id>', methods=['POST'])
@login_required
@admin_required
def delete_supplier(sup_id):
    sup = Supplier.query.get_or_404(sup_id)
    # Unlink ingredients from this supplier but don't delete them
    Ingredient.query.filter_by(supplier_id=sup_id).update({'supplier_id': None})
    db.session.delete(sup)
    db.session.commit()
    log_audit('DELETE', 'Supplier', sup_id, f'Deleted supplier: {sup.name}')
    flash(f'Supplier "{sup.name}" deleted.', 'success')
    return redirect(url_for('admin.inventory', tab='suppliers'))

@admin_bp.route('/suppliers/bulk-delete', methods=['POST'])
@login_required
@admin_required
def bulk_delete_suppliers():
    item_ids = request.form.getlist('item_ids[]')
    if item_ids:
        Ingredient.query.filter(Ingredient.supplier_id.in_(item_ids)).update({'supplier_id': None}, synchronize_session=False)
        Supplier.query.filter(Supplier.id.in_(item_ids)).delete(synchronize_session=False)
        db.session.commit()
        log_audit('DELETE', 'Supplier', None, f'Bulk deleted {len(item_ids)} suppliers')
        flash(f'Deleted {len(item_ids)} suppliers.', 'success')
    return redirect(url_for('admin.inventory', tab='suppliers'))

# ─── WASTE MANAGEMENT ─────────────────────────────────────────────
# DEPRECATED: Old duplicate routes removed in favor of single canonical routes in inventory_portal (routes/portals/__init__.py)
# @admin_bp.route('/inventory/waste', methods=['GET'])
# @admin_bp.route('/inventory/batches', methods=['GET'])
# @admin_bp.route('/inventory/audit', methods=['GET'])

# ─── KITCHEN STOCK REQUESTS ───────────────────────────────────────
@admin_bp.route('/stock-requests', methods=['GET'])
@login_required
@admin_required
def stock_requests():
    role_upper = current_user.role.upper() if current_user.role else ''
    if role_upper == 'KITCHEN':
        # Kitchen sees its own requests
        requests_list = (
            StockRequest.query.filter_by(requested_by_id=current_user.id)
            .order_by(StockRequest.created_at.desc())
            .limit(200)
            .all()
        )
    else:
        # Inventory / Admin sees all requests
        requests_list = (
            StockRequest.query.order_by(StockRequest.created_at.desc())
            .limit(200)
            .all()
        )
        
    ingredients = Ingredient.query.order_by(Ingredient.category, Ingredient.name).limit(500).all()
    from itertools import groupby
    grouped_ingredients = {}
    for category, group in groupby(ingredients, lambda x: x.category or 'General'):
        # Convert objects to dicts for JSON serialization in template
        grouped_ingredients[category] = [
            {'id': ing.id, 'name': ing.name, 'unit': ing.unit, 'ingredient_code': ing.ingredient_code or ''} for ing in group
        ]
    
    # Auto-suggestion: Get ingredients that need restocking
    # Critical: kitchen_qty = 0
    # Low: 0 < kitchen_qty <= reorder_level
    critical_ingredients = Ingredient.query.filter(
        Ingredient.kitchen_qty == 0
    ).order_by(Ingredient.name).all()
    
    low_ingredients = Ingredient.query.filter(
        Ingredient.kitchen_qty > 0,
        Ingredient.kitchen_qty <= Ingredient.reorder_level
    ).order_by(Ingredient.kitchen_qty, Ingredient.name).all()
    
    # Get pending request ingredient IDs to mark them
    pending_ingredient_ids = set(
        req.ingredient_id for req in StockRequest.query.filter_by(status='PENDING').all()
    )
        
    pending_count = StockRequest.query.filter_by(status='PENDING').count()
    base_layout = 'admin/base.html' if request.path.startswith('/admin') else 'layouts/staff_layout.html'
    return render_template('admin/stock_requests.html',
                           base_layout=base_layout,
                           requests=requests_list, 
                           grouped_ingredients=grouped_ingredients,
                           critical_ingredients=critical_ingredients,
                           low_ingredients=low_ingredients,
                           pending_ingredient_ids=pending_ingredient_ids,
                           pending_count=pending_count)

@admin_bp.route('/stock-requests/create', methods=['POST'])
@login_required
@admin_required
def create_stock_request():
    ing_id = request.form.get('ingredient_id', type=int)
    qty = request.form.get('quantity_requested', type=float)
    notes = request.form.get('notes', '').strip()
    
    ing = Ingredient.query.get(ing_id)
    if not ing:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Ingredient not found.'})
        flash('Ingredient not found.', 'danger')
        return redirect(url_for('admin.stock_requests'))
        
    # Validation: Do not allow request if main inventory cannot fulfill it
    if float(ing.stock_qty) < qty:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': f'Insufficient warehouse stock. Only {ing.stock_qty} {ing.unit} available. Cannot fulfill this request.'})
        flash(f'Insufficient warehouse stock. Only {ing.stock_qty} {ing.unit} available.', 'danger')
        return redirect(url_for('admin.stock_requests'))
        
    req = StockRequest(
        ingredient_id=ing_id,
        requested_by_id=current_user.id,
        quantity_requested=qty,
        quantity_fulfilled=0,
        status='PENDING',
        fulfilled_by_id=None,
        notes=notes
    )
    db.session.add(req)
    db.session.commit()
    
    # Notify inventory staff about the new request
    inv_staff = User.query.filter(User.role.in_(['INVENTORY_STAFF', 'INVENTORY', 'ADMIN'])).all()
    for s in inv_staff:
        _create_web_notification(s.id, 'New Stock Request', f'{current_user.first_name} requested {qty} units of {req.ingredient.name}', 'SYSTEM')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'message': 'Stock request submitted! Waiting for inventory staff approval.'
        })

    flash('Stock request submitted!', 'info')
    return redirect(url_for('admin.stock_requests'))

@admin_bp.route('/stock-requests/<int:req_id>/fulfill', methods=['POST'])
@login_required
@admin_required
def fulfill_stock_request(req_id):
    req = StockRequest.query.get_or_404(req_id)
    action = request.form.get('action')  # approve, reject, fulfill
    qty_fulfilled = request.form.get('quantity_fulfilled', type=float)

    if action == 'reject':
        req.status = 'REJECTED'
        req.fulfilled_by_id = current_user.id
        db.session.commit()
        _create_web_notification(req.requested_by_id, 'Stock Request Rejected', f'Your request for {req.ingredient.name} was rejected.', 'SYSTEM')
        flash(f'Stock request #{req_id} rejected.', 'warning')
    elif action == 'fulfill' and qty_fulfilled:
        ing = Ingredient.query.get(req.ingredient_id)
        if ing:
            # Validate against main stock
            if float(ing.stock_qty) < qty_fulfilled:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'message': f'Insufficient warehouse stock. Current: {ing.stock_qty} {ing.unit}'})
                flash(f'Insufficient warehouse stock. Only {ing.stock_qty} {ing.unit} available.', 'danger')
                return redirect(url_for('admin.stock_requests'))

            # 1. Deduct from Main Inventory (FIFO)
            prev_main = float(ing.stock_qty)
            ing.stock_qty = max(0, prev_main - qty_fulfilled)
            log_inventory_change(ing.id, 'DEDUCT', qty_fulfilled, prev_main, f"Transfer to Kitchen (Req #{req_id})")

            # 2. Add to Kitchen Side
            prev_kitchen = float(ing.kitchen_qty or 0)
            ing.kitchen_qty = prev_kitchen + qty_fulfilled
            log_inventory_change(ing.id, 'ADD', qty_fulfilled, prev_kitchen, f"Received from Bodega (Req #{req_id})")

            # 3. Handle FIFO Batches (Exhaust from Warehouse)
            remaining_needed = qty_fulfilled
            batches = IngredientBatch.query.filter_by(ingredient_id=ing.id, is_exhausted=False)\
                                           .order_by(IngredientBatch.purchase_date.asc(), IngredientBatch.id.asc()).all()
            for batch in batches:
                if remaining_needed <= 0: break
                batch_avail = float(batch.remaining_qty)
                if batch_avail <= remaining_needed:
                    remaining_needed -= batch_avail
                    batch.remaining_qty = 0
                    batch.is_exhausted = True
                else:
                    batch.remaining_qty = batch_avail - remaining_needed
                    remaining_needed = 0

            # 4. Mandatory Sync: Auto-update is_available for all menus using this ingredient
            _sync_single_ingredient_availability(ing.id)

        req.quantity_fulfilled = qty_fulfilled
        req.fulfilled_by_id = current_user.id
        req.status = 'FULFILLED'
        db.session.commit()
        
        _create_web_notification(req.requested_by_id, 'Stock Request Fulfilled', f'{qty_fulfilled} {ing.unit} of {ing.name} is ready for Kitchen.', 'SYSTEM')
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': f'Stock request #{req_id} fulfilled! {qty_fulfilled} units transferred to kitchen.'
            })

        flash(f'Stock request #{req_id} fulfilled! {qty_fulfilled} units transferred to kitchen.', 'success')
        return redirect(url_for('admin.stock_requests'))

def _sync_single_ingredient_availability(ing_id):
    """Checks kitchen stock and toggles is_available for any menu item using this ingredient."""
    links = MenuItemIngredient.query.filter_by(ingredient_id=ing_id).all()
    for link in links:
        mi = MenuItem.query.get(link.menu_item_id)
        if not mi: continue
        
        # Check all ingredients for this menu item to see if it can still be prepared
        can_make = True
        for recipe_item in mi.ingredients:
            qty_in_kitchen = float(recipe_item.ingredient.kitchen_qty or 0)
            qty_needed_per_serving = float(recipe_item.quantity_needed or 0)
            
            # If we don't even have enough for 1 single serving, it's Sold Out
            if qty_in_kitchen < qty_needed_per_serving:
                can_make = False
                break
        
        # Update the status
        mi.is_available = can_make
    
    db.session.commit()

# ─── CUSTOMER CHAT MANAGEMENT ──────────────────────
@admin_bp.route('/chats')
@login_required
@admin_required
def chats():
    """List all users who have sent messages"""
    from models import db
    # Get users who have messages, grouped by user
    subquery = db.session.query(
        ChatMessage.user_id,
        func.max(ChatMessage.created_at).label('last_msg_at')
    ).group_by(ChatMessage.user_id).subquery()
    
    chat_users = db.session.query(User, subquery.c.last_msg_at)\
        .join(subquery, User.id == subquery.c.user_id)\
        .order_by(subquery.c.last_msg_at.desc()).limit(200).all()
        
    return render_template('admin/chats.html', chat_users=chat_users)

@admin_bp.route('/chats/<int:user_id>')
@login_required
@admin_required
def chat_with_user(user_id):
    """View chat history and reply to a specific user"""
    user = User.query.get_or_404(user_id)
    # Cap payload for speed. Keep chronological order for UI.
    messages_desc = (
        ChatMessage.query.filter_by(user_id=user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(300)
        .all()
    )
    messages = list(reversed(messages_desc))
    
    # Mark messages as read by admin
    ChatMessage.query.filter_by(user_id=user_id, sender='USER', is_read=False).update({'is_read': True})
    db.session.commit()
    
    return render_template('admin/chat_detail.html', user=user, messages=messages)

@admin_bp.route('/chats/<int:user_id>/reply', methods=['POST'])
@login_required
@admin_required
def chat_reply(user_id):
    """Send a reply from admin to a user"""
    from flask import request
    message_text = request.form.get('message', '').strip()
    if not message_text:
        flash("Message cannot be empty.", "danger")
        return redirect(url_for('admin.chat_with_user', user_id=user_id))
        
    new_msg = ChatMessage(
        user_id=user_id,
        sender='ADMIN',
        message=message_text,
        is_read=False
    )
    db.session.add(new_msg)
    db.session.commit()
    
    return redirect(url_for('admin.chat_with_user', user_id=user_id))

# ─── AUDIT LOG HELPER ──────────────────────────────
def log_audit(action, target_type, target_id, description):
    """Centralized audit log helper"""
    try:
        log = AuditLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            description=description,
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()

# ─── AUDIT LOGS PAGE ───────────────────────────────
@admin_bp.route('/audit-logs')
@login_required
@admin_required
def audit_logs():
    if current_user.role.upper() != 'SUPER_ADMIN':
        flash("Access denied. Admin Boss only.", "danger")
        return redirect(url_for('admin.overview'))
    """View system audit logs"""
    page = request.args.get('page', 1, type=int)
    per_page = 30
    user_branch = getattr(current_user, 'branch', None)
    if user_branch and user_branch not in ('ALL', 'Pagsanjan'):
        class MockPagination:
            items = []
            page = 1
            pages = 1
            has_next = False
            has_prev = False
            iter_pages = lambda self: []
        logs = MockPagination()
    else:
        logs = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('admin/audit_logs.html', logs=logs)

# ─── SMART INVENTORY ALERTS API ────────────────────
@admin_bp.route('/api/inventory-alerts')
@login_required
@admin_required
def inventory_alerts_api():
    """Get low-stock ingredient alerts"""
    low_stock = Ingredient.query.filter(
        Ingredient.stock_qty <= Ingredient.reorder_level
    ).order_by(Ingredient.stock_qty.asc()).limit(300).all()
    alerts = []
    for ing in low_stock:
        alerts.append({
            'id': ing.id,
            'name': ing.name,
            'stock_qty': float(ing.stock_qty),
            'reorder_level': float(ing.reorder_level),
            'unit': ing.unit,
            'status': 'OUT_OF_STOCK' if float(ing.stock_qty) == 0 else 'LOW_STOCK'
        })
    return jsonify({'success': True, 'alerts': alerts, 'count': len(alerts)})

# ─── ADVANCED ANALYTICS: PEAK HOURS + RETENTION ───
@admin_bp.route('/api/advanced-analytics')
@login_required
@admin_required
def advanced_analytics_api():
    """Advanced business analytics (peak hours, retention rate)"""
    import json as _json
    today = date.today()

    # Peak Hours Analysis
    hour_col = func.extract('hour', Order.created_at)
    peak_data = db.session.query(
        hour_col.label('hr'),
        func.count(Order.id).label('cnt')
    ).group_by(hour_col).order_by(func.count(Order.id).desc()).all()
    
    peak_hours = []
    for h, c in peak_data[:5]:
        if h is not None:
            try:
                peak_hours.append({'hour': f'{int(h):02d}:00', 'orders': int(c or 0)})
            except (ValueError, TypeError):
                pass

    # Customer Retention Rate
    total_customers_with_orders = db.session.query(func.count(func.distinct(Order.user_id))).scalar() or 0
    
    repeat_sub = db.session.query(Order.user_id).group_by(Order.user_id).having(func.count(Order.id) > 1).subquery()
    repeat_count = db.session.query(func.count()).select_from(repeat_sub).scalar() or 0
    
    retention_rate = round((repeat_count / total_customers_with_orders * 100), 1) if total_customers_with_orders > 0 else 0

    # Average Order Value
    avg_order = db.session.query(func.avg(Order.total_amount)).scalar()
    avg_order_value = round(float(avg_order), 2) if avg_order else 0

    # Orders by Day of Week
    dow_col = func.extract('dow', Order.created_at)
    dow_data = db.session.query(
        dow_col.label('dow'),
        func.count(Order.id)
    ).group_by(dow_col).order_by(dow_col).all()
    days_map = {0: 'Sun', 1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri', 6: 'Sat'}
    orders_by_day = []
    for d, c in dow_data:
        if d is not None:
            try:
                orders_by_day.append({'day': days_map.get(int(d), str(d)), 'orders': int(c or 0)})
            except (ValueError, TypeError):
                pass

    return jsonify({
        'success': True,
        'peak_hours': peak_hours,
        'retention_rate': retention_rate,
        'repeat_customers': repeat_count,
        'total_customers_with_orders': total_customers_with_orders,
        'avg_order_value': avg_order_value,
        'orders_by_day': orders_by_day
    })

# ─── VOUCHER MANAGEMENT (ADMIN) ───────────────────
@admin_bp.route('/vouchers')
@login_required
@admin_required
def vouchers():
    if current_user.role.upper() != 'SUPER_ADMIN':
        flash("Access denied. Admin Boss only.", "danger")
        return redirect(url_for('admin.overview'))
    """List all vouchers"""
    user_branch = getattr(current_user, 'branch', None)
    if user_branch and user_branch not in ('ALL', 'Pagsanjan'):
        all_vouchers = []
    else:
        all_vouchers = Voucher.query.order_by(Voucher.created_at.desc()).limit(200).all()
    return render_template('admin/vouchers.html', vouchers=all_vouchers)

@admin_bp.route('/vouchers/add', methods=['POST'])
@login_required
@admin_required
def voucher_add():
    """Create a new voucher"""
    code = request.form.get('code', '').strip().upper()
    discount_type = request.form.get('discount_type', 'PERCENT')
    discount_value = request.form.get('discount_value', 0, type=float)
    min_order = request.form.get('min_order_amount', 0, type=float)
    max_uses = request.form.get('max_uses', 100, type=int)
    valid_from_str = request.form.get('valid_from', '')
    valid_until_str = request.form.get('valid_until', '')

    # ── Validation ──────────────────────────────────────────────
    errors = []

    if not code:
        errors.append("Voucher code is required.")

    if discount_value <= 0:
        errors.append("Discount value must be greater than 0.")

    if discount_type == 'PERCENT':
        if discount_value > 80:
            errors.append("Percentage discount cannot exceed 80%.")
    else:  # FIXED
        # Get the lowest menu item price as a ceiling reference
        from models import MenuItem
        cheapest = db.session.query(db.func.min(MenuItem.price)).filter_by(is_deleted=False, is_available=True).scalar()
        max_fixed = float(cheapest) if cheapest else 9999
        if discount_value >= max_fixed:
            errors.append(f"Fixed discount (₱{discount_value:.2f}) cannot be equal to or exceed the cheapest menu item price (₱{max_fixed:.2f}). It would make items free.")

    if max_uses < 1:
        errors.append("Max uses must be at least 1.")

    if min_order < 0:
        errors.append("Minimum order amount cannot be negative.")
    if min_order > 99999:
        errors.append("Minimum order amount cannot exceed ₱99,999.")

    now = datetime.now()
    valid_from = None
    valid_until = None

    if valid_from_str:
        valid_from = datetime.strptime(valid_from_str, '%Y-%m-%d')
        if valid_from.date() < now.date():
            errors.append("Valid From date cannot be in the past.")
        if valid_from.date() > (now + timedelta(days=30)).date():
            errors.append("Valid From date cannot be more than 1 month from today.")

    if valid_until_str:
        valid_until = datetime.strptime(valid_until_str, '%Y-%m-%d')
        start = valid_from if valid_from else now
        if valid_until <= start:
            errors.append("Valid Until must be after the Valid From date.")
        max_until = start + timedelta(days=30)
        if valid_until > max_until:
            errors.append("Valid Until cannot be more than 1 month from the start date.")

    if errors:
        for e in errors:
            flash(e, "danger")
        return redirect(url_for('admin.vouchers'))

    if Voucher.query.filter_by(code=code).first():
        flash(f"Voucher code '{code}' already exists.", "danger")
        return redirect(url_for('admin.vouchers'))

    v = Voucher(
        code=code,
        discount_type=discount_type,
        discount_value=discount_value,
        min_order_amount=min_order,
        max_uses=max_uses,
        valid_from=valid_from,
        valid_until=valid_until
    )
    db.session.add(v)
    db.session.commit()

    log_audit('CREATE', 'Voucher', v.id, f'Created voucher {code} ({discount_type} {discount_value})')
    flash(f"Voucher '{code}' created successfully!", "success")
    return redirect(url_for('admin.vouchers'))

@admin_bp.route('/vouchers/<int:voucher_id>/toggle', methods=['POST'])
@login_required
@admin_required
def voucher_toggle(voucher_id):
    """Toggle voucher active/inactive"""
    v = Voucher.query.get_or_404(voucher_id)
    v.is_active = not v.is_active
    db.session.commit()
    status = 'activated' if v.is_active else 'deactivated'
    log_audit('UPDATE', 'Voucher', v.id, f'Voucher {v.code} {status}')
    flash(f"Voucher '{v.code}' {status}.", "success")
    return redirect(url_for('admin.vouchers'))

@admin_bp.route('/vouchers/<int:voucher_id>/delete', methods=['POST'])
@login_required
@admin_required
def voucher_delete(voucher_id):
    """Delete a voucher"""
    v = Voucher.query.get_or_404(voucher_id)
    code = v.code
    db.session.delete(v)
    db.session.commit()
    log_audit('DELETE', 'Voucher', voucher_id, f'Deleted voucher {code}')
    flash(f"Voucher '{code}' deleted.", "success")
    return redirect(url_for('admin.vouchers'))

# ─── DELIVERY AREAS MANAGEMENT ───────────────────────────────────
@admin_bp.route('/delivery-areas', methods=['GET'])
@login_required
@admin_required
def delivery_areas():
    if current_user.role.upper() != 'SUPER_ADMIN':
        flash("Access denied. Admin Boss only.", "danger")
        return redirect(url_for('admin.overview'))
    from models import DeliveryArea
    all_areas = DeliveryArea.query.order_by(DeliveryArea.branch.asc(), DeliveryArea.municipality.asc()).all()
    
    # Group by branch
    grouped_areas = {}
    for area in all_areas:
        if area.branch not in grouped_areas:
            grouped_areas[area.branch] = []
        grouped_areas[area.branch].append(area)
        
    return render_template('admin/delivery_areas.html', grouped_areas=grouped_areas)

@admin_bp.route('/delivery-areas/add', methods=['POST'])
@login_required
@admin_required
def delivery_area_add():
    import json
    from models import DeliveryArea
    municipality = request.form.get('municipality', '').strip().title()
    branch = request.form.get('branch', 'Pagsanjan')
    barangays_raw = request.form.get('barangays', '').strip()
    lat = request.form.get('lat', type=float)
    lng = request.form.get('lng', type=float)

    if not municipality:
        flash("Municipality name is required.", "danger")
        return redirect(url_for('admin.delivery_areas'))

    if DeliveryArea.query.filter_by(municipality=municipality, branch=branch).first():
        flash(f"'{municipality}' already exists for {branch}.", "danger")
        return redirect(url_for('admin.delivery_areas'))

    # Parse barangays — one per line or comma-separated
    brgys = [b.strip() for b in barangays_raw.replace('\n', ',').split(',') if b.strip()]
    if not brgys:
        flash("At least one barangay is required.", "danger")
        return redirect(url_for('admin.delivery_areas'))

    area = DeliveryArea(
        municipality=municipality,
        branch=branch,
        barangays=json.dumps(brgys),
        lat=lat,
        lng=lng,
        is_active=True
    )
    db.session.add(area)
    db.session.commit()
    log_audit('CREATE', 'DeliveryArea', area.id, f'Added delivery area: {municipality}')
    flash(f"Delivery area '{municipality}' added.", "success")
    return redirect(url_for('admin.delivery_areas'))

@admin_bp.route('/delivery-areas/<int:area_id>/edit', methods=['POST'])
@login_required
@admin_required
def delivery_area_edit(area_id):
    import json
    from models import DeliveryArea
    area = DeliveryArea.query.get_or_404(area_id)
    municipality = request.form.get('municipality', '').strip().title()
    branch = request.form.get('branch', area.branch)
    barangays_raw = request.form.get('barangays', '').strip()
    lat = request.form.get('lat', type=float)
    lng = request.form.get('lng', type=float)

    if not municipality:
        flash("Municipality name is required.", "danger")
        return redirect(url_for('admin.delivery_areas'))

    # Check duplicate (excluding self)
    dup = DeliveryArea.query.filter(DeliveryArea.municipality == municipality, DeliveryArea.branch == branch, DeliveryArea.id != area_id).first()
    if dup:
        flash(f"'{municipality}' already exists for {branch}.", "danger")
        return redirect(url_for('admin.delivery_areas'))

    brgys = [b.strip() for b in barangays_raw.replace('\n', ',').split(',') if b.strip()]
    if not brgys:
        flash("At least one barangay is required.", "danger")
        return redirect(url_for('admin.delivery_areas'))

    area.municipality = municipality
    area.branch = branch
    area.barangays = json.dumps(brgys)
    area.lat = lat
    area.lng = lng
    db.session.commit()
    log_audit('UPDATE', 'DeliveryArea', area.id, f'Updated delivery area: {municipality}')
    flash(f"Delivery area '{municipality}' updated.", "success")
    return redirect(url_for('admin.delivery_areas'))

@admin_bp.route('/delivery-areas/<int:area_id>/toggle', methods=['POST'])
@login_required
@admin_required
def delivery_area_toggle(area_id):
    from models import DeliveryArea
    area = DeliveryArea.query.get_or_404(area_id)
    area.is_active = not area.is_active
    db.session.commit()
    status = 'enabled' if area.is_active else 'disabled'
    log_audit('UPDATE', 'DeliveryArea', area.id, f'Delivery area {area.municipality} {status}')
    return {'status': 'ok', 'is_active': area.is_active}

@admin_bp.route('/delivery-areas/<int:area_id>/delete', methods=['POST'])
@login_required
@admin_required
def delivery_area_delete(area_id):
    from models import DeliveryArea
    area = DeliveryArea.query.get_or_404(area_id)
    name = area.municipality
    db.session.delete(area)
    db.session.commit()
    log_audit('DELETE', 'DeliveryArea', area_id, f'Deleted delivery area: {name}')
    return {'status': 'ok'}

# ─── CONTACT MESSAGES MANAGEMENT ───────────────────
@admin_bp.route('/contact-messages')
@login_required
@admin_required
def contact_messages():
    """List all contact us messages"""
    from models import ContactMessage
    user_branch = getattr(current_user, 'branch', None)
    if user_branch and user_branch not in ('ALL', 'Pagsanjan'):
        messages = []
    else:
        messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
        
    # mark all as read when admin visits the page
    has_unread = False
    for m in messages:
        if not m.is_read:
            m.is_read = True
            has_unread = True
            
    if has_unread:
        db.session.commit()

    return render_template('admin/contact_messages.html', messages=messages)

@admin_bp.route('/contact-messages/reply/<int:msg_id>', methods=['POST'])
@login_required
@admin_required
def reply_contact_message(msg_id):
    """Reply to a contact us message via email"""
    from models import ContactMessage
    from utils import send_email, get_ph_time
    from flask import request
    
    message = ContactMessage.query.get_or_404(msg_id)
    reply_text = request.form.get('reply_message', '').strip()
    
    if reply_text:
        # Send email
        subject = "Re: Your Contact Us Message to Le Maison Yelo Lane"
        
        # Use HTML formatting so it displays correctly and elegantly in email clients
        body = f"""
        <div style="font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 12px; overflow: hidden; background-color: #ffffff;">
            <!-- Header -->
            <div style="background-color: #3E2723; padding: 25px; text-align: center;">
                <h2 style="color: #c9a96e; margin: 0; font-family: Georgia, serif; font-weight: normal; letter-spacing: 1px;">Le Maison Yelo Lane</h2>
            </div>
            
            <!-- Body -->
            <div style="padding: 30px; color: #4a4a4a; line-height: 1.6;">
                <h3 style="color: #3E2723; margin-top: 0; font-size: 20px;">Hello {message.first_name},</h3>
                
                <p>Thank you for reaching out to us. We appreciate you taking the time to write to Le Maison Yelo Lane.</p>
                
                <!-- Our Reply -->
                <div style="background-color: #f0fdf4; border-left: 4px solid #059669; padding: 15px 20px; margin: 25px 0; border-radius: 0 8px 8px 0;">
                    <p style="margin: 0; color: #065f46; font-size: 13px; text-transform: uppercase; letter-spacing: 1px; font-weight: bold; margin-bottom: 8px;">Our Response</p>
                    <p style="margin: 0; color: #1f2937; white-space: pre-wrap;">{reply_text}</p>
                </div>
                
                <!-- Original Message Snippet -->
                <div style="background-color: #f9f9f9; padding: 15px 20px; border-radius: 8px; margin-top: 30px;">
                    <p style="margin: 0; color: #888888; font-size: 13px; text-transform: uppercase; letter-spacing: 1px; font-weight: bold; margin-bottom: 8px;">Your Original Message</p>
                    <p style="margin: 0; color: #666666; font-style: italic; white-space: pre-wrap;">"{message.message}"</p>
                </div>
                
                <p style="margin-top: 30px; margin-bottom: 0;">Warm regards,<br>
                <strong style="color: #3E2723;">The Le Maison Yelo Lane Team</strong></p>
            </div>
            
            <!-- Footer -->
            <div style="background-color: #f5f5f5; padding: 15px; text-align: center; border-top: 1px solid #eeeeee;">
                <p style="margin: 0; color: #888888; font-size: 12px;">Yelo Lane, General Taino Street, Pagsanjan, Laguna</p>
            </div>
        </div>
        """
        try:
            send_email(message.email, subject, body)
            
            # Update DB
            message.is_replied = True
            message.reply_message = reply_text
            message.replied_by_id = current_user.id
            message.replied_at = get_ph_time()
            db.session.commit()
            
            flash('Reply sent successfully to ' + message.email, 'success')
            log_audit('UPDATE', 'ContactMessage', message.id, f'Replied to message from {message.email}')
        except Exception as e:
            flash(f'Failed to send email: {str(e)}', 'danger')
            db.session.rollback()
    else:
        flash('Reply message cannot be empty.', 'danger')
        
    return redirect(url_for('admin.contact_messages'))


# ─── DATA ARCHIVE MANAGEMENT ─────────────────────────────────────
@admin_bp.route('/archive')
@login_required
@admin_required
def archive_dashboard():
    if current_user.role.upper() != 'SUPER_ADMIN':
        flash("Access denied. Super Admin only.", "danger")
        return redirect(url_for('admin.overview'))

    from archive import get_archive_manager
    from sqlalchemy.exc import OperationalError
    
    manager = get_archive_manager()
    if not manager:
        flash("Archive system is not initialized.", "danger")
        return redirect(url_for('admin.overview'))

    try:
        stats = manager.get_stats()
        timeline = manager.get_archive_storage_summary()
    except OperationalError as e:
        from models import db
        db.session.rollback()
        flash(f"Database connection error. Please try again. Error: {str(e)}", "danger")
        return redirect(url_for('admin.overview'))
    except Exception as e:
        flash(f"Error loading archive data: {str(e)}", "danger")
        return redirect(url_for('admin.overview'))
    
    return render_template(
        'admin/archive.html',
        stats=stats,
        timeline=timeline,
        config=manager.config,
    )


@admin_bp.route('/archive/run', methods=['POST'])
@login_required
@admin_required
def archive_run_now():
    if current_user.role.upper() != 'SUPER_ADMIN':
        flash("Access denied. Super Admin only.", "danger")
        return redirect(url_for('admin.overview'))

    from archive import get_archive_manager
    from sqlalchemy.exc import OperationalError
    
    manager = get_archive_manager()
    dry_run = request.form.get('dry_run') == '1'

    try:
        result = manager.run(triggered_by='admin', user_id=current_user.id, dry_run=dry_run)
    except OperationalError as e:
        from models import db
        db.session.rollback()
        flash(f"Database connection error during archive: {str(e)}", "danger")
        return redirect(url_for('admin.archive_dashboard'))
    except Exception as e:
        flash(f"Unexpected error during archive: {str(e)}", "danger")
        return redirect(url_for('admin.archive_dashboard'))

    if result['success']:
        summary = result['summary']
        if dry_run:
            flash(
                f"Dry run complete. Eligible preview — orders: {summary.get('orders', 0)}, "
                f"reservations: {summary.get('reservations', 0)}, audit logs: {summary.get('audit_logs', 0)}.",
                "info",
            )
        else:
            flash(
                f"Archive completed. Moved — orders: {summary.get('orders', 0)}, "
                f"reservations: {summary.get('reservations', 0)}, audit logs: {summary.get('audit_logs', 0)}, "
                f"inventory logs: {summary.get('inventory_logs', 0)}, notifications: {summary.get('notifications', 0)}.",
                "success",
            )
    else:
        flash(f"Archive failed: {result.get('error', 'Unknown error')}", "danger")

    return redirect(url_for('admin.archive_dashboard'))


@admin_bp.route('/archive/orders')
@login_required
@admin_required
def archive_orders():
    if current_user.role.upper() != 'SUPER_ADMIN':
        flash("Access denied. Super Admin only.", "danger")
        return redirect(url_for('admin.overview'))

    from archive import get_archive_manager
    manager = get_archive_manager()
    page = request.args.get('page', 1, type=int)
    branch = request.args.get('branch', '')
    status = request.args.get('status', '')
    source = request.args.get('source', 'soft')

    pagination = manager.search_archived_orders(
        page=page,
        branch=branch or None,
        status=status or None,
        source=source,
    )
    return render_template(
        'admin/archive_orders.html',
        pagination=pagination,
        branch=branch,
        status=status,
        source=source,
    )


@admin_bp.route('/archive/orders/<int:original_id>')
@login_required
@admin_required
def archive_order_detail(original_id):
    if current_user.role.upper() != 'SUPER_ADMIN':
        flash("Access denied. Super Admin only.", "danger")
        return redirect(url_for('admin.overview'))

    from archive import get_archive_manager
    manager = get_archive_manager()
    source = request.args.get('source')
    detail = manager.get_archived_order_detail(original_id, source=source)
    if not detail:
        flash("Archived order not found.", "warning")
        return redirect(url_for('admin.archive_orders'))

    return render_template('admin/archive_order_detail.html', detail=detail)


@admin_bp.route('/archive/orders/<int:order_id>/restore', methods=['POST'])
@login_required
@admin_required
def archive_order_restore(order_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if current_user.role.upper() != 'SUPER_ADMIN':
        if is_ajax:
            return jsonify({'success': False, 'message': 'Access denied. Super Admin only.'}), 403
        flash("Access denied. Super Admin only.", "danger")
        return redirect(url_for('admin.overview'))

    order = Order.query.get_or_404(order_id)
    if not order.is_archived:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Order is not archived.'}), 400
        flash("Order is not archived.", "warning")
        return redirect(url_for('admin.orders'))

    order.is_archived = False
    order.archived_at = None
    db.session.commit()
    log_audit('RESTORE', 'Order', order.id, f'Unarchived order #{order.id}')
    if is_ajax:
        return jsonify({'success': True, 'message': 'Order restored successfully.', 'redirect': url_for('admin.orders')})
    flash("Order restored successfully.", "success")
    return redirect(url_for('admin.orders'))




@admin_bp.route('/api/archive/orders', methods=['GET'])
@login_required
@admin_required
def api_archive_orders():
    """API endpoint for fetching archived orders as JSON"""
    if current_user.role.upper() != 'SUPER_ADMIN':
        return jsonify({'error': 'Access denied'}), 403

    from archive import get_archive_manager
    manager = get_archive_manager()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 15, type=int)
    branch = request.args.get('branch', '')
    status = request.args.get('status', '')
    source = request.args.get('source', 'soft')

    pagination = manager.search_archived_orders(
        page=page,
        per_page=per_page,
        branch=branch or None,
        status=status or None,
        source=source,
    )

    orders_data = []
    for order in pagination.items:
        original_id = order.original_id if source == 'legacy' else order.id
        orders_data.append({
            'original_id': original_id,
            'order_code': order.order_code or '—',
            'branch': order.branch or '—',
            'status': order.status,
            'total_amount': float(order.total_amount) if order.total_amount else 0,
            'created_at': order.created_at.strftime('%Y-%m-%d') if order.created_at else '—',
            'archived_at': order.archived_at.strftime('%Y-%m-%d') if order.archived_at else '—',
        })

    return jsonify({
        'orders': orders_data,
        'pagination': {
            'page': pagination.page,
            'total_pages': pagination.pages,
            'total_items': pagination.total,
            'has_prev': pagination.has_prev,
            'has_next': pagination.has_next,
        }
    })
