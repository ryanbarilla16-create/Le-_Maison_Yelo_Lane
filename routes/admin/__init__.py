from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user, login_user, logout_user
from flask_mail import Message
from models import db, User, Reservation, MenuItem, Order, OrderItem, Review, Notification
from datetime import datetime, date, timedelta
from utils import get_ph_time, create_notification
from sqlalchemy import func
from functools import wraps
import traceback

def _create_web_notification(user_id, title, message, notif_type='SYSTEM'):
    """Backwards compatible helper for admin routes"""
    return create_notification(user_id, title, message, notif_type)

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

    # 1) Revenue Trend
    revenue_trend_labels, revenue_trend_data = [], []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        revenue_trend_labels.append(d.strftime('%b %d'))
        day_rev = db.session.query(func.coalesce(func.sum(Order.total_amount), 0)).filter(func.date(Order.created_at) == d).scalar()
        revenue_trend_data.append(float(day_rev))

    # 2) Daily Orders
    daily_orders_labels, daily_orders_data = [], []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        daily_orders_labels.append(d.strftime('%b %d'))
        cnt = db.session.query(func.count(Order.id)).filter(func.date(Order.created_at) == d).scalar()
        daily_orders_data.append(int(cnt or 0))

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
    today = date.today()

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
    total_revenue = db.session.query(func.coalesce(func.sum(Order.total_amount), 0)).scalar()

    return render_template('admin/analytics.html',
        total_customers=total_customers,
        total_menu_items=total_menu_items,
        menu_by_category=menu_by_category,
        total_revenue=float(total_revenue),
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
        <div style="font-family: 'Georgia', serif; max-width: 500px; margin: 0 auto; padding: 40px 30px; background: #ffffff; border-radius: 12px; border: 1px solid #e0d5c7;">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #8B4513; margin: 0; font-size: 1.5rem;">☕ Le Maison Yelo Lane</h1>
                <p style="color: #999; font-size: 0.85rem; margin-top: 5px;">Account Notification</p>
            </div>
            <div style="text-align: center; margin-bottom: 25px;">
                <div style="display: inline-block; background: linear-gradient(135deg, #28a745, #20c997); width: 60px; height: 60px; border-radius: 50%; line-height: 60px; font-size: 1.8rem;">✓</div>
            </div>
            <h2 style="text-align: center; color: #28a745; font-size: 1.3rem; margin-bottom: 15px;">Account Approved!</h2>
            <p style="color: #333; font-size: 1rem;">Hello <strong>{user.first_name}</strong>,</p>
            <p style="color: #555; font-size: 0.95rem;">Great news! Your account has been reviewed and approved by our admin team. You can now enjoy all the features of Le Maison Yelo Lane:</p>
            <ul style="color: #555; font-size: 0.9rem; line-height: 2;">
                <li>🍽️ Browse and order from our menu</li>
                <li>📅 Make table reservations</li>
                <li>⭐ Rate and review your orders</li>
            </ul>
            <div style="text-align: center; margin: 30px 0;">
                <a href="http://127.0.0.1:5000/login" style="display: inline-block; background: linear-gradient(135deg, #8B4513, #A0522D); color: #fff; font-weight: bold; text-decoration: none; padding: 12px 35px; border-radius: 50px; font-size: 0.95rem;">Log In Now</a>
            </div>
            <hr style="border: none; border-top: 1px solid #e0d5c7; margin: 25px 0;">
            <p style="color: #bbb; font-size: 0.75rem; text-align: center;">Thank you for choosing Le Maison Yelo Lane!</p>
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
    if role_filter == 'ALL':
        all_users = User.query.order_by(User.id).all()
    else:
        all_users = User.query.filter(func.upper(User.role) == role_filter.upper()).order_by(User.id).all()
    return render_template('admin/users.html', users=all_users, role_filter=role_filter)

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
            <div style="font-family: 'Georgia', serif; max-width: 500px; margin: 0 auto; padding: 40px 30px; background: #ffffff; border-radius: 12px; border: 1px solid #e0d5c7;">
                <div style="text-align: center; margin-bottom: 25px;">
                    <h1 style="color: #8B4513; margin: 0; font-size: 1.5rem;">☕ Le Maison Yelo Lane</h1>
                </div>
                <p style="color: #333; font-size: 1rem;">Hello,</p>
                <div style="color: #555; font-size: 0.95rem; line-height: 1.6;">
                    {message_content.replace(chr(10), '<br>')}
                </div>
                <hr style="border: none; border-top: 1px solid #e0d5c7; margin: 25px 0;">
                <p style="color: #bbb; font-size: 0.75rem; text-align: center;">Le Maison Yelo Lane · Pagsanjan, Laguna</p>
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
    if status_filter == 'ALL':
        all_res = Reservation.query.order_by(Reservation.created_at.desc()).all()
    else:
        all_res = Reservation.query.filter_by(status=status_filter).order_by(Reservation.created_at.desc()).all()
    return render_template('admin/reservations.html', reservations=all_res, status_filter=status_filter)

@admin_bp.route('/reservations/update/<int:res_id>', methods=['POST'])
@login_required
@admin_required
def update_reservation(res_id):
    res = Reservation.query.get_or_404(res_id)
    new_status = request.form.get('status')
    res.status = new_status
    db.session.commit()
    # Notify user about reservation status change
    status_msgs = {
        'CONFIRMED': f'Your reservation for {res.date.strftime("%b %d, %Y")} at {res.time.strftime("%I:%M %p")} has been confirmed!',
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
    items = MenuItem.query.order_by(MenuItem.category).all()
    total_items = len(items)
    out_of_stock = sum(1 for i in items if not i.is_available)
    return render_template('admin/inventory.html', items=items, total_items=total_items, out_of_stock=out_of_stock)

@admin_bp.route('/inventory/toggle/<int:item_id>', methods=['POST'])
@login_required
@admin_required
def toggle_stock(item_id):
    if current_user.role.upper() in ['CASHIER', 'STAFF']:
        flash("Access denied. View only.", "danger")
        return redirect(url_for('admin.inventory'))

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
    
    return render_template('admin/kitchen.html', 
        orders=active_orders, 
        status_filter=status_filter,
        pending_count=pending_count,
        preparing_count=preparing_count,
        completed_count=completed_count,
        cancelled_count=cancelled_count
    )

@admin_bp.route('/kitchen/api/orders')
@login_required
@admin_required
def kitchen_api_orders():
    """API endpoint for auto-refresh of kitchen orders"""
    active_orders = Order.query.filter(
        Order.status.in_(['PENDING', 'PREPARING'])
    ).order_by(Order.created_at.asc()).all()
    
    orders_data = []
    for order in active_orders:
        items_list = []
        for item in order.items:
            items_list.append({
                'name': item.menu_item.name,
                'qty': item.quantity
            })
        
        customer = 'Walk-in'
        if order.user:
            customer = f"{order.user.first_name} {order.user.last_name}"
        elif order.customer_name:
            customer = order.customer_name
        
        elapsed = (get_ph_time() - order.created_at).total_seconds()
        minutes = int(elapsed // 60)
        
        orders_data.append({
            'id': order.id,
            'customer': customer,
            'status': order.status,
            'dining_option': order.dining_option,
            'notes': order.notes or '',
            'items': items_list,
            'minutes_ago': minutes,
            'created_at': order.created_at.strftime('%I:%M %p')
        })
    
    return jsonify(orders_data)

@admin_bp.route('/kitchen/update/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def kitchen_update_order(order_id):
    if current_user.role.upper() == 'ADMIN':
        flash("Admin has View Only access for Kitchen.", "danger")
        return redirect(url_for('admin.kitchen_view'))

    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    if new_status in ['PENDING', 'PREPARING', 'COMPLETED', 'CANCELLED']:
        order.status = new_status
        db.session.commit()
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
    if current_user.role.upper() == 'ADMIN':
        flash("Admin has View Only access for POS.", "danger")
        return redirect(url_for('admin.walkin_order'))

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
        status='PENDING',
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
    query = Order.query.filter_by(dining_option='DELIVERY')
    if status_filter != 'ALL':
        if status_filter == 'WAITING':
            query = query.filter((Order.delivery_status == None) | (Order.delivery_status == 'WAITING'))
        else:
            query = query.filter_by(delivery_status=status_filter)
    all_orders = query.order_by(Order.created_at.desc()).all()
    return render_template('admin/deliveries.html', orders=all_orders, status_filter=status_filter)

# ─── ORDERS ──────────────────────────────────────────
@admin_bp.route('/orders')
@login_required
@admin_required
def orders():
    status_filter = request.args.get('status', 'ALL')
    if status_filter == 'ALL':
        all_orders = Order.query.order_by(Order.created_at.desc()).all()
    else:
        all_orders = Order.query.filter_by(status=status_filter).order_by(Order.created_at.desc()).all()
    return render_template('admin/orders.html', orders=all_orders, status_filter=status_filter)

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
@admin_required
def settings():
    site_settings = load_site_settings()
    if request.method == 'POST':
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

        if save_site_settings(site_settings):
            flash("Homepage content updated successfully.", "success")
        else:
            flash("Failed to save settings.", "danger")
        return redirect(url_for('admin.settings'))

    return render_template('admin/settings.html', site=site_settings)

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

