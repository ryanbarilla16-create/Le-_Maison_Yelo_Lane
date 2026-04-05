from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user, login_user, logout_user
from flask_mail import Message
from models import db, User, Reservation, MenuItem, Order, OrderItem, Review, Notification, Supplier, Ingredient, MenuItemIngredient, ChatMessage, AuditLog, Voucher, InventoryLog, WasteRecord, IngredientBatch, StockRequest
from datetime import datetime, date, timedelta
from utils import get_ph_time, create_notification, validate_name, validate_email, validate_username, validate_password
from sqlalchemy import func
from functools import wraps
import traceback

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

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        allowed_roles = ['ADMIN', 'CASHIER', 'INVENTORY_STAFF', 'INVENTORY', 'KITCHEN', 'STAFF', 'RIDER']
        if not current_user.is_authenticated or not current_user.role or current_user.role.upper() not in allowed_roles:
            flash("Access denied. Staff privileges required.", "danger")
            return redirect(url_for('admin.admin_login'))
        return f(*args, **kwargs)
    return decorated_function

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
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('admin.admin_login'))

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
    low_stock_items = MenuItem.query.filter_by(is_available=False).all()
    
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
    for c in cashiers:
        orders_count = Order.query.filter(Order.processed_by_id == c.id).count()
        total_sales = db.session.query(db.func.sum(Order.total_amount)).filter(Order.processed_by_id == c.id).scalar() or 0
        avg_order_value = float(total_sales) / orders_count if orders_count > 0 else 0
        # Today's activity
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_orders = Order.query.filter(Order.processed_by_id == c.id, Order.created_at >= today_start).count()
        cashier_stats.append({
            'name': f"{c.first_name} {c.last_name}",
            'count': orders_count,
            'sales': float(total_sales),
            'avg_order': round(avg_order_value, 2),
            'today_orders': today_orders
        })

    # ── RIDER STATS ──
    riders = User.query.filter(db.func.upper(User.role) == 'RIDER').all()
    rider_stats = []
    for r in riders:
        delivered_count = Order.query.filter(Order.rider_id == r.id, Order.delivery_status == 'DELIVERED').count()
        total_assigned = Order.query.filter(Order.rider_id == r.id).count()
        # Calculate total delivery fees earned
        delivery_earnings = db.session.query(db.func.sum(Order.delivery_fee)).filter(
            Order.rider_id == r.id, Order.delivery_status == 'DELIVERED'
        ).scalar() or 0
        pending_deliveries = Order.query.filter(
            Order.rider_id == r.id, 
            Order.delivery_status.in_(['WAITING', 'PICKED_UP', 'ON_THE_WAY'])
        ).count()
        rider_stats.append({
            'name': f"{r.first_name} {r.last_name}",
            'count': delivered_count,
            'total_assigned': total_assigned,
            'earnings': float(delivery_earnings),
            'pending': pending_deliveries,
            'success_rate': round((delivered_count / total_assigned * 100), 1) if total_assigned > 0 else 0
        })

    # ── INVENTORY STAFF STATS ──
    inv_staff = User.query.filter(db.func.upper(User.role).in_(['INVENTORY_STAFF', 'INVENTORY'])).all()
    inventory_stats = []
    for s in inv_staff:
        total_actions = InventoryLog.query.filter(InventoryLog.user_id == s.id).count()
        adds = InventoryLog.query.filter(InventoryLog.user_id == s.id, InventoryLog.action == 'ADD').count()
        deducts = InventoryLog.query.filter(InventoryLog.user_id == s.id, InventoryLog.action == 'DEDUCT').count()
        spoiled = InventoryLog.query.filter(InventoryLog.user_id == s.id, InventoryLog.action.in_(['EXPIRED', 'SPOILED'])).count()
        # Items they manage (unique ingredients)
        items_managed = db.session.query(db.func.count(db.func.distinct(InventoryLog.ingredient_id))).filter(
            InventoryLog.user_id == s.id
        ).scalar() or 0
        inventory_stats.append({
            'name': f"{s.first_name} {s.last_name}",
            'total_actions': total_actions,
            'adds': adds,
            'deducts': deducts,
            'spoiled': spoiled,
            'items_managed': items_managed
        })

    # ── KITCHEN STAFF STATS ──
    kitchen_staff = User.query.filter(db.func.upper(User.role) == 'KITCHEN').all()
    kitchen_stats = []
    # General kitchen metrics
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    kitchen_completed_today = Order.query.filter(Order.status == 'COMPLETED', Order.prep_end_at >= today_start).count()
    kitchen_preparing_now = Order.query.filter(Order.status == 'PREPARING').count()

    completed_with_prep = Order.query.filter(
        Order.status == 'COMPLETED', Order.prep_start_at.isnot(None), Order.prep_end_at.isnot(None)
    ).all()
    avg_prep_minutes = 0
    if completed_with_prep:
        total_secs = sum((o.prep_end_at - o.prep_start_at).total_seconds() for o in completed_with_prep)
        avg_prep_minutes = round(total_secs / len(completed_with_prep) / 60, 1)

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
    menu_by_category = db.session.query(MenuItem.category, func.count(MenuItem.id)).group_by(MenuItem.category).all()
    
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
        menu_by_category=menu_by_category,
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
    items = MenuItem.query.order_by(MenuItem.category, MenuItem.name).all()
    return render_template('admin/menu.html', items=items, categories_list=MENU_CATEGORIES)

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
            is_available=request.form.get('is_available') == 'on'
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
        item.is_available = request.form.get('is_available') == 'on'
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
    db.session.delete(item)
    db.session.commit()
    log_audit('DELETE', 'MenuItem', item_id, f'Deleted menu item: {item.name}')
    flash("Menu item deleted.", "success")
    return redirect(url_for('admin.menu', category=category))

# ─── MANAGEMENT: ACCOUNT APPROVALS ──────────────────
@admin_bp.route('/approvals')
@login_required
@admin_required
def approvals():
    pending = User.query.filter_by(status='PENDING', role='USER', is_verified=True).all()
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
        mail = current_app.extensions['mail']
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
        mail.send(msg)
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
            mail = current_app.extensions['mail']
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
            mail.send(msg)
            flash(f"Broadcast sent successfully to {len(emails)} user(s).", "success")
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
    
    # Paginated data
    items_paginated = MenuItem.query.order_by(MenuItem.category, MenuItem.name).paginate(page=page_items, per_page=15)
    ingredients_paginated = Ingredient.query.order_by(Ingredient.name).paginate(page=page_ingredients, per_page=20)
    
    all_suppliers = Supplier.query.order_by(Supplier.name).all()
    all_ingredients_raw = Ingredient.query.order_by(Ingredient.name).all()
    
    return render_template('admin/inventory.html', 
        items=items_paginated, 
        total_items=total_items, 
        out_of_stock=out_of_stock, 
        ingredients=ingredients_paginated, 
        suppliers=all_suppliers, 
        low_stock_count=low_stock_count,
        expiring_soon_count=expiring_soon_count,
        total_ingredients=total_ingredients,
        all_ingredients_raw=all_ingredients_raw,
        today=today)

@admin_bp.route('/inventory/generate-po')
@login_required
@admin_required
def generate_purchase_order():
    all_ingredients = Ingredient.query.all()
    low_stock = [ing for ing in all_ingredients if float(ing.stock_qty) <= float(ing.reorder_level)]
    
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
    if status_filter == 'ACTIVE':
        active_orders = Order.query.filter(
            Order.status.in_(['PENDING', 'PREPARING'])
        ).order_by(Order.created_at.asc()).all()
    elif status_filter == 'COMPLETED':
        active_orders = Order.query.filter_by(status='COMPLETED').order_by(Order.created_at.desc()).limit(20).all()
    elif status_filter == 'CANCELLED':
        active_orders = Order.query.filter_by(status='CANCELLED').order_by(Order.created_at.desc()).limit(20).all()
    else:
        active_orders = Order.query.filter_by(status=status_filter).order_by(Order.created_at.asc()).all()
    
    # Counts for badges
    pending_count = Order.query.filter_by(status='PENDING').count()
    preparing_count = Order.query.filter_by(status='PREPARING').count()
    completed_count = Order.query.filter_by(status='COMPLETED').count()
    cancelled_count = Order.query.filter_by(status='CANCELLED').count()
    
    # Calculate throughput metrics (Average Prep Time today)
    from sqlalchemy import func
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    completed_today = Order.query.filter(
        Order.status == 'COMPLETED',
        Order.prep_end_at >= today_start
    ).all()
    
    avg_prep_time = 0
    if completed_today:
        total_prep_seconds = 0
        valid_count = 0
        for o in completed_today:
            if o.prep_start_at and o.prep_end_at:
                total_prep_seconds += (o.prep_end_at - o.prep_start_at).total_seconds()
                valid_count += 1
        if valid_count > 0:
            avg_prep_time = round((total_prep_seconds / valid_count) / 60, 1)

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

    # Handle partial request (for soft refresh)
    if request.args.get('partial'):
        return render_template('admin/kitchen_partial.html', 
            orders=active_orders, hot_kitchen=hot_kitchen, cold_kitchen=cold_kitchen,
            bar_station=bar_station, item_count=len(item_data), status_filter=status_filter,
            pending_count=pending_count, preparing_count=preparing_count,
            completed_count=completed_count, cancelled_count=cancelled_count,
            avg_prep_time=avg_prep_time, ph_now=ph_now
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
        ph_now=ph_now
    )

@admin_bp.route('/kitchen/api/orders')
@login_required
@admin_required
def kitchen_api_orders():
    """API endpoint for auto-refresh of kitchen orders"""
    status_filter = request.args.get('status', 'ACTIVE')
    ph_now = get_ph_time()
    
    # Base query
    if status_filter == 'ACTIVE':
        active_orders = Order.query.filter(Order.status.in_(['PENDING', 'PREPARING']))
    else:
        active_orders = Order.query.filter_by(status=status_filter)
        
    active_orders = active_orders.order_by(Order.created_at.asc()).all()
    
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
        # Auto-deduct ingredients when order moves to PREPARING
        if new_status == 'PREPARING' and order.status != 'PREPARING':
            order.prep_start_at = datetime.utcnow()
            for oi in order.items:
                recipe = MenuItemIngredient.query.filter_by(menu_item_id=oi.menu_item_id).all()
                for r in recipe:
                    ingredient = Ingredient.query.get(r.ingredient_id)
                    if ingredient:
                        prev = float(ingredient.stock_qty)
                        deduction = float(r.quantity_needed) * oi.quantity
                        log_inventory_change(ingredient.id, 'DEDUCT', deduction, prev, f"Used for Order #{order.id}")
                        ingredient.stock_qty = max(0, prev - deduction)
                        if float(ingredient.stock_qty) <= 0:
                            for mi_link in ingredient.menu_items:
                                mi = MenuItem.query.get(mi_link.menu_item_id)
                                if mi: mi.is_available = False
        
        if new_status == 'COMPLETED':
            order.prep_end_at = datetime.utcnow()
            
        order.status = new_status
        db.session.commit()
        
        # Real-time update
        from extensions import socketio
        socketio.emit('order_status_update', {'id': order.id, 'status': new_status}, namespace='/')
        
        log_audit('UPDATE', 'Order', order.id, f'Order #{order.id} status changed to {new_status}')
    return redirect(url_for('admin.kitchen_view'))

# ─── WALK-IN ORDERS ──────────────────────────────────
@admin_bp.route('/walkin-order', methods=['GET'])
@login_required
@admin_required
def walkin_order():
    items = MenuItem.query.filter_by(is_available=True).order_by(MenuItem.category, MenuItem.name).all()
    categories = sorted(set(i.category for i in items))
    return render_template('admin/walkin_order.html', items=items, categories=categories)

@admin_bp.route('/walkin-order/submit', methods=['POST'])
@login_required
@admin_required
def walkin_order_submit():
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

    # --- ORDER VALIDATION LOGIC ---
    items_data = [{'menu_item_id': int(id), 'quantity': int(qty)} for id, qty in zip(item_ids, quantities)]
    is_valid, msg, status_override = validate_order(items_data, dining_option, payment_method, is_pos=True)
    
    if not is_valid:
        flash(msg, "danger")
        return redirect(url_for('admin.walkin_order'))
    # ------------------------------

    order_items = []
    total = 0
    for item_id, qty in zip(item_ids, quantities):
        qty = int(qty)
        if qty <= 0:
            continue
        menu_item = MenuItem.query.get(int(item_id))
        if menu_item:
            order_items.append(OrderItem(
                menu_item_id=menu_item.id,
                quantity=qty,
                price_at_time=menu_item.price
            ))
            total += float(menu_item.price) * qty

    if not order_items:
        flash("No valid items in order.", "danger")
        return redirect(url_for('admin.walkin_order'))
        
    amount_tendered = None
    change_amount = None
    if payment_method == 'COUNTER':
        req_amount = request.form.get('amount_tendered')
        if req_amount:
            try:
                amount_tendered = float(req_amount)
                change_amount = amount_tendered - float(total)
            except ValueError:
                pass


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
        # Generate Xendit Invoice for Walk-in
        import os, base64, requests
        from datetime import datetime
        xendit_secret_key = os.environ.get('XENDIT_SECRET_KEY')
        if xendit_secret_key and xendit_secret_key != 'add_your_xendit_secret_key_here':
            api_key_b64 = base64.b64encode(f"{xendit_secret_key}:".encode('utf-8')).decode('utf-8')
            headers = {
                'Authorization': f'Basic {api_key_b64}',
                'Content-Type': 'application/json'
            }
            
            success_url = url_for('admin.orders', _external=True)
            failure_url = url_for('admin.orders', _external=True)
            
            payload = {
                'external_id': f"order-walkin-{order.id}-{int(get_ph_time().timestamp())}",
                'amount': float(total),
                'payer_email': current_user.email, # Use the admin/cashier's email since walkin has no email
                'description': f"Walk-in Order #{order.id} for {customer_name}",
                'success_redirect_url': success_url,
                'failure_redirect_url': failure_url,
                'currency': 'PHP'
            }
            
            try:
                response = requests.post('https://api.xendit.co/v2/invoices', json=payload, headers=headers)
                if response.status_code == 200:
                    invoice_data = response.json()
                    order.xendit_invoice_url = invoice_data.get('invoice_url')
                    order.xendit_invoice_id = invoice_data.get('id')
                    db.session.commit()
                    
                    flash(f"Walk-in Order #{order.id} created! Redirecting to GCash payment...", "success")
                    return redirect(order.xendit_invoice_url)
                else:
                    flash(f"Walk-in Order created, but failed to generate GCash link: {response.json().get('message')}", "warning")
            except Exception as e:
                flash("Walk-in Order created. An error occurred with the payment gateway.", "warning")
                print("Xendit Error (Walk-in):", e)
        else:
            flash("Walk-in Order created. Payment gateway not configured. Please collect payment manually.", "warning")
            
    else:
        flash(f"Walk-in Order #{order.id} created for {customer_name}! Please collect ₱{total:,.2f} at the counter.", "success")
        
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

@admin_bp.route('/orders/update/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def update_order(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    
    # Auto-deduct ingredients when order moves to PREPARING
    if new_status == 'PREPARING' and order.status != 'PREPARING':
        for oi in order.items:
            recipe = MenuItemIngredient.query.filter_by(menu_item_id=oi.menu_item_id).all()
            for r in recipe:
                ingredient = Ingredient.query.get(r.ingredient_id)
                if ingredient:
                    deduction = float(r.quantity_needed) * oi.quantity
                    ingredient.stock_qty = max(0, float(ingredient.stock_qty) - deduction)
                    
                    # Deducting stock might make the ingredient insufficient for more orders
                    if float(ingredient.stock_qty) < float(r.quantity_needed):
                        # Re-scan all menu items that use this ingredient and disable them if needed
                        affected_menu_items = MenuItemIngredient.query.filter_by(ingredient_id=ingredient.id).all()
                        for ami in affected_menu_items:
                            mi = MenuItem.query.get(ami.menu_item_id)
                            if mi and mi.is_available:
                                # We check if the ingredient that was just depleted is indeed insufficient for this model
                                if float(ingredient.stock_qty) < float(ami.quantity_needed):
                                    mi.is_available = False
                                    db.session.commit()
    
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
    
    # Send receipt email when order is COMPLETED (skip walk-in orders)
    if new_status == 'COMPLETED' and order.user:
        try:
            mail = current_app.extensions['mail']
            user = order.user
            
            # Build order items table rows
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
                sender=current_app.config['MAIL_USERNAME'],
                recipients=[user.email]
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
            mail.send(msg)
        except Exception as e:
            print(f"Receipt email failed: {e}")
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
    if status_filter == 'ALL':
        all_reviews = Review.query.order_by(Review.created_at.desc()).all()
    else:
        all_reviews = Review.query.filter_by(status=status_filter).order_by(Review.created_at.desc()).all()
        
    # AI Sentiment Analysis (Dynamic Calculation to avoid DB Migrations)
    positive_words = ['good', 'great', 'excellent', 'amazing', 'best', 'delicious', 'love', 'perfect', 'nice', 'awesome', 'sarap', 'mabilis', 'ayos', 'sulit', 'outstanding', 'fantastic', 'superb', 'yummy', 'tasty']
    negative_words = ['bad', 'terrible', 'awful', 'worst', 'horrible', 'poor', 'slow', 'cold', 'disappointing', 'hate', 'pangit', 'panget', 'mabagal', 'matagal', 'bland', 'salty', 'late', 'matabang', 'maalat']

    for review in all_reviews:
        text = str(review.comment or '').lower()
        if not text:
            review.ai_sentiment = "NEUTRAL"
            review.ai_sentiment_icon = "😐"
            review.ai_sentiment_color = "secondary"
            continue
            
        pos_count = sum(text.count(word) for word in positive_words)
        neg_count = sum(text.count(word) for word in negative_words)
        
        # Adjust weight based on star rating
        if review.rating >= 4:
            pos_count += 2
        elif review.rating <= 2:
            neg_count += 2
            
        if pos_count > neg_count:
            review.ai_sentiment = "POSITIVE"
            review.ai_sentiment_icon = "😊"
            review.ai_sentiment_color = "success"
        elif neg_count > pos_count:
            review.ai_sentiment = "NEGATIVE"
            review.ai_sentiment_icon = "😠"
            review.ai_sentiment_color = "danger"
        else:
            if review.rating >= 4:
                review.ai_sentiment = "POSITIVE"
                review.ai_sentiment_icon = "😊"
                review.ai_sentiment_color = "success"
            elif review.rating <= 2:
                review.ai_sentiment = "NEGATIVE"
                review.ai_sentiment_icon = "😠"
                review.ai_sentiment_color = "danger"
            else:
                review.ai_sentiment = "NEUTRAL"
                review.ai_sentiment_icon = "😐"
                review.ai_sentiment_color = "secondary"

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
    
    ing = Ingredient(
        name=name, unit=unit, stock_qty=stock_qty, 
        reorder_level=reorder_level, cost_per_unit=cost_per_unit, 
        supplier_id=supplier_id if supplier_id else None,
        expiration_date=expiration_date
    )
    db.session.add(ing)
    db.session.flush() # Get ID before logging
    
    if stock_qty > 0:
        log_inventory_change(ing.id, 'ADD', stock_qty, 0, "Initial stock on creation")
    
    db.session.commit()
    flash(f'Ingredient "{name}" added successfully!', 'success')
    return redirect(url_for('admin.inventory', tab='ingredients'))

@admin_bp.route('/ingredients/update/<int:ing_id>', methods=['POST'])
@login_required
@admin_required
def update_ingredient(ing_id):
    ing = Ingredient.query.get_or_404(ing_id)
    ing.name = request.form.get('name', ing.name).strip()
    ing.unit = request.form.get('unit', ing.unit).strip()
    ing.stock_qty = request.form.get('stock_qty', float(ing.stock_qty), type=float)
    ing.reorder_level = request.form.get('reorder_level', float(ing.reorder_level), type=float)
    ing.cost_per_unit = request.form.get('cost_per_unit', float(ing.cost_per_unit), type=float)
    supplier_id = request.form.get('supplier_id', type=int)
    ing.supplier_id = supplier_id if supplier_id else None
    db.session.commit()
    flash(f'Ingredient "{ing.name}" updated!', 'success')
    return redirect(url_for('admin.inventory', tab='ingredients'))

@admin_bp.route('/ingredients/delete/<int:ing_id>', methods=['POST'])
@login_required
@admin_required
def delete_ingredient(ing_id):
    ing = Ingredient.query.get_or_404(ing_id)
    MenuItemIngredient.query.filter_by(ingredient_id=ing_id).delete()
    db.session.delete(ing)
    db.session.commit()
    flash(f'Ingredient "{ing.name}" deleted.', 'success')
    return redirect(url_for('admin.inventory', tab='ingredients'))

@admin_bp.route('/ingredients/bulk-delete', methods=['POST'])
@login_required
@admin_required
def bulk_delete_ingredients():
    item_ids = request.form.getlist('item_ids[]')
    if item_ids:
        Ingredient.query.filter(Ingredient.id.in_(item_ids)).delete(synchronize_session=False)
        MenuItemIngredient.query.filter(MenuItemIngredient.ingredient_id.in_(item_ids)).delete(synchronize_session=False)
        db.session.commit()
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
            if mi and not mi.is_available:
                can_enable = True
                for other in mi.ingredients:
                    if float(other.ingredient.stock_qty) < float(other.quantity_needed):
                        can_enable = False
                        break
                if can_enable:
                    mi.is_available = True
                    db.session.commit()

        flash(f'Restocked {add_qty} {ing.unit} of "{ing.name}".', 'success')
    return redirect(url_for('admin.inventory', tab='ingredients'))

@admin_bp.route('/ingredients/waste/<int:ing_id>', methods=['POST'])
@login_required
@admin_required
def waste_ingredient(ing_id):
    ing = Ingredient.query.get_or_404(ing_id)
    qty = request.form.get('qty', 0, type=float)
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

        flash(f'Recorded {qty} {ing.unit} as {action}.', 'warning')
    else:
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
    result = []
    for l in links:
        ing = Ingredient.query.get(l.ingredient_id)
        if ing:
            result.append({'id': l.id, 'ingredient_id': ing.id, 'name': ing.name, 'unit': ing.unit, 'quantity_needed': float(l.quantity_needed)})
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
    flash('Recipe updated!', 'success')
    return redirect(url_for('admin.inventory'))

@admin_bp.route('/recipe/remove/<int:link_id>', methods=['POST'])
@login_required
@admin_required
def remove_recipe_ingredient(link_id):
    link = MenuItemIngredient.query.get_or_404(link_id)
    db.session.delete(link)
    db.session.commit()
    flash('Ingredient removed from recipe.', 'success')
    return redirect(url_for('admin.inventory'))

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
    records = WasteRecord.query.order_by(WasteRecord.created_at.desc()).all()
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
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
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    today = date.today()
    batches = IngredientBatch.query.filter_by(is_exhausted=False).order_by(
        IngredientBatch.purchase_date.asc()
    ).all()
    return render_template('admin/batches.html', batches=batches, ingredients=ingredients, today=today)

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
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
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
        requests_list = StockRequest.query.filter_by(
            requested_by_id=current_user.id
        ).order_by(StockRequest.created_at.desc()).all()
    else:
        # Inventory / Admin sees all requests
        requests_list = StockRequest.query.order_by(StockRequest.created_at.desc()).all()
        
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
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
    flash('Stock request submitted! Waiting for inventory staff approval.', 'info')
    
    # Notify inventory staff
    inv_staff = User.query.filter(User.role.in_(['INVENTORY_STAFF', 'INVENTORY', 'ADMIN'])).all()
    for s in inv_staff:
        _create_web_notification(s.id, 'New Stock Request', f'Kitchen requested {qty} units of ingredient ID {ing_id}', 'SYSTEM')

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
            prev_qty = float(ing.stock_qty)
            ing.stock_qty = max(0, prev_qty - qty_fulfilled)
            log_inventory_change(ing.id, 'DEDUCT', qty_fulfilled, prev_qty,
                                 f'Fulfilled kitchen stock request #{req_id}')
            
        req.quantity_fulfilled = qty_fulfilled
        req.fulfilled_by_id = current_user.id
        req.status = 'FULFILLED'
        db.session.commit()
        
        _create_web_notification(req.requested_by_id, 'Stock Request Fulfilled', f'{qty_fulfilled} {ing.unit} of {ing.name} is ready.', 'SYSTEM')
        flash(f'Stock request #{req_id} fulfilled! {qty_fulfilled} units sent to kitchen.', 'success')
    return redirect(url_for('admin.stock_requests'))

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
        .order_by(subquery.c.last_msg_at.desc()).all()
        
    return render_template('admin/chats.html', chat_users=chat_users)

@admin_bp.route('/chats/<int:user_id>')
@login_required
@admin_required
def chat_with_user(user_id):
    """View chat history and reply to a specific user"""
    user = User.query.get_or_404(user_id)
    messages = ChatMessage.query.filter_by(user_id=user_id).order_by(ChatMessage.created_at.asc()).all()
    
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
    low_stock = Ingredient.query.filter(Ingredient.stock_qty <= Ingredient.reorder_level).all()
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
    all_vouchers = Voucher.query.order_by(Voucher.created_at.desc()).all()
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
