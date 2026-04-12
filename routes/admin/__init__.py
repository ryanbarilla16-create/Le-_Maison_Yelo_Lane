from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user, login_user, logout_user
from flask_mail import Message
from models import db, User, Reservation, MenuItem, Order, OrderItem, Review, Notification, Supplier, Ingredient, MenuItemIngredient, ChatMessage, AuditLog, Voucher, InventoryLog, WasteRecord, IngredientBatch, StockRequest
from datetime import datetime, date, timedelta
from utils import get_ph_time, create_notification, validate_name, validate_email, validate_username, validate_password
from sqlalchemy import func
from sqlalchemy.orm import load_only, selectinload
from functools import wraps
import traceback
import time
import threading
from itertools import groupby
from sqlalchemy import text as sql_text
import random
from utils import get_ph_time, create_notification, validate_name, validate_email, validate_username, validate_password, safe_elapsed

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

def _create_web_notification(user_id, title, message, notif_type='SYSTEM'):
    """Backwards compatible helper for admin routes"""
    return create_notification(user_id, title, message, notif_type)

def log_inventory_change(ingredient_id, action, quantity, previous_stock, reason=None):
    from models import InventoryLog
    new_stock = previous_stock
    if action == 'ADD':
        new_stock = previous_stock + quantity
    elif action in ['DEDUCT', 'EXPIRED', 'SPOILED']:
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
    @wraps(f)
    def decorated_function(*args, **kwargs):
        allowed_roles = ['ADMIN', 'CASHIER', 'INVENTORY_STAFF', 'INVENTORY', 'KITCHEN', 'STAFF', 'RIDER']
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
    if current_user.role.upper() != 'ADMIN':
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
    allowed_roles = ['ADMIN', 'CASHIER', 'INVENTORY_STAFF', 'INVENTORY', 'KITCHEN', 'STAFF', 'RIDER']
    
    if current_user.is_authenticated and current_user.role and current_user.role.upper() in allowed_roles:
        role_upper = current_user.role.upper()
        if role_upper == 'CASHIER':
            return redirect(url_for('admin.orders'))
        elif role_upper in ['INVENTORY_STAFF', 'INVENTORY']:
            return redirect(url_for('admin.inventory'))
        elif role_upper == 'KITCHEN':
            return redirect(url_for('admin.kitchen_view'))
        elif role_upper == 'RIDER':
            return redirect(url_for('admin.deliveries'))
        return redirect(url_for('admin.overview'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        pwd = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(pwd) and user.role and user.role.upper() in allowed_roles:
            login_user(user)
            role_upper = user.role.upper()
            if role_upper == 'CASHIER':
                return redirect(url_for('admin.orders'))
            elif role_upper in ['INVENTORY_STAFF', 'INVENTORY']:
                return redirect(url_for('admin.inventory'))
            elif role_upper == 'KITCHEN':
                return redirect(url_for('admin.kitchen_view'))
            elif role_upper == 'RIDER':
                return redirect(url_for('admin.deliveries'))
            return redirect(url_for('admin.overview'))
            
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
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        user = User.query.filter_by(email=email).first()
        
        # Security: Only allow staff roles to use this flow
        allowed_roles = ['ADMIN', 'CASHIER', 'INVENTORY_STAFF', 'INVENTORY', 'KITCHEN', 'STAFF', 'RIDER']
        if not user or not user.role or user.role.upper() not in allowed_roles:
            flash(f"If an account exists for {email}, a reset code has been sent.", "info")
            return redirect(url_for('admin.admin_login'))
            
        if user.otp_created_at:
            elapsed = safe_elapsed(user.otp_created_at)
            if elapsed < 60:
                flash(f"Please wait {int(60 - elapsed)}s before requesting a new code.", "warning")
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
        return redirect(url_for('admin.admin_verify_reset_otp', user_id=user.id))
        
    return render_template('admin/forgot_password.html')

@admin_bp.route('/verify-reset-otp/<int:user_id>', methods=['GET', 'POST'])
def admin_verify_reset_otp(user_id):
    from flask import session
    if session.get('admin_reset_user_id') != user_id:
        flash("Invalid session.", "danger")
        return redirect(url_for('admin.admin_forgot_password'))
        
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        otp_input = request.form.get('otp', '').strip()
        if user.otp_created_at and safe_elapsed(user.otp_created_at) > 300:
            flash("Code expired. Please request a new one.", "danger")
            return redirect(url_for('admin.admin_forgot_password'))
                
        if user.otp_code == otp_input:
            session['admin_reset_verified_id'] = user.id
            flash("Code verified. Set your new password.", "success")
            return redirect(url_for('admin.admin_reset_password'))
        else:
            flash("Invalid code.", "danger")
            
    cooldown = 0
    if user.otp_created_at:
        cooldown = max(0, int(60 - safe_elapsed(user.otp_created_at)))
        
    return render_template('admin/verify_reset_otp.html', user=user, cooldown_remaining=cooldown)

@admin_bp.route('/resend-reset-otp/<int:user_id>', methods=['POST'])
def admin_resend_reset_otp(user_id):
    from flask import session
    if session.get('admin_reset_user_id') != user_id:
        return redirect(url_for('admin.admin_forgot_password'))
    
    user = User.query.get_or_404(user_id)
    if user.otp_created_at and safe_elapsed(user.otp_created_at) < 60:
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
    
    flash("New code sent.", "success")
    return redirect(url_for('admin.admin_verify_reset_otp', user_id=user.id))

@admin_bp.route('/reset-password', methods=['GET', 'POST'])
def admin_reset_password():
    from flask import session
    user_id = session.get('admin_reset_verified_id')
    if not user_id:
        return redirect(url_for('admin.admin_forgot_password'))
        
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        err = validate_password(new_password, confirm_password)
        if err:
            flash(err, "danger")
            return render_template('admin/reset_password.html')
            
        user.set_password(new_password)
        user.otp_code = None
        user.otp_created_at = None
        db.session.commit()
        
        session.pop('admin_reset_user_id', None)
        session.pop('admin_reset_verified_id', None)
        
        flash("Password updated successfully. Please log in.", "success")
        return redirect(url_for('admin.admin_login'))
        
    return render_template('admin/reset_password.html')

# ─── MAIN: OVERVIEW ─────────────────────────────────
@admin_bp.route('/')
@admin_bp.route('/overview')
@login_required
@admin_required
def overview():
    # Optimization: Aggregate queries to prevent high network latency to NeonDB (US-East)
    # Get user counts in 1 query instead of 2
    users_stats = db.session.query(User.role, User.status, func.count(User.id)).group_by(User.role, User.status).all()
    total_customers = sum(c for r, s, c in users_stats if r == 'USER')
    pending_users = sum(c for r, s, c in users_stats if r == 'USER' and s == 'PENDING')
    
    # Get reservation stats in 1 query instead of 3
    res_stats = db.session.query(Reservation.status, func.count(Reservation.id)).group_by(Reservation.status).all()
    total_reservations = sum(c for s, c in res_stats)
    pending_reservations = sum(c for s, c in res_stats if s == 'PENDING')
    confirmed_reservations = sum(c for s, c in res_stats if s == 'CONFIRMED')
    
    # Menu stats
    total_menu = MenuItem.query.count()
    low_stock_items = MenuItem.query.filter_by(is_available=False).limit(200).all()
    
    recent_reservations = Reservation.query.order_by(Reservation.created_at.desc()).limit(5).all()

    import json as _json
    today = date.today()

    # 1) & 2) Revenue and Orders Trend (Combined optimization)
    week_ago = today - timedelta(days=6)
    trend_stats = db.session.query(
        func.date(Order.created_at).label('d'),
        func.count(Order.id).label('cnt'),
        func.sum(Order.total_amount).label('rev')
    ).filter(func.date(Order.created_at) >= week_ago).group_by('d').all()
    
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

    # 3) Busy Times
    busy_hours_raw = db.session.query(func.extract('hour', Order.created_at).label('hr'), func.count(Order.id)).group_by('hr').order_by('hr').all()
    busy_map = {int(h): c for h, c in busy_hours_raw}
    busy_times_labels = [f'{h:02d}:00' for h in range(24)]
    busy_times_data = [busy_map.get(h, 0) for h in range(24)]

    # 4) Order Status Donut
    order_status_rows = db.session.query(Order.status, func.count(Order.id)).group_by(Order.status).all()
    order_status_labels = [r[0] for r in order_status_rows] if order_status_rows else ['No Data']
    order_status_data = [r[1] for r in order_status_rows] if order_status_rows else [1]

    # Compute total revenue
    total_revenue = float(db.session.query(func.coalesce(func.sum(Order.total_amount), 0)).scalar())

    return render_template('admin/overview.html',
        total_customers=total_customers,
        pending_users=pending_users,
        total_menu=total_menu,
        total_reservations=total_reservations,
        pending_reservations=pending_reservations,
        confirmed_reservations=confirmed_reservations,
        recent_reservations=recent_reservations,
        low_stock_items=low_stock_items,
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

# ─── STAFF PERFORMANCE ────────────────────────────────
@admin_bp.route('/staff-performance')
@login_required
@admin_required
def staff_performance():
    from models import InventoryLog
    import json as _json

    # ── CASHIER STATS ──
    cashiers = User.query.filter(db.func.upper(User.role).in_(['CASHIER', 'STAFF'])).all()
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
    riders = User.query.filter(db.func.upper(User.role) == 'RIDER').all()
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
    kitchen_staff = User.query.filter(db.func.upper(User.role) == 'KITCHEN').all()
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
    if current_user.role.upper() != 'ADMIN':
        flash("Access denied. Admin only.", "danger")
        return redirect(url_for('admin.overview'))

    import json as _json
    # Existing metrics
    total_customers = User.query.filter_by(role='USER').count()
    total_menu_items = MenuItem.query.count()
    
    # Reservation counts by type
    exclusive_count = Reservation.query.filter_by(booking_type='EXCLUSIVE').count()
    regular_count = Reservation.query.filter_by(booking_type='REGULAR').count()
    total_reservations = Reservation.query.count()
    
    # ── CHART DATA (Moved from overview) ──────────────────
    # Get PH today date for consistency with stored records
    today = get_ph_time().date()

    # 1) Revenue Trend (Last 7 Days) — Line chart
    revenue_trend_labels = []
    revenue_trend_data = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        revenue_trend_labels.append(d.strftime('%b %d'))
        day_rev = db.session.query(func.coalesce(func.sum(Order.total_amount), 0))\
            .filter(func.date(Order.created_at) == d).scalar()
        revenue_trend_data.append(float(day_rev))

    # 2) Order Status — Donut chart
    order_status_rows = db.session.query(Order.status, func.count(Order.id))\
        .group_by(Order.status).all()
    order_status_labels = [r[0] for r in order_status_rows] if order_status_rows else ['No Data']
    order_status_data = [r[1] for r in order_status_rows] if order_status_rows else [1]

    # 3) Daily Orders (Last 7 Days) — Bar chart
    daily_orders_labels = []
    daily_orders_data = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        daily_orders_labels.append(d.strftime('%b %d'))
        cnt = db.session.query(func.count(Order.id))\
            .filter(func.date(Order.created_at) == d).scalar()
        daily_orders_data.append(int(cnt or 0))

    # 4) Busy Times — Line chart (orders grouped by hour 0-23)
    busy_hours_raw = db.session.query(
        func.extract('hour', Order.created_at).label('hr'),
        func.count(Order.id)
    ).group_by('hr').order_by('hr').all()
    busy_map = {int(h): c for h, c in busy_hours_raw}
    busy_times_labels = [f'{h:02d}:00' for h in range(24)]
    busy_times_data = [busy_map.get(h, 0) for h in range(24)]

    # 5) Top 5 Best Selling Dishes — Horizontal bar chart
    top_dishes_raw = db.session.query(
        MenuItem.name,
        func.sum(OrderItem.quantity).label('total_qty')
    ).join(OrderItem, OrderItem.menu_item_id == MenuItem.id)\
     .group_by(MenuItem.name)\
     .order_by(func.sum(OrderItem.quantity).desc())\
     .limit(5).all()
    top_dishes_labels = [r[0] for r in top_dishes_raw] if top_dishes_raw else ['No Data']
    top_dishes_data = [int(r[1]) for r in top_dishes_raw] if top_dishes_raw else [0]

    # 6) Monthly Revenue — Area chart (last 6 months)
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
        rev = db.session.query(func.coalesce(func.sum(Order.total_amount), 0))\
            .filter(Order.created_at >= datetime.combine(month_start, datetime.min.time()),
                    Order.created_at < datetime.combine(month_end, datetime.min.time())).scalar()
        monthly_rev_data.append(float(rev))

    # 7) Customer Loyalty — Donut chart (repeat vs one-time buyers)
    order_counts_sub = db.session.query(
        Order.user_id,
        func.count(Order.id).label('order_count')
    ).group_by(Order.user_id).subquery()
    repeat_customers = db.session.query(func.count()).filter(order_counts_sub.c.order_count > 1).scalar() or 0
    onetime_customers = db.session.query(func.count()).filter(order_counts_sub.c.order_count == 1).scalar() or 0
    loyalty_labels = ['Repeat Customers', 'One-time Customers']
    loyalty_data = [repeat_customers, onetime_customers]
    if repeat_customers == 0 and onetime_customers == 0:
        loyalty_labels = ['No Orders Yet']
        loyalty_data = [1]

    # Compute total revenue
    total_revenue_val = db.session.query(func.coalesce(func.sum(Order.total_amount), 0)).scalar()
    
    # 8) Advanced Analytics: Profit & Loss (P&L)
    # COGS = Sum (Ingredient.cost_per_unit * recipe.quantity_needed * qty_sold)
    # Using select_from to anchor the query at OrderItem and avoid cross-join
    cogs_query = db.session.query(
        func.sum(OrderItem.quantity * MenuItemIngredient.quantity_needed * Ingredient.cost_per_unit)
    ).select_from(OrderItem)\
     .join(Order, Order.id == OrderItem.order_id)\
     .join(MenuItem, MenuItem.id == OrderItem.menu_item_id)\
     .join(MenuItemIngredient, MenuItemIngredient.menu_item_id == MenuItem.id)\
     .join(Ingredient, Ingredient.id == MenuItemIngredient.ingredient_id)\
     .filter(Order.status == 'COMPLETED')

    total_cogs = float(cogs_query.scalar() or 0.0)
    net_profit = float(total_revenue_val) - total_cogs
    
    # 9) Sales Forecast (Next 7 Days)
    # Simple moving average of the last 14 days
    last_14_days_rev = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        rev = db.session.query(func.coalesce(func.sum(Order.total_amount), 0))\
            .filter(func.date(Order.created_at) == d).scalar()
        last_14_days_rev.append(float(rev))
    
    avg_daily_rev = sum(last_14_days_rev) / 14 if last_14_days_rev else 0
    forecast_labels = []
    forecast_data = []
    for i in range(1, 8):
        future_date = today + timedelta(days=i)
        forecast_labels.append(future_date.strftime('%b %d'))
        # Adding a small randomness/trend factor? No, keep it simple for now
        forecast_data.append(round(avg_daily_rev, 2))

    return render_template('admin/analytics.html',
        total_customers=total_customers,
        total_menu_items=total_menu_items,
        exclusive_count=exclusive_count,
        regular_count=regular_count,
        total_reservations=total_reservations,
        total_revenue=float(total_revenue_val),
        total_cogs=total_cogs,
        net_profit=net_profit,
        forecast_labels=_json.dumps(forecast_labels),
        forecast_data=_json.dumps(forecast_data),
        revenue_trend_labels=_json.dumps(revenue_trend_labels),
        revenue_trend_data=_json.dumps(revenue_trend_data),
        order_status_labels=_json.dumps(order_status_labels),
        order_status_data=_json.dumps(order_status_data),
        daily_orders_labels=_json.dumps(daily_orders_labels),
        daily_orders_data=_json.dumps(daily_orders_data),
        busy_times_labels=_json.dumps(busy_times_labels),
        busy_times_data=_json.dumps(busy_times_data),
        top_dishes_labels=_json.dumps(top_dishes_labels),
        top_dishes_data=_json.dumps(top_dishes_data),
        monthly_rev_labels=_json.dumps(monthly_rev_labels),
        monthly_rev_data=_json.dumps(monthly_rev_data),
        loyalty_labels=_json.dumps(loyalty_labels),
        loyalty_data=_json.dumps(loyalty_data)
    )

MENU_CATEGORIES = [
    "All Day Breakfast",
    "Best Sellers",
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
@admin_required
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
@admin_required
def menu_item_json(item_id):
    if current_user.role.upper() != 'ADMIN':
        return jsonify({'success': False, 'message': 'Admin only.'}), 403

    item = MenuItem.query.get_or_404(item_id)
    return jsonify({
        'id': item.id,
        'name': item.name,
        'description': item.description or '',
        'price': float(item.price or 0),
        'category': item.category,
        'image_url': item.image_url or '',
        'is_available': bool(item.is_available),
    })

@admin_bp.route('/menu/items', methods=['GET'])
@login_required
@admin_required
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
                MenuItem.name,
                MenuItem.description,
                MenuItem.price,
                MenuItem.category,
                MenuItem.image_url,
                MenuItem.is_available,
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
            'name': i.name,
            'description': i.description or '',
            'price': float(i.price or 0),
            'category': i.category,
            'image_url': i.image_url or '',
            'is_available': bool(i.is_available),
        } for i in items],
    })

@admin_bp.route('/menu/add', methods=['POST'])
@login_required
@admin_required
def menu_add():
    if current_user.role.upper() != 'ADMIN':
        flash("Access denied. Admin only.", "danger")
        return redirect(url_for('admin.menu'))

    name = (request.form.get('name') or '').strip()[:50]
    description = request.form.get('description', '')[:255]
    image_url = (request.form.get('image_url') or '')[:255]
    category = request.form.get('category', '')

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
        item = MenuItem(
            name=name,
            description=description,
            price=price,
            category=category,
            image_url=image_url,
            is_available=False  # Automatically false until ingredients are assigned
        )
        db.session.add(item)
        db.session.commit()
        log_audit('CREATE', 'MenuItem', item.id, f'Added new menu item: {item.name}')
        flash("Menu item added successfully.", "success")
        return redirect(url_for('admin.menu', category=item.category))
    except Exception as e:
        db.session.rollback()
        flash(f"Error adding item: {str(e)}", "danger")
        return redirect(url_for('admin.menu'))

@admin_bp.route('/menu/edit/<int:item_id>', methods=['POST'])
@login_required
@admin_required
def menu_edit(item_id):
    if current_user.role.upper() != 'ADMIN':
        flash("Access denied. Admin only.", "danger")
        return redirect(url_for('admin.menu'))

    item = MenuItem.query.get_or_404(item_id)

    name = (request.form.get('name') or '').strip()[:50]
    description = request.form.get('description', '')[:255]
    image_url = (request.form.get('image_url') or '')[:255]
    category = request.form.get('category', '')

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
        item.image_url = image_url
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
@admin_required
def menu_delete(item_id):
    if current_user.role.upper() != 'ADMIN':
        flash("Access denied. Admin only.", "danger")
        return redirect(url_for('admin.menu'))

    item = MenuItem.query.get_or_404(item_id)
    category = item.category
    item.is_deleted = True
    db.session.commit()
    log_audit('DELETE', 'MenuItem', item_id, f'Trashed menu item: {item.name}')
    flash("Menu item moved to trash.", "success")
    return redirect(url_for('admin.menu', category=category))

@admin_bp.route('/menu/trash')
@login_required
@admin_required
def menu_trash():
    """View items that have been moved to trash."""
    trashed_items = MenuItem.query.filter_by(is_deleted=True).order_by(MenuItem.created_at.desc()).all()
    return render_template('admin/menu_trash.html', items=trashed_items)

@admin_bp.route('/menu/restore/<int:item_id>', methods=['POST'])
@login_required
@admin_required
def menu_restore(item_id):
    """Restore a trashed menu item."""
    if current_user.role.upper() != 'ADMIN':
        flash("Access denied.", "danger")
        return redirect(url_for('admin.menu_trash'))
        
    item = MenuItem.query.get_or_404(item_id)
    item.is_deleted = False
    db.session.commit()
    log_audit('RESTORE', 'MenuItem', item_id, f'Restored menu item: {item.name}')
    flash(f"Restored '{item.name}' successfully.", "success")
    return redirect(url_for('admin.menu_trash'))

# ─── MANAGEMENT: ACCOUNT APPROVALS ──────────────────
@admin_bp.route('/approvals')
@login_required
@admin_required
def approvals():
    pending = User.query.filter_by(status='PENDING', role='USER', is_verified=True).limit(300).all()
    return render_template('admin/approvals.html', pending=pending)

@admin_bp.route('/approve/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
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
    
    flash(f"User {user.username} approved.", "success")
    return redirect(url_for('admin.approvals'))

@admin_bp.route('/reject/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def reject_user(user_id):
    user = User.query.get_or_404(user_id)
    user.status = 'REJECTED'
    db.session.commit()
    _create_web_notification(user.id, 'Account Update', 'Your account registration was not approved. Please contact us for more information.', 'SYSTEM')
    flash(f"User {user.username} rejected.", "warning")
    return redirect(url_for('admin.approvals'))

# ─── MANAGEMENT: USER MANAGEMENT ────────────────────
@admin_bp.route('/users')
@login_required
@admin_required
def users():
    if current_user.role.upper() != 'ADMIN':
        flash("Access denied. Admin only.", "danger")
        return redirect(url_for('admin.overview'))

    role_filter = request.args.get('role', 'ALL')
    page = request.args.get('page', 1, type=int)
    
    query = User.query
    if role_filter != 'ALL':
        query = query.filter(func.upper(User.role) == role_filter.upper())
    
    pagination = query.order_by(User.id).paginate(page=page, per_page=30, error_out=False)
    return render_template('admin/users.html', users=pagination, role_filter=role_filter)

@admin_bp.route('/users/update-role/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def update_user_role(user_id):
    if current_user.role.upper() != 'ADMIN':
        flash("Access denied. Admin only.", "danger")
        return redirect(url_for('admin.overview'))

    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    user.role = new_role
    db.session.commit()
    flash(f"Role updated for {user.username}.", "success")
    return redirect(url_for('admin.users'))

@admin_bp.route('/users/broadcast', methods=['POST'])
@login_required
@admin_required
def broadcast():
    if current_user.role.upper() != 'ADMIN':
        flash("Access denied. Admin only.", "danger")
        return redirect(url_for('admin.overview'))

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
    if current_user.role.upper() != 'ADMIN':
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
@admin_required
def reservations():
    status_filter = request.args.get('status', 'ALL')
    page = request.args.get('page', 1, type=int)
    
    query = Reservation.query
    if status_filter != 'ALL':
        query = query.filter_by(status=status_filter)
    
    pagination = query.order_by(Reservation.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/reservations.html', reservations=pagination, status_filter=status_filter)

@admin_bp.route('/reservations/update/<int:res_id>', methods=['POST'])
@login_required
@admin_required
def update_reservation(res_id):
    res = Reservation.query.get_or_404(res_id)
    new_status = request.form.get('status')
    table_number = request.form.get('table_number')
    
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
        _create_web_notification(res.user_id, f'Reservation {new_status.capitalize()}', status_msgs[new_status], 'RESERVATION')
    
    flash(f"Reservation #{res.id} updated to {new_status}.", "success")
    return redirect(url_for('admin.reservations'))

# ─── INVENTORY ───────────────────────────────────
@admin_bp.route('/inventory')
@login_required
@admin_required
def inventory():
    page_items = request.args.get('page_items', 1, type=int)
    page_ingredients = request.args.get('page_ingredients', 1, type=int)
    
    # Counts using SQL instead of Python loops
    total_items = MenuItem.query.count()
    out_of_stock = MenuItem.query.filter_by(is_available=False).count()
    total_ingredients = Ingredient.query.count()
    low_stock_count = db.session.query(func.count(Ingredient.id)).filter(Ingredient.stock_qty <= Ingredient.reorder_level).scalar()
    
    today = date.today()
    seven_days_later = today + timedelta(days=7)
    expiring_soon_count = db.session.query(func.count(Ingredient.id)).filter(
        Ingredient.expiration_date.between(today, seven_days_later)
    ).scalar()
    
    # Filters
    q_ing = request.args.get('q_ing', '').strip()

    # Fetch all ingredients
    ingredients_query = Ingredient.query
    if q_ing:
        ingredients_query = ingredients_query.filter(Ingredient.name.ilike(f'%{q_ing}%'))

    ingredients_query = ingredients_query.order_by(Ingredient.category, Ingredient.name)
    all_ingredients = ingredients_query.all()
    
    # ⚡ OPTIMIZED: Fetch all mappings in a single query instead of a loop
    ing_ids = [ing.id for ing in all_ingredients]
    mappings = (
        db.session.query(MenuItemIngredient.ingredient_id, MenuItem.category)
        .join(MenuItem, MenuItem.id == MenuItemIngredient.menu_item_id)
        .filter(MenuItemIngredient.ingredient_id.in_(ing_ids))
        .distinct()
        .all()
    )
    from collections import defaultdict
    cats_by_ing = defaultdict(list)
    for i_id, cat in mappings:
        cats_by_ing[i_id].append(cat)
    
    for ing in all_ingredients:
        ing.mapped_menu_categories = cats_by_ing.get(ing.id, [])

    # Get unique menu categories for the dropdown
    menu_categories = [r[0] for r in db.session.query(MenuItem.category).filter(MenuItem.is_deleted == False).distinct().order_by(MenuItem.category).all()]

    # Fetch all Menu Items for grouping
    all_menu_items = MenuItem.query.filter_by(is_deleted=False).order_by(MenuItem.category, MenuItem.name).all()
    
    # Group menu items by category (ensure sorted for groupby)
    grouped_items = {}
    for category, group in groupby(all_menu_items, lambda x: x.category or 'General'):
        grouped_items[category] = list(group)
    
    # Group ingredients by category
    grouped_ingredients = {}
    for category, group in groupby(all_ingredients, lambda x: x.category or 'General'):
        grouped_ingredients[category] = list(group)
    
    # Logic for ingredients pagination
    ingredients_paginated = ingredients_query.paginate(page=page_ingredients, per_page=20)
    
    # Fetch suppliers and map their menu category specialties (optimized)
    all_suppliers = _get_suppliers_cached()
    all_ingredients_raw = _get_all_ingredients_raw_cached()
    
    # ⚡ OPTIMIZED: Bulk fetch supplier specialties
    sup_ids = [s.id for s in all_suppliers]
    sup_mappings = (
        db.session.query(Ingredient.supplier_id, MenuItem.category)
        .join(MenuItemIngredient, MenuItemIngredient.ingredient_id == Ingredient.id)
        .join(MenuItem, MenuItem.id == MenuItemIngredient.menu_item_id)
        .filter(Ingredient.supplier_id.in_(sup_ids))
        .distinct()
        .all()
    )
    cats_by_sup = defaultdict(list)
    for s_id, cat in sup_mappings:
        cats_by_sup[s_id].append(cat)

    for sup in all_suppliers:
        sup.supplied_menu_categories = cats_by_sup.get(sup.id, [])

    return render_template('admin/inventory.html', 
        grouped_items=grouped_items, 
        total_items=total_items, 
        out_of_stock=out_of_stock, 
        ingredients=ingredients_paginated,
        grouped_ingredients=grouped_ingredients,
        suppliers=all_suppliers, 
        menu_categories=menu_categories,
        low_stock_count=low_stock_count,
        expiring_soon_count=expiring_soon_count,
        total_ingredients=total_ingredients,
        all_ingredients_raw=all_ingredients_raw,
        today=today)

@admin_bp.route('/inventory/generate-po')
@login_required
@admin_required
def generate_purchase_order():
    # Filter in SQL (fast) instead of loading all ingredients into Python
    low_stock = (
        Ingredient.query.options(selectinload(Ingredient.supplier))
        .filter(Ingredient.stock_qty <= Ingredient.reorder_level)
        .order_by(Ingredient.name.asc())
        .all()
    )
    
    if not low_stock:
        flash("No ingredients are currently low on stock.", "info")
        return redirect(url_for('admin.inventory'))
        
    from fpdf import FPDF
    import io
    from datetime import datetime
    
    class PDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 15)
            self.cell(0, 10, 'Le Maison Yelo Lane - Purchase Order', 0, 1, 'C')
            self.set_font('Arial', '', 10)
            self.cell(0, 10, f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M")}', 0, 1, 'C')
            self.ln(10)
            
        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 12)
    
    # Group by supplier
    suppliers = {}
    for ing in low_stock:
        s_name = ing.supplier.name if ing.supplier else "No Supplier Assigned"
        if s_name not in suppliers:
            suppliers[s_name] = []
        suppliers[s_name].append(ing)
        
    for s_name, items in suppliers.items():
        pdf.set_text_color(139, 69, 19) # Brown
        pdf.cell(0, 10, f'Supplier: {s_name}', 0, 1)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(80, 8, 'Ingredient', 1)
        pdf.cell(40, 8, 'Current Stock', 1)
        pdf.cell(40, 8, 'Reorder Level', 1)
        pdf.cell(30, 8, 'UnitCost', 1)
        pdf.ln()
        
        pdf.set_font('Arial', '', 10)
        for ing in items:
            pdf.cell(80, 8, ing.name, 1)
            pdf.cell(40, 8, f"{ing.stock_qty} {ing.unit}", 1)
            pdf.cell(40, 8, f"{ing.reorder_level} {ing.unit}", 1)
            pdf.cell(30, 8, f"P{ing.cost_per_unit}", 1)
            pdf.ln()
        pdf.ln(5)
        
    output = io.BytesIO()
    pdf_out = pdf.output(dest='S')
    output.write(pdf_out)
    output.seek(0)
    
    from flask import send_file
    return send_file(
        output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'Purchase_Order_{datetime.now().strftime("%Y%m%d")}.pdf'
    )

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
    return redirect(url_for('admin.inventory'))

# ─── KITCHEN VIEW ─────────────────────────────────────
@admin_bp.route('/kitchen')
@login_required
@admin_required
def kitchen_view():
    status_filter = request.args.get('status', 'ACTIVE')
    base = (
        Order.query.options(
            selectinload(Order.items).selectinload(OrderItem.menu_item),
            selectinload(Order.reservation),
            selectinload(Order.user),
        )
    )
    if status_filter == 'ACTIVE':
        active_orders = base.filter(
            Order.status.in_(['PENDING', 'PREPARING'])
        ).order_by(Order.created_at.asc()).limit(80).all()
    elif status_filter == 'COMPLETED':
        active_orders = base.filter_by(status='COMPLETED').order_by(Order.created_at.desc()).limit(40).all()
    elif status_filter == 'CANCELLED':
        active_orders = base.filter_by(status='CANCELLED').order_by(Order.created_at.desc()).limit(40).all()
    else:
        active_orders = base.filter_by(status=status_filter).order_by(Order.created_at.asc()).limit(80).all()
    
    # Counts for badges
    pending_count = Order.query.filter_by(status='PENDING').count()
    preparing_count = Order.query.filter_by(status='PREPARING').count()
    completed_count = Order.query.filter_by(status='COMPLETED').count()
    cancelled_count = Order.query.filter_by(status='CANCELLED').count()
    
    # Calculate throughput metrics (Average Prep Time today)
    from sqlalchemy import func
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    # Compute avg prep time in SQL (avoid loading all rows)
    avg_prep_time = 0
    avg_seconds = db.session.query(
        func.avg(func.extract('epoch', Order.prep_end_at - Order.prep_start_at))
    ).filter(
        Order.status == 'COMPLETED',
        Order.prep_end_at >= today_start,
        Order.prep_start_at.isnot(None),
        Order.prep_end_at.isnot(None),
    ).scalar()
    if avg_seconds:
        avg_prep_time = round((float(avg_seconds) / 60), 1)

    ph_now = get_ph_time()

    # 1. Separate Active Orders
    asap_orders = []
    for order in active_orders:
        if not order.reservation:
            asap_orders.append(order)
        else:
            # Check if reservation is within 1 hour
            res = order.reservation
            if res.date and res.time:
                try:
                    res_dt = datetime.combine(res.date, res.time)
                    # Handle potential timezone mismatch
                    if res_dt.tzinfo is not None: res_dt = res_dt.replace(tzinfo=None)
                    
                    diff = (res_dt - ph_now.replace(tzinfo=None)).total_seconds() / 60
                    if diff <= 60:
                        asap_orders.append(order)
                except Exception:
                    asap_orders.append(order) # Show anyway if comparison fails

    # 2. Aggregation for Prep Summary
    item_data = {}
    for order in asap_orders:
        for item in order.items:
            if not item.menu_item: continue
            key = item.menu_item.name
            cat = item.menu_item.category or 'Other'
            if key in item_data:
                item_data[key].update({'qty': item_data[key]['qty'] + item.quantity})
            else:
                item_data[key] = {'qty': item.quantity, 'cat': cat}

    # 3. Categorize into Stations
    hot_kitchen, cold_kitchen, bar_station = [], [], []
    for name, info in item_data.items():
        cat_lower = info['cat'].lower()
        station_item = {'name': name, 'qty': info['qty']}
        
        if any(kw in cat_lower for kw in ['drink', 'beverage', 'coffee', 'shake', 'juice', 'tea']):
            bar_station.append(station_item)
        elif any(kw in cat_lower for kw in ['dessert', 'cake', 'pastry', 'sweet', 'cheesecake', 'waffle']):
            cold_kitchen.append(station_item)
        else:
            hot_kitchen.append(station_item)

    # 4. Get Kitchen-side Inventory for display
    # Show ingredients that are low in kitchen OR are used in today's menu categories
    kitchen_ingredients = Ingredient.query.filter(
        (Ingredient.kitchen_qty < Ingredient.reorder_level / 2) | # Alert level
        (Ingredient.kitchen_qty > 0)
    ).order_by(Ingredient.kitchen_qty.asc()).limit(15).all()

    # Handle partial request (for soft refresh)
    if request.args.get('partial'):
        return render_template('admin/kitchen_partial.html', 
            orders=active_orders, hot_kitchen=hot_kitchen, cold_kitchen=cold_kitchen,
            bar_station=bar_station, item_count=len(item_data), status_filter=status_filter,
            pending_count=pending_count, preparing_count=preparing_count,
            completed_count=completed_count, cancelled_count=cancelled_count,
            avg_prep_time=avg_prep_time, ph_now=ph_now,
            kitchen_ingredients=kitchen_ingredients
        )

    return render_template('admin/kitchen.html', 
        orders=active_orders,
        hot_kitchen=hot_kitchen,
        cold_kitchen=cold_kitchen,
        bar_station=bar_station,
        item_count=len(item_data),
        status_filter=status_filter,
        pending_count=pending_count,
        preparing_count=preparing_count,
        completed_count=completed_count,
        cancelled_count=cancelled_count,
        avg_prep_time=avg_prep_time,
        ph_now=ph_now,
        kitchen_ingredients=kitchen_ingredients
    )

@admin_bp.route('/kitchen/pantry')
@login_required
@admin_required
def kitchen_pantry():
    """Independent view for kitchen staff to monitor all on-hand stocks and alerts."""
    ingredients = Ingredient.query.order_by(Ingredient.category, Ingredient.name).all()
    
    # Group ingredients by category for the UI
    grouped_ingredients = {}
    
    for category, group in groupby(ingredients, lambda x: x.category or 'General'):
        grouped_ingredients[category] = list(group)
        
    return render_template('admin/kitchen_pantry.html', grouped_ingredients=grouped_ingredients, today=date.today())

@admin_bp.route('/kitchen/pantry/update/<int:ing_id>', methods=['POST'])
@login_required
@admin_required
def kitchen_pantry_update(ing_id):
    """Temporary dev endpoint to instantly set kitchen stock & sync menu items."""
    ingredient = Ingredient.query.get_or_404(ing_id)
    try:
        new_qty = float(request.form.get('kitchen_qty', 0))
        ingredient.kitchen_qty = max(0, new_qty)
        _sync_single_ingredient_availability(ingredient.id)
        db.session.commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'new_qty': new_qty})
        flash(f'Kitchen stock for {ingredient.name} updated to {new_qty}.', 'success')
    except ValueError:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Invalid quantity.'})
        flash('Invalid quantity.', 'danger')
        
    return redirect(url_for('admin.kitchen_pantry'))

@admin_bp.route('/kitchen/api/orders')
@login_required
@admin_required
def kitchen_api_orders():
    """API endpoint for auto-refresh of kitchen orders"""
    status_filter = request.args.get('status', 'ACTIVE')
    ph_now = get_ph_time()
    
    # Base query
    base = (
        Order.query.options(
            selectinload(Order.items).selectinload(OrderItem.menu_item),
            selectinload(Order.reservation),
            selectinload(Order.user),
        )
    )
    if status_filter == 'ACTIVE':
        active_orders = base.filter(Order.status.in_(['PENDING', 'PREPARING']))
    else:
        active_orders = base.filter_by(status=status_filter)
        
    active_orders = active_orders.order_by(Order.created_at.asc()).limit(80).all()
    
    # Counts for badges
    stats = {
        'pending': Order.query.filter_by(status='PENDING').count(),
        'preparing': Order.query.filter_by(status='PREPARING').count(),
        'completed': Order.query.filter_by(status='COMPLETED').count(),
        'cancelled': Order.query.filter_by(status='CANCELLED').count()
    }
    
    # Station aggregation (Only for ACTIVE filter)
    hot_kitchen, cold_kitchen, bar_station = [], [], []
    item_data = {}
    
    orders_data = []
    for order in active_orders:
        # Check ASAP logic for station summary
        is_asap = True
        if order.reservation and order.reservation.date and order.reservation.time:
            try:
                res_dt = datetime.combine(order.reservation.date, order.reservation.time)
                diff = (res_dt - ph_now.replace(tzinfo=None)).total_seconds() / 60
                if diff > 60: is_asap = False
            except: pass
            
        items_list = []
        for item in order.items:
            items_list.append({'name': item.menu_item.name, 'qty': item.quantity})
            
            if is_asap and status_filter == 'ACTIVE':
                name = item.menu_item.name
                cat = (item.menu_item.category or 'Other').lower()
                if name in item_data:
                    item_data[name]['qty'] += item.quantity
                else:
                    item_data[name] = {'qty': item.quantity, 'cat': cat}
        
        customer = 'Walk-in'
        if order.user: customer = f"{order.user.first_name} {order.user.last_name}"
        elif order.customer_name: customer = order.customer_name
        
        orders_data.append({
            'id': order.id,
            'customer': customer,
            'status': order.status,
            'dining_option': order.dining_option,
            'notes': order.notes or '',
            'items': items_list,
            'is_reservation': bool(order.reservation),
            'res_time': order.reservation.time.strftime('%I:%M %p') if (order.reservation and order.reservation.time) else None,
            'guest_count': order.reservation.guest_count if order.reservation else None,
            'table': order.reservation.table_number if order.reservation else None,
            'created_at_utc': order.created_at.isoformat() + 'Z',
            'created_at_str': order.created_at.strftime('%I:%M %p')
        })

    # Final station categorization
    for name, info in item_data.items():
        s_item = {'name': name, 'qty': info['qty']}
        c = info['cat']
        if any(kw in c for kw in ['drink', 'beverage', 'coffee', 'shake', 'juice', 'tea']):
            bar_station.append(s_item)
        elif any(kw in c for kw in ['dessert', 'cake', 'pastry', 'sweet', 'cheesecake', 'waffle']):
            cold_kitchen.append(s_item)
        else:
            hot_kitchen.append(s_item)

    return jsonify({
        'orders': orders_data,
        'stats': stats,
        'stations': {
            'hot': hot_kitchen,
            'cold': cold_kitchen,
            'bar': bar_station
        },
        'status_filter': status_filter
    })

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
        notes = request.form.get('notes', '').strip()
        payment_method = request.form.get('payment_method', 'COUNTER')

        # Parse items from form
        item_ids = request.form.getlist('item_id[]')
        quantities = request.form.getlist('quantity[]')

        if not item_ids:
            flash("Please add at least one item to the order.", "danger")
            return redirect(url_for('admin.walkin_order'))

        items_data = [{'menu_item_id': int(id), 'quantity': int(qty)} for id, qty in zip(item_ids, quantities)]
        from routes.orders import validate_order
        is_valid, msg, status_override = validate_order(items_data, dining_option, payment_method, is_pos=True)
        
        if not is_valid:
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

        order = Order(
            user_id=None,
            customer_name=customer_name,
            total_amount=total,
            status=status_override or 'PENDING',
            payment_status='PAID' if payment_method == 'COUNTER' else 'UNPAID',
            payment_method=payment_method,
            amount_tendered=amount_tendered,
            change_amount=change_amount,
            dining_option=dining_option,
            notes=notes,
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
                    'success_redirect_url': url_for('admin.orders', _external=True),
                    'failure_redirect_url': url_for('admin.orders', _external=True),
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
        
        flash("Walk-in order submitted successfully!", "success")
        return redirect(url_for('admin.orders'))
    except Exception as e:
        db.session.rollback()
        print(f"WALKIN SUBMIT ERROR: {str(e)}")
        flash(f"System Error: {str(e)}", "danger")
        return redirect(url_for('admin.walkin_order'))
    return redirect(url_for('admin.orders'))

# ─── DELIVERIES ───────────────────────────────────────
@admin_bp.route('/deliveries')
@login_required
@admin_required
def deliveries():
    status_filter = request.args.get('status', 'ALL')
    page = request.args.get('page', 1, type=int)
    
    query = Order.query.filter_by(dining_option='DELIVERY')
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
@admin_required
def orders():
    status_filter = request.args.get('status', 'ALL')
    page = request.args.get('page', 1, type=int)
    
    query = Order.query
    if status_filter != 'ALL':
        query = query.filter_by(status=status_filter)
        
    pagination = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
        
    # Optimized Stats Calculation via SQL Group By
    today = get_ph_time().date()
    # 1 query for all today's stats
    today_stats_rows = db.session.query(
        Order.status, 
        Order.payment_status,
        Order.payment_method,
        func.count(Order.id),
        func.sum(Order.total_amount)
    ).filter(func.date(Order.created_at) == today).group_by(Order.status, Order.payment_status, Order.payment_method).all()
    
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
@admin_required
def billing():
    status_filter = request.args.get('status', 'UNPAID')
    page = request.args.get('page', 1, type=int)
    
    query = Order.query
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
    ).filter(func.date(Order.created_at) == today).group_by(Order.payment_status, Order.payment_method).all()
    
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
        # Batch fetch all recipe rows for items in this order.
        from collections import defaultdict

        order_items = list(order.items)
        menu_item_ids = list({oi.menu_item_id for oi in order_items if oi.menu_item_id})
        if menu_item_ids:
            recipe_rows = MenuItemIngredient.query.filter(MenuItemIngredient.menu_item_id.in_(menu_item_ids)).all()

            recipes_by_menu_item_id = defaultdict(list)
            ingredient_ids = set()
            for rr in recipe_rows:
                recipes_by_menu_item_id[rr.menu_item_id].append(rr)
                ingredient_ids.add(rr.ingredient_id)

            # Compute total deductions per ingredient across the whole order.
            deduction_by_ingredient_id = defaultdict(float)
            for oi in order_items:
                for rr in recipes_by_menu_item_id.get(oi.menu_item_id, []):
                    deduction_by_ingredient_id[rr.ingredient_id] += float(rr.quantity_needed) * oi.quantity

            # Fetch ingredients once.
            ingredients = (
                Ingredient.query.filter(Ingredient.id.in_(ingredient_ids))
                .all()
            )
            ingredients_by_id = {ing.id: ing for ing in ingredients}

            new_stock_by_ingredient_id = {}
            for ing_id, deduction in deduction_by_ingredient_id.items():
                ing = ingredients_by_id.get(ing_id)
                if not ing:
                    continue
                new_stock = max(0.0, float(ing.stock_qty) - float(deduction))
                ing.stock_qty = new_stock
                new_stock_by_ingredient_id[ing_id] = new_stock

            # Disable menu items that now lack required ingredients (using final stock values).
            if new_stock_by_ingredient_id:
                links = MenuItemIngredient.query.filter(
                    MenuItemIngredient.ingredient_id.in_(list(new_stock_by_ingredient_id.keys()))
                ).all()
                menu_item_ids_to_disable = set()
                for link in links:
                    new_stock = new_stock_by_ingredient_id.get(link.ingredient_id)
                    if new_stock is None:
                        continue
                    if new_stock < float(link.quantity_needed):
                        menu_item_ids_to_disable.add(link.menu_item_id)

                if menu_item_ids_to_disable:
                    MenuItem.query.filter(
                        MenuItem.id.in_(menu_item_ids_to_disable),
                        MenuItem.is_available == True,
                    ).update({'is_available': False}, synchronize_session=False)
    
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
            _create_web_notification(order.user_id, f'Order {new_status.capitalize()}', order_status_msgs[new_status], 'ORDER')
    
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
    order = Order.query.get_or_404(order_id)
    new_payment_status = request.form.get('payment_status')
    if new_payment_status in ['PAID', 'UNPAID']:
        order.payment_status = new_payment_status
        db.session.commit()
        flash(f"Order #{order.id} payment status marked as {new_payment_status}.", "success")
    return redirect(url_for('admin.orders'))

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
        new_order = Order(
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
    status_filter = request.args.get('status', 'PENDING')
    limit = request.args.get('limit', 250, type=int)
    limit = max(1, min(limit, 500))
    if status_filter == 'ALL':
        all_reviews = Review.query.options(selectinload(Review.user)).order_by(Review.created_at.desc()).limit(limit).all()
    else:
        all_reviews = Review.query.options(selectinload(Review.user)).filter_by(status=status_filter).order_by(Review.created_at.desc()).limit(limit).all()
        
    # AI Sentiment Analysis (Dynamic Calculation to avoid DB Migrations)
    positive_words = ['good', 'great', 'excellent', 'amazing', 'best', 'delicious', 'love', 'perfect', 'nice', 'awesome', 'sarap', 'mabilis', 'ayos', 'sulit', 'outstanding', 'fantastic', 'superb', 'yummy', 'tasty']
    negative_words = ['bad', 'terrible', 'awful', 'worst', 'horrible', 'poor', 'slow', 'cold', 'disappointing', 'hate', 'pangit', 'panget', 'mabagal', 'matagal', 'bland', 'salty', 'late', 'matabang', 'maalat']

    # Prevent unbounded growth in long-running deployments.
    if len(_REVIEW_SENTIMENT_CACHE) > 2500:
        _REVIEW_SENTIMENT_CACHE.clear()

    # Speed optimization: compute sentiment for missing reviews in background thread.
    # This prevents /admin/reviews from timing out when there are many new/unique comments.
    now_mono = time.monotonic()

    def _compute_sentiment(text: str, rating: int):
        t = (text or '').lower()
        if not t:
            return ("NEUTRAL", "😐", "secondary")
        pos_count = sum(t.count(word) for word in positive_words)
        neg_count = sum(t.count(word) for word in negative_words)

        # Adjust weight based on star rating
        if rating >= 4:
            pos_count += 2
        elif rating <= 2:
            neg_count += 2

        if pos_count > neg_count:
            return ("POSITIVE", "😊", "success")
        if neg_count > pos_count:
            return ("NEGATIVE", "😠", "danger")
        # Tie-break with rating
        if rating >= 4:
            return ("POSITIVE", "😊", "success")
        if rating <= 2:
            return ("NEGATIVE", "😠", "danger")
        return ("NEUTRAL", "😐", "secondary")

    # Protect cache dict in case multiple requests compute at once.
    import threading as _threading
    if not hasattr(reviews, "_sentiment_lock"):
        reviews._sentiment_lock = _threading.Lock()

    jobs = []  # (cache_key, comment_text, rating)
    for review in all_reviews:
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
            # Default fast placeholder; background thread will fill the cache.
            review.ai_sentiment = "NEUTRAL"
            review.ai_sentiment_icon = "😐"
            review.ai_sentiment_color = "secondary"
            jobs.append((cache_key, comment_text, review.rating))

    if jobs:
        # Copy jobs to avoid accidental mutation.
        jobs_copy = list(jobs)

        def _worker(jobs_local):
            mono = time.monotonic()
            try:
                for cache_key, comment_text, rating in jobs_local:
                    sentiment, icon, color = _compute_sentiment(comment_text, rating)
                    with reviews._sentiment_lock:
                        _REVIEW_SENTIMENT_CACHE[cache_key] = (mono, (sentiment, icon, color))
            except Exception as e:
                print(f"Sentiment background worker failed: {e}")

        threading.Thread(target=_worker, args=(jobs_copy,), daemon=True).start()

    return render_template('admin/reviews.html', reviews=all_reviews, status_filter=status_filter)

@admin_bp.route('/reviews/update/<int:review_id>', methods=['POST'])
@login_required
@admin_required
def update_review(review_id):
    review = Review.query.get_or_404(review_id)
    new_status = request.form.get('status')
    review.status = new_status
    db.session.commit()
    flash(f"Review from {review.user.first_name} marked as {new_status}.", "success")
    return redirect(url_for('admin.reviews'))

# ─── SYSTEM: SETTINGS ────────────────────────────────
from utils import load_site_settings, save_site_settings
@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    site_settings = load_site_settings()
    if request.method == 'POST' and current_user.role.upper() == 'ADMIN':
        # Handle form submission for homepage content
        # Update Hero 2
        site_settings['hero2']['title1'] = request.form.get('hero2_title1', site_settings['hero2']['title1'])
        site_settings['hero2']['title2'] = request.form.get('hero2_title2', site_settings['hero2']['title2'])
        site_settings['hero2']['description'] = request.form.get('hero2_desc', site_settings['hero2']['description'])
        site_settings['hero2']['image_url'] = request.form.get('hero2_img', site_settings['hero2']['image_url'])
        
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

        if save_site_settings(site_settings):
            flash("Homepage content updated successfully.", "success")
        else:
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

    # --- VALIDATIONS ---
    if not all([first_name, last_name, username, email, phone_number]):
        flash("All profile fields are required.", "danger")
        return redirect(url_for('admin.settings'))
    
    # Validate Names
    for name, label in [(first_name, 'First Name'), (last_name, 'Last Name')]:
        err = validate_name(name, label)
        if err: flash(err, "danger"); return redirect(url_for('admin.settings'))
    if middle_name:
        err = validate_name(middle_name, 'Middle Name')
        if err: flash(err, "danger"); return redirect(url_for('admin.settings'))

    # Validate Email
    err = validate_email(email)
    if err: flash(err, "danger"); return redirect(url_for('admin.settings'))

    # Validate Username
    err = validate_username(username, first_name, last_name)
    if err: flash(err, "danger"); return redirect(url_for('admin.settings'))

    # Conflicts
    if email != current_user.email and User.query.filter_by(email=email).first():
        flash("Email already registered.", "danger")
        return redirect(url_for('admin.settings'))
    if username != current_user.username and User.query.filter_by(username=username).first():
        flash("Username already taken.", "danger")
        return redirect(url_for('admin.settings'))
    
    # Password Change
    if new_password:
        if not current_password:
            flash("Current password is required to change password.", "danger")
            return redirect(url_for('admin.settings'))
        if not current_user.check_password(current_password):
            flash("Incorrect current password.", "danger")
            return redirect(url_for('admin.settings'))
        
        err = validate_password(new_password, confirm_new_password)
        if err: flash(err, "danger"); return redirect(url_for('admin.settings'))
        
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
    return redirect(url_for('admin.settings'))

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
                'type': 'SYSTEM', 'is_read': False, 'created_at': 'Pending', 'raw_date': get_ph_time()
            })
            
        pend_res = Reservation.query.filter_by(status='PENDING').order_by(Reservation.created_at.desc()).limit(5).all()
        for r in pend_res:
            notifs_data.append({
                'id': f'res_{r.id}', 'title': 'New Reservation Need Confirmation',
                'message': f'{r.guest_count} guests for {r.date.strftime("%b %d")} at {r.time.strftime("%I:%M %p")}.',
                'type': 'RESERVATION', 'is_read': False,
                'created_at': r.created_at.strftime('%b %d, %I:%M %p') if r.created_at else 'Pending',
                'raw_date': r.created_at or get_ph_time()
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
                'raw_date': o.created_at or get_ph_time()
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
        extras['waiting_deliveries'] = Order.query.filter_by(dining_option='DELIVERY', delivery_status='WAITING').count()
    
    return jsonify({'count': count, **extras})

@admin_bp.route('/api/notifications/mark-all-read', methods=['POST'])
@login_required
@admin_required
def admin_mark_all_read():
    """Mark all admin's notifications as read"""
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
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
@admin_bp.route('/ingredients/add', methods=['POST'])
@login_required
@admin_required
def add_ingredient():
    name = request.form.get('name', '').strip()
    unit = request.form.get('unit', '').strip()
    stock_qty = request.form.get('stock_qty', 0, type=float)
    reorder_level = request.form.get('reorder_level', 10, type=float)
    cost_per_unit = request.form.get('cost_per_unit', 0, type=float)
    supplier_id = request.form.get('supplier_id', type=int)
    exp_date_str = request.form.get('expiration_date')
    expiration_date = None
    if exp_date_str:
        try:
            expiration_date = datetime.strptime(exp_date_str, '%Y-%m-%d').date()
        except: pass

    if not name or not unit:
        flash('Ingredient name and unit are required.', 'danger')
        return redirect(url_for('admin.inventory', tab='ingredients'))
    
    category = request.form.get('category', 'General').strip()
    
    ing = Ingredient(
        name=name, unit=unit, stock_qty=stock_qty, 
        reorder_level=reorder_level, cost_per_unit=cost_per_unit, 
        category=category,
        supplier_id=supplier_id if supplier_id else None,
        expiration_date=expiration_date
    )
    db.session.add(ing)
    db.session.flush() # Get ID before logging
    
    if stock_qty > 0:
        log_inventory_change(ing.id, 'ADD', stock_qty, 0, "Initial stock on creation")
    
    db.session.commit()
    
    # Sync supplier catalog
    if supplier_id:
        _sync_supplier_catalog(supplier_id)
        
    flash(f'Ingredient "{name}" added successfully!', 'success')
    return redirect(url_for('admin.inventory', tab='ingredients'))

@admin_bp.route('/ingredients/update/<int:ing_id>', methods=['POST'])
@login_required
@admin_required
def update_ingredient(ing_id):
    ing = Ingredient.query.get_or_404(ing_id)
    old_supplier_id = ing.supplier_id
    ing.name = request.form.get('name', ing.name).strip()
    ing.unit = request.form.get('unit', ing.unit).strip()
    ing.stock_qty = request.form.get('stock_qty', float(ing.stock_qty), type=float)
    ing.reorder_level = request.form.get('reorder_level', float(ing.reorder_level), type=float)
    ing.cost_per_unit = request.form.get('cost_per_unit', float(ing.cost_per_unit), type=float)
    ing.category = request.form.get('category', ing.category or 'General').strip()
    exp_date_str = request.form.get('expiration_date', '').strip()
    ing.expiration_date = date.fromisoformat(exp_date_str) if exp_date_str else None
    supplier_id = request.form.get('supplier_id', type=int)
    ing.supplier_id = supplier_id if supplier_id else None
    db.session.commit()

    # Sync supplier catalogs (both old and new)
    if supplier_id:
        _sync_supplier_catalog(supplier_id)
    if old_supplier_id and old_supplier_id != supplier_id:
        _sync_supplier_catalog(old_supplier_id)

    # If AJAX request, return JSON
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
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
            }
        })

    flash(f'Ingredient "{ing.name}" updated!', 'success')
    return redirect(url_for('admin.inventory', tab='ingredients'))

@admin_bp.route('/ingredients/delete/<int:ing_id>', methods=['POST'])
@login_required
@admin_required
def delete_ingredient(ing_id):
    ing = Ingredient.query.get_or_404(ing_id)
    MenuItemIngredient.query.filter_by(ingredient_id=ing_id).delete()
    sup_id = ing.supplier_id
    db.session.delete(ing)
    db.session.commit()
    
    # Sync supplier catalog after deletion
    if sup_id:
        _sync_supplier_catalog(sup_id)
        
    flash(f'Ingredient "{ing.name}" deleted.', 'success')
    return redirect(url_for('admin.inventory', tab='ingredients'))

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

@admin_bp.route('/inventory/audit-logs')
@login_required
@admin_required
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
        return redirect(url_for('admin.inventory'))
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
    return redirect(url_for('admin.inventory'))

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
    return redirect(url_for('admin.inventory'))

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
        flash(f'Deleted {len(item_ids)} suppliers.', 'success')
    return redirect(url_for('admin.inventory', tab='suppliers'))

# ─── WASTE MANAGEMENT ─────────────────────────────────────────────
@admin_bp.route('/inventory/waste', methods=['GET'])
@login_required
@admin_required
def waste_records():
    # Cap payload for speed (older records may be hidden; UI remains functional).
    records = WasteRecord.query.order_by(WasteRecord.created_at.desc()).limit(200).all()
    ingredients = Ingredient.query.order_by(Ingredient.name).limit(500).all()
    total_lost = sum(float(r.cost_lost or 0) for r in records)
    return render_template('admin/waste.html', records=records, ingredients=ingredients, total_lost=total_lost)

@admin_bp.route('/inventory/waste/add', methods=['POST'])
@login_required
@admin_required
def add_waste_record():
    ing_id = request.form.get('ingredient_id', type=int)
    qty = request.form.get('quantity_wasted', type=float)
    reason = request.form.get('reason', 'OTHER')
    notes = request.form.get('notes', '').strip()

    ing = Ingredient.query.get_or_404(ing_id)
    cost_lost = qty * float(ing.cost_per_unit or 0)
    prev_qty = float(ing.stock_qty)
    ing.stock_qty = max(0, prev_qty - qty)

    record = WasteRecord(
        ingredient_id=ing_id,
        recorded_by_id=current_user.id,
        quantity_wasted=qty,
        reason=reason,
        notes=notes,
        cost_lost=cost_lost
    )
    db.session.add(record)
    log_inventory_change(ing_id, 'SPOILED', qty, prev_qty, f'Waste: {reason} - {notes}')
    db.session.commit()
    flash(f'Waste record added. ₱{cost_lost:,.2f} lost. Stock deducted.', 'warning')
    return redirect(url_for('admin.waste_records'))

# ─── FIFO BATCH MANAGEMENT ────────────────────────────────────────
@admin_bp.route('/inventory/batches', methods=['GET'])
@login_required
@admin_required
def ingredient_batches():
    ingredients = Ingredient.query.order_by(Ingredient.name).limit(500).all()
    today = date.today()
    batches = (
        IngredientBatch.query.filter_by(is_exhausted=False)
        .join(Ingredient)
        .options(selectinload(IngredientBatch.ingredient))
        .order_by(IngredientBatch.purchase_date.asc())
        .limit(300)
        .all()
    )

    # Get all menu categories for the dropdown
    menu_categories = [r[0] for r in db.session.query(MenuItem.category)
                       .filter(MenuItem.is_deleted == False)
                       .distinct().order_by(MenuItem.category).all()]

    # Pre-compute which menu categories each ingredient belongs to
    # so the frontend can filter without a page reload
    ing_menu_cats = {}
    for ing in ingredients:
        cats = db.session.query(MenuItem.category).join(MenuItemIngredient).filter(
            MenuItemIngredient.ingredient_id == ing.id
        ).distinct().all()
        ing_menu_cats[ing.id] = [c[0] for c in cats]

    return render_template('admin/batches.html',
        batches=batches,
        ingredients=ingredients,
        today=today,
        menu_categories=menu_categories,
        ing_menu_cats=ing_menu_cats)

@admin_bp.route('/inventory/batches/add', methods=['POST'])
@login_required
@admin_required
def add_ingredient_batch():
    ing_id = request.form.get('ingredient_id', type=int)
    qty = request.form.get('batch_qty', type=float)
    cost = request.form.get('cost_per_unit', type=float, default=0)
    purchase_date_str = request.form.get('purchase_date')
    exp_date_str = request.form.get('expiration_date', '')

    purchase_date = date.fromisoformat(purchase_date_str)
    exp_date = date.fromisoformat(exp_date_str) if exp_date_str else None

    ing = Ingredient.query.get_or_404(ing_id)
    prev_qty = float(ing.stock_qty)
    ing.stock_qty = prev_qty + qty

    batch = IngredientBatch(
        ingredient_id=ing_id,
        batch_qty=qty,
        remaining_qty=qty,
        cost_per_unit=cost,
        purchase_date=purchase_date,
        expiration_date=exp_date
    )
    db.session.add(batch)
    log_inventory_change(ing_id, 'ADD', qty, prev_qty, f'Batch received on {purchase_date}')
    db.session.commit()
    flash(f'Batch of {qty} {ing.unit} added for {ing.name}.', 'success')
    return redirect(url_for('admin.ingredient_batches'))

# ─── INVENTORY AUDIT HISTORY ──────────────────────────────────────
@admin_bp.route('/inventory/audit', methods=['GET'])
@login_required
@admin_required
def inventory_audit():
    ing_filter = request.args.get('ingredient_id', type=int)
    action_filter = request.args.get('action', '')
    query = InventoryLog.query
    if ing_filter:
        query = query.filter_by(ingredient_id=ing_filter)
    if action_filter:
        query = query.filter_by(action=action_filter)
    logs = query.order_by(InventoryLog.created_at.desc()).limit(200).all()
    ingredients = Ingredient.query.order_by(Ingredient.name).limit(500).all()
    return render_template('admin/inventory_audit.html', logs=logs, ingredients=ingredients,
                           ing_filter=ing_filter, action_filter=action_filter)

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
        
    ingredients = Ingredient.query.order_by(Ingredient.name).limit(500).all()
    pending_count = StockRequest.query.filter_by(status='PENDING').count()
    return render_template('admin/stock_requests.html',
                           requests=requests_list, ingredients=ingredients,
                           pending_count=pending_count)

@admin_bp.route('/stock-requests/create', methods=['POST'])
@login_required
@admin_required
def create_stock_request():
    ing_id = request.form.get('ingredient_id', type=int)
    qty = request.form.get('quantity_requested', type=float)
    notes = request.form.get('notes', '').strip()
    req = StockRequest(
        ingredient_id=ing_id,
        requested_by_id=current_user.id,
        quantity_requested=qty,
        notes=notes
    )
    db.session.add(req)
    db.session.commit()
    # Notify inventory staff
    inv_staff = User.query.filter(User.role.in_(['INVENTORY_STAFF', 'INVENTORY', 'ADMIN'])).all()
    for s in inv_staff:
        _create_web_notification(s.id, 'New Stock Request', f'Kitchen requested {qty} units of {req.ingredient.name}', 'SYSTEM')

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
    """View system audit logs"""
    page = request.args.get('page', 1, type=int)
    per_page = 30
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
    peak_data = db.session.query(
        func.extract('hour', Order.created_at).label('hr'),
        func.count(Order.id).label('cnt')
    ).group_by('hr').order_by(func.count(Order.id).desc()).all()
    
    peak_hours = [{'hour': f'{int(h):02d}:00', 'orders': int(c)} for h, c in peak_data[:5]]

    # Customer Retention Rate
    total_customers_with_orders = db.session.query(func.count(func.distinct(Order.user_id))).scalar() or 0
    
    repeat_sub = db.session.query(Order.user_id).group_by(Order.user_id).having(func.count(Order.id) > 1).subquery()
    repeat_count = db.session.query(func.count()).select_from(repeat_sub).scalar() or 0
    
    retention_rate = round((repeat_count / total_customers_with_orders * 100), 1) if total_customers_with_orders > 0 else 0

    # Average Order Value
    avg_order = db.session.query(func.avg(Order.total_amount)).scalar()
    avg_order_value = round(float(avg_order), 2) if avg_order else 0

    # Orders by Day of Week
    dow_data = db.session.query(
        func.extract('dow', Order.created_at).label('dow'),
        func.count(Order.id)
    ).group_by('dow').order_by('dow').all()
    days_map = {0: 'Sun', 1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri', 6: 'Sat'}
    orders_by_day = [{'day': days_map.get(int(d), str(d)), 'orders': int(c)} for d, c in dow_data]

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
    """List all vouchers"""
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

    if not code or discount_value <= 0:
        flash("Please provide a valid code and discount value.", "danger")
        return redirect(url_for('admin.vouchers'))

    if Voucher.query.filter_by(code=code).first():
        flash(f"Voucher code '{code}' already exists.", "danger")
        return redirect(url_for('admin.vouchers'))

    valid_from = datetime.strptime(valid_from_str, '%Y-%m-%d') if valid_from_str else None
    valid_until = datetime.strptime(valid_until_str, '%Y-%m-%d') if valid_until_str else None

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
