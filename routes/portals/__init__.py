from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from flask_login import login_user, current_user, login_required
from flask_mail import Message
from models import db, User, Order, OrderItem, Ingredient, MenuItemIngredient, Supplier, WasteRecord, MenuItem, IngredientBatch
from utils import get_ph_time, validate_password, safe_elapsed
import random
import threading
import traceback
from collections import defaultdict

# Blueprints WITHOUT prefix because we specify full paths in decorators to match user's custom URL mix
cashier_bp = Blueprint('cashier_portal', __name__)
kitchen_bp = Blueprint('kitchen_portal', __name__)
inventory_bp = Blueprint('inventory_portal', __name__)
rider_bp = Blueprint('rider_portal', __name__)

# ── Shared Helpers ────────────────────────────────────────────────

def _authenticate_portal(email, password, allowed_roles):
    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password) and user.status == 'ACTIVE' and user.role and user.role.upper() in allowed_roles:
        return user
    return None


def _send_mail_async(app, msg):
    """Background worker to send Flask-Mail messages without blocking."""
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
                    print(f"Portal mail send failed (final): {e}")
                    traceback.print_exc()
                    return


def _portal_forgot_password(portal_name, allowed_roles, login_url_name, verify_url_name):
    """
    Reusable forgot-password handler for all portals.
    Step 1: Accept email, generate OTP, send via Flask-Mail.
    """
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        user = User.query.filter_by(email=email).first()

        if not user or not user.role or user.role.upper() not in allowed_roles:
            flash(f"If an account exists for {email}, a reset code has been sent.", "info")
            return redirect(url_for(login_url_name))

        if user.otp_created_at:
            elapsed = safe_elapsed(user.otp_created_at)
            if elapsed < 60:
                flash(f"Please wait {int(60 - elapsed)}s before requesting a new code.", "warning")
                return redirect(url_for(verify_url_name, user_id=user.id))

        otp = f"{random.randint(100000, 999999)}"
        user.otp_code = otp
        user.otp_created_at = get_ph_time()
        db.session.commit()

        print(f"--- {portal_name.upper()} FORGOT PASSWORD OTP FOR {email} IS: {otp} ---")

        html_msg = f"""
        <div style="background-color: #fcfaf8; padding: 40px 20px; font-family: 'Helvetica Neue', Arial, sans-serif;">
            <div style="max-width: 500px; margin: 0 auto; background: #ffffff; border-radius: 20px; border: 1px solid #eee; overflow: hidden; box-shadow: 0 10px 20px rgba(0,0,0,0.05);">
                <div style="background: #8b634b; padding: 30px; text-align: center;">
                    <h1 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 300;">Le Maison {portal_name}</h1>
                </div>
                <div style="padding: 40px; color: #4a3b32; line-height: 1.6;">
                    <h2 style="margin-top: 0; font-size: 18px;">Staff Access Reset</h2>
                    <p>Hello <strong>{user.first_name}</strong>,</p>
                    <p>A password reset was requested for your {portal_name} account. Use the code below to proceed:</p>
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
            target=_send_mail_async,
            args=(app_obj, Message(
                f'{portal_name} Password Reset - Le Maison',
                recipients=[email],
                html=html_msg,
                body=f"Hello {user.first_name},\n\nYour {portal_name} password reset code is: {otp}\n\nThis code will expire in 5 minutes.\n\nIf you did not request this, please ignore this email."
            )),
            daemon=True,
        ).start()

        session[f'{portal_name.lower()}_reset_user_id'] = user.id
        return redirect(url_for(verify_url_name, user_id=user.id))

    return None  # Let caller render template


def _portal_verify_otp(portal_name, user_id, forgot_url_name, reset_url_name, login_url_name):
    """
    Reusable OTP verification handler for all portals.
    Step 2: Accept OTP code, verify against DB.
    """
    session_key = f'{portal_name.lower()}_reset_user_id'
    if session.get(session_key) != user_id:
        flash("Invalid session.", "danger")
        return redirect(url_for(forgot_url_name))

    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        otp_input = request.form.get('otp', '').strip()
        if user.otp_created_at and safe_elapsed(user.otp_created_at) > 300:
            flash("Code expired. Please request a new one.", "danger")
            return redirect(url_for(forgot_url_name))

        if user.otp_code == otp_input:
            session[f'{portal_name.lower()}_reset_verified_id'] = user.id
            flash("Code verified. Set your new password.", "success")
            return redirect(url_for(reset_url_name))
        else:
            flash("Invalid code.", "danger")

    cooldown = 0
    if user.otp_created_at:
        cooldown = max(0, int(60 - safe_elapsed(user.otp_created_at)))

    return {'user': user, 'cooldown_remaining': cooldown}


def _portal_resend_otp(portal_name, user_id, forgot_url_name, verify_url_name):
    """Resend OTP for any portal."""
    session_key = f'{portal_name.lower()}_reset_user_id'
    if session.get(session_key) != user_id:
        return redirect(url_for(forgot_url_name))

    user = User.query.get_or_404(user_id)
    if user.otp_created_at and safe_elapsed(user.otp_created_at) < 60:
        return redirect(url_for(verify_url_name, user_id=user.id))

    otp = f"{random.randint(100000, 999999)}"
    user.otp_code = otp
    user.otp_created_at = get_ph_time()
    db.session.commit()

    html_msg = f"<p>Your new {portal_name} reset code is: <strong>{otp}</strong></p>"
    app_obj = current_app._get_current_object()
    threading.Thread(
        target=_send_mail_async,
        args=(app_obj, Message(
            f'New {portal_name} Reset Code', 
            recipients=[user.email], 
            html=html_msg,
            body=f"Your new {portal_name} reset code is: {otp}"
        )),
        daemon=True,
    ).start()

    flash("New code sent.", "success")
    return redirect(url_for(verify_url_name, user_id=user.id))


def _portal_reset_password(portal_name, login_url_name):
    """
    Reusable password reset handler for all portals.
    Step 3: Accept new password and confirm.
    """
    verified_key = f'{portal_name.lower()}_reset_verified_id'
    session_key = f'{portal_name.lower()}_reset_user_id'
    user_id = session.get(verified_key)
    if not user_id:
        return redirect(url_for(login_url_name))

    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        err = validate_password(new_password, confirm_password)
        if err:
            flash(err, "danger")
            return None  # Caller re-renders

        user.set_password(new_password)
        user.otp_code = None
        user.otp_created_at = None
        db.session.commit()

        session.pop(session_key, None)
        session.pop(verified_key, None)

        flash("Password updated successfully. Please log in.", "success")
        return redirect(url_for(login_url_name))

    return None  # Caller renders template


# ══════════════════════════════════════════════════════════════════
# ── UNIFIED STAFF LOGIN (/staff/login) ────────────────────────────
# ══════════════════════════════════════════════════════════════════

ALL_STAFF_ROLES = ['CASHIER', 'STAFF', 'KITCHEN', 'INVENTORY_STAFF', 'INVENTORY', 'ADMIN']

def _get_dashboard_for_role(role):
    """Return the correct dashboard URL name based on user role."""
    role_upper = (role or '').upper()
    if role_upper in ('CASHIER', 'STAFF'):
        return 'cashier_portal.cashier_dashboard'
    elif role_upper == 'KITCHEN':
        return 'kitchen_portal.kitchen_dashboard'
    elif role_upper in ('INVENTORY_STAFF', 'INVENTORY'):
        return 'inventory_portal.inventory_dashboard'
    elif role_upper == 'ADMIN':
        return 'admin.overview'
    return 'cashier_portal.staff_login'

@cashier_bp.route('/staff/login', methods=['GET', 'POST'])
def staff_login():
    # If already logged in as staff, redirect to their dashboard
    if current_user.is_authenticated and current_user.role and current_user.role.upper() in ALL_STAFF_ROLES:
        return redirect(url_for(_get_dashboard_for_role(current_user.role)))

    if request.method == 'POST':
        user = _authenticate_portal(
            request.form.get('email'),
            request.form.get('password'),
            ALL_STAFF_ROLES
        )
        if user:
            role_upper = user.role.upper()
            if role_upper in ('CASHIER', 'STAFF'):
                session['logged_in_portal'] = 'cashier'
            elif role_upper == 'KITCHEN':
                session['logged_in_portal'] = 'kitchen'
            elif role_upper in ('INVENTORY_STAFF', 'INVENTORY'):
                session['logged_in_portal'] = 'inventory'
            else:
                session['logged_in_portal'] = 'admin'

            login_user(user)
            return redirect(url_for(_get_dashboard_for_role(user.role)))
        flash('Invalid email, password, or insufficient permissions.', 'error')
    return render_template('staff/login.html')


# ── Unified Staff Forgot Password ──
@cashier_bp.route('/staff/forgot-password', methods=['GET', 'POST'])
def staff_forgot_password():
    result = _portal_forgot_password('Staff', ALL_STAFF_ROLES, 'cashier_portal.staff_login', 'cashier_portal.staff_verify_otp')
    if result:
        return result
    return render_template('portal_auth/forgot_password.html', portal='Staff', portal_color='#5D4037',
                           form_action=url_for('cashier_portal.staff_forgot_password'),
                           login_url=url_for('cashier_portal.staff_login'))

@cashier_bp.route('/staff/verify-otp/<int:user_id>', methods=['GET', 'POST'])
def staff_verify_otp(user_id):
    result = _portal_verify_otp('Staff', user_id, 'cashier_portal.staff_forgot_password', 'cashier_portal.staff_reset_password', 'cashier_portal.staff_login')
    if isinstance(result, dict):
        return render_template('portal_auth/verify_otp.html', portal='Staff', portal_color='#5D4037',
                               user=result['user'], cooldown_remaining=result['cooldown_remaining'],
                               verify_action=url_for('cashier_portal.staff_verify_otp', user_id=user_id),
                               resend_action=url_for('cashier_portal.staff_resend_otp', user_id=user_id),
                               login_url=url_for('cashier_portal.staff_login'))
    return result

@cashier_bp.route('/staff/resend-otp/<int:user_id>', methods=['POST'])
def staff_resend_otp(user_id):
    return _portal_resend_otp('Staff', user_id, 'cashier_portal.staff_forgot_password', 'cashier_portal.staff_verify_otp')

@cashier_bp.route('/staff/reset-password', methods=['GET', 'POST'])
def staff_reset_password():
    result = _portal_reset_password('Staff', 'cashier_portal.staff_login')
    if result:
        return result
    return render_template('portal_auth/reset_password.html', portal='Staff', portal_color='#5D4037',
                           form_action=url_for('cashier_portal.staff_reset_password'),
                           login_url=url_for('cashier_portal.staff_login'))


# ══════════════════════════════════════════════════════════════════
# ── Cashier Portal ────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════

CASHIER_ROLES = ['CASHIER', 'STAFF', 'ADMIN']

@cashier_bp.route('/cashier/login', methods=['GET', 'POST'])
@cashier_bp.route('/staff/cashier/login', methods=['GET', 'POST'])
def cashier_login():
    # Redirect to unified staff login
    return redirect(url_for('cashier_portal.staff_login'))

@cashier_bp.route('/staff/cashier')
def cashier_dashboard():
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    # Required by templates/cashier/dashboard.html: 
    # active_orders (count), completed_today (count), unpaid_orders (count), orders (list)
    
    today = get_ph_time().date()
    
    active_orders_count = Order.query.filter(Order.status.in_(['PENDING', 'PREPARING', 'READY'])).count()
    completed_today_count = Order.query.filter(Order.status == 'COMPLETED', db.func.date(Order.created_at) == today).count()
    unpaid_orders_count = Order.query.filter_by(payment_status='UNPAID').count()
    
    # Recent active orders for the live queue
    live_orders = Order.query.filter(Order.status.in_(['PENDING', 'PREPARING', 'READY'])).order_by(Order.created_at.desc()).limit(50).all()
    
    return render_template('cashier/dashboard.html', 
                           portal_name=f"{current_user.first_name} {current_user.last_name}",
                           active_orders=active_orders_count,
                           completed_today=completed_today_count,
                           unpaid_orders=unpaid_orders_count,
                           orders=live_orders)

@cashier_bp.route('/staff/cashier/walkin-order')
def cashier_walkin_order():
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    items = MenuItem.query.filter_by(is_available=True, is_deleted=False).order_by(MenuItem.category, MenuItem.name).all()
    categories = sorted(set(i.category for i in items))
    return render_template('cashier/walkin_order.html', items=items, categories=categories)

@cashier_bp.route('/staff/cashier/billing')
def cashier_billing():
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))

    status_filter = request.args.get('status', 'UNPAID')
    page = request.args.get('page', 1, type=int)

    query = Order.query
    if status_filter != 'ALL':
        query = query.filter_by(payment_status=status_filter)

    pagination = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=20, error_out=False)

    today = get_ph_time().date()
    stats = db.session.query(
        Order.payment_status, Order.payment_method,
        db.func.count(Order.id), db.func.sum(Order.total_amount)
    ).filter(db.func.date(Order.created_at) == today).group_by(Order.payment_status, Order.payment_method).all()

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

    return render_template('cashier/billing.html',
                           orders=pagination,
                           status_filter=status_filter,
                           total_sales_today=total_sales_today,
                           unpaid_count=unpaid_count,
                           cash_sales=cash_sales,
                           online_sales=online_sales)

@cashier_bp.route('/staff/cashier/history')
def cashier_orders_history():
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    page = request.args.get('page', 1, type=int)
    orders_pg = Order.query.order_by(Order.created_at.desc()).paginate(page=page, per_page=20)
    
    return render_template('cashier/orders_history.html', 
                           orders=orders_pg, 
                           portal_name=f"{current_user.first_name} {current_user.last_name}")

@cashier_bp.route('/staff/cashier/chats')
def cashier_chats():
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    from models import ChatMessage
    from sqlalchemy import func
    subquery = db.session.query(
        ChatMessage.user_id,
        func.max(ChatMessage.created_at).label('last_msg_at')
    ).group_by(ChatMessage.user_id).subquery()
    chat_users = db.session.query(User, subquery.c.last_msg_at)\
        .join(subquery, User.id == subquery.c.user_id)\
        .order_by(subquery.c.last_msg_at.desc()).limit(200).all()
    return render_template('cashier/chats.html', chat_users=chat_users)

@cashier_bp.route('/cashier/logout')
def cashier_logout():
    return redirect(url_for('admin.admin_logout'))

@cashier_bp.route('/cashier/forgot-password', methods=['GET', 'POST'])
@cashier_bp.route('/staff/cashier/forgot-password', methods=['GET', 'POST'])
def cashier_forgot_password():
    result = _portal_forgot_password('Cashier', CASHIER_ROLES, 'cashier_portal.staff_login', 'cashier_portal.cashier_verify_otp')
    if result:
        return result
    return render_template('portal_auth/forgot_password.html', portal='Cashier', portal_color='#16A085',
                           form_action=url_for('cashier_portal.cashier_forgot_password'),
                           login_url=url_for('cashier_portal.staff_login'))

@cashier_bp.route('/cashier/verify-otp/<int:user_id>', methods=['GET', 'POST'])
@cashier_bp.route('/staff/cashier/verify-otp/<int:user_id>', methods=['GET', 'POST'])
def cashier_verify_otp(user_id):
    result = _portal_verify_otp('Cashier', user_id, 'cashier_portal.cashier_forgot_password', 'cashier_portal.cashier_reset_password', 'cashier_portal.staff_login')
    if isinstance(result, dict):
        return render_template('portal_auth/verify_otp.html', portal='Cashier', portal_color='#16A085',
                               user=result['user'], cooldown_remaining=result['cooldown_remaining'],
                               verify_action=url_for('cashier_portal.cashier_verify_otp', user_id=user_id),
                               resend_action=url_for('cashier_portal.cashier_resend_otp', user_id=user_id),
                               login_url=url_for('cashier_portal.staff_login'))
    return result

@cashier_bp.route('/cashier/resend-otp/<int:user_id>', methods=['POST'])
def cashier_resend_otp(user_id):
    return _portal_resend_otp('Cashier', user_id, 'cashier_portal.cashier_forgot_password', 'cashier_portal.cashier_verify_otp')

@cashier_bp.route('/cashier/reset-password', methods=['GET', 'POST'])
def cashier_reset_password():
    result = _portal_reset_password('Cashier', 'cashier_portal.staff_login')
    if result:
        return result
    return render_template('portal_auth/reset_password.html', portal='Cashier', portal_color='#16A085',
                           form_action=url_for('cashier_portal.cashier_reset_password'),
                           login_url=url_for('cashier_portal.staff_login'))


# ══════════════════════════════════════════════════════════════════
# ── Kitchen Portal ────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════

KITCHEN_ROLES = ['KITCHEN', 'ADMIN', 'CASHIER']

@kitchen_bp.route('/kitchen/login', methods=['GET', 'POST'])
@kitchen_bp.route('/staff/kitchen/login', methods=['GET', 'POST'])
def kitchen_login():
    # Redirect to unified staff login
    return redirect(url_for('cashier_portal.staff_login'))

@kitchen_bp.route('/staff/kitchen')
def kitchen_dashboard():
    if not current_user.is_authenticated or current_user.role not in KITCHEN_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
        
    try:
        from sqlalchemy.orm import selectinload
        pending_orders = Order.query.options(selectinload(Order.items)).filter(Order.status == 'PENDING', Order.reservation_id.is_(None)).order_by(Order.created_at.asc()).all()
        preparing_orders = Order.query.options(selectinload(Order.items)).filter(Order.status == 'PREPARING', Order.reservation_id.is_(None)).order_by(Order.created_at.asc()).all()
        # For ready orders, we want to see the last 20
        ready_orders = Order.query.options(selectinload(Order.items)).filter(Order.status == 'READY', Order.reservation_id.is_(None)).order_by(Order.created_at.desc()).limit(20).all()
        
        return render_template('kitchen/dashboard.html',
                               portal_name=f"{current_user.first_name} {current_user.last_name}",
                               pending_orders=pending_orders,
                               preparing_orders=preparing_orders,
                               ready_orders=ready_orders)
    except Exception as e:
        import traceback
        print("ERROR IN KITCHEN DASHBOARD:")
        traceback.print_exc()
        return f"Internal Error: {str(e)}", 500

@kitchen_bp.route('/staff/kitchen/reservations')
def kitchen_reservations():
    if not current_user.is_authenticated or current_user.role not in KITCHEN_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
        
    try:
        from sqlalchemy.orm import selectinload
        # Fetching pre-orders linked to a reservation, ordered by the reservation date/time
        # We join Reservation to order by date
        from models import Reservation
        reserve_orders = Order.query.options(selectinload(Order.items)).join(Reservation).filter(
            Order.reservation_id.isnot(None),
            ~Order.status.in_(['COMPLETED', 'CANCELLED'])
        ).order_by(Reservation.date.asc(), Reservation.time.asc()).all()
        
        return render_template('kitchen/reservations.html',
                               portal_name=f"{current_user.first_name} {current_user.last_name}",
                               reserve_orders=reserve_orders)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Internal Error: {str(e)}", 500

@kitchen_bp.route('/staff/kitchen/update/<int:order_id>', methods=['POST'])
@login_required
def kitchen_update_order(order_id):
    if current_user.role not in KITCHEN_ROLES:
        flash("Unauthorized", "error")
        return redirect(url_for('main.index'))
        
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    
    # Statuses allowed by kitchen: PREPARING, READY, COMPLETED
    if new_status in ['PREPARING', 'READY', 'COMPLETED']:
        # Auto-deduct ingredients when order moves to PREPARING
        if new_status == 'PREPARING' and order.status != 'PREPARING':
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

                deduction_by_ingredient_id = defaultdict(float)
                for oi in order_items:
                    for rr in recipes_by_menu_item_id.get(oi.menu_item_id, []):
                        deduction_by_ingredient_id[rr.ingredient_id] += float(rr.quantity_needed) * oi.quantity

                ingredients = Ingredient.query.filter(Ingredient.id.in_(ingredient_ids)).all()
                ingredients_by_id = {ing.id: ing for ing in ingredients}

                for ing_id, deduction in deduction_by_ingredient_id.items():
                    ing = ingredients_by_id.get(ing_id)
                    if ing:
                        # Deduct from KITCHEN stock, not warehouse stock
                        ing.kitchen_qty = max(0.0, float(ing.kitchen_qty or 0) - float(deduction))
                        
                        # Sync availability for this ingredient (checks kitchen stock)
                        # We do this logic inline here as the helper isn't exported
                        links = MenuItemIngredient.query.filter_by(ingredient_id=ing.id).all()
                        for link in links:
                            mi = MenuItem.query.get(link.menu_item_id)
                            if mi:
                                can_make = True
                                for recipe_item in mi.ingredients:
                                    qty_in_kitchen = float(recipe_item.ingredient.kitchen_qty or 0)
                                    qty_needed = float(recipe_item.quantity_needed or 0)
                                    if qty_in_kitchen < qty_needed:
                                        can_make = False
                                        break
                                mi.is_available = can_make
            
            order.prep_start_at = get_ph_time()
            
        if new_status in ['READY', 'COMPLETED']:
            order.prep_end_at = get_ph_time()
            
        order.status = new_status
        db.session.commit()
        
        # Notify via SocketIO if available
        try:
            from extensions import socketio
            socketio.emit('order_status_update', {'id': order.id, 'status': new_status}, namespace='/')
        except:
            pass
            
        flash(f"Order #{order.id} updated to {new_status}.", "success")
        
    return redirect(url_for('kitchen_portal.kitchen_dashboard'))

@kitchen_bp.route('/staff/kitchen/pantry')
def kitchen_pantry():
    if not current_user.is_authenticated or current_user.role not in KITCHEN_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    from itertools import groupby
    ingredients = Ingredient.query.order_by(Ingredient.category, Ingredient.name).all()
    grouped_ingredients = {}
    for category, group in groupby(ingredients, lambda x: x.category or 'General'):
        grouped_ingredients[category] = list(group)
        
    return render_template('kitchen/pantry.html', 
                           grouped_ingredients=grouped_ingredients,
                           portal_name=f"{current_user.first_name} {current_user.last_name}")

@kitchen_bp.route('/staff/kitchen/recipes')
def kitchen_recipes():
    if not current_user.is_authenticated or current_user.role not in KITCHEN_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    from itertools import groupby
    all_menu_items = MenuItem.query.filter_by(is_deleted=False).order_by(MenuItem.category, MenuItem.name).all()
    grouped_items = {}
    for category, group in groupby(all_menu_items, lambda x: x.category or 'General'):
        grouped_items[category] = list(group)
        
    menu_categories = [r[0] for r in db.session.query(MenuItem.category).filter(MenuItem.is_deleted == False).distinct().order_by(MenuItem.category).all()]
    
    return render_template('kitchen/recipes.html',
                           portal_name=f"{current_user.first_name} {current_user.last_name}",
                           grouped_items=grouped_items,
                           menu_categories=menu_categories)

@kitchen_bp.route('/staff/kitchen/pantry/update', methods=['POST'])
def kitchen_update_pantry():
    if not current_user.is_authenticated or current_user.role not in KITCHEN_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    ing_id = request.form.get('ingredient_id', type=int)
    new_qty = request.form.get('kitchen_qty', type=float)
    
    if ing_id is not None and new_qty is not None:
        ing = Ingredient.query.get(ing_id)
        if ing:
            ing.kitchen_qty = new_qty
            db.session.commit()
            flash(f"Updated {ing.name} kitchen stock to {new_qty} {ing.unit}.", "success")
            
    return redirect(url_for('kitchen_portal.kitchen_pantry'))

@kitchen_bp.route('/staff/kitchen/pantry/emergency-fill', methods=['POST'])
def kitchen_emergency_fill():
    if not current_user.is_authenticated or current_user.role not in KITCHEN_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
        
    all_ings = Ingredient.query.all()
    for ing in all_ings:
        ing.kitchen_qty = 100.0 # Emergency baseline to allow testing
        
    db.session.commit()
    flash("Emergency fill completed! All ingredients set to 100.0 for testing.", "warning")
    return redirect(url_for('kitchen_portal.kitchen_pantry'))

@kitchen_bp.route('/staff/kitchen/stock-requests')
def kitchen_stock_requests():
    from routes.admin import stock_requests
    return stock_requests()

@kitchen_bp.route('/kitchen/logout')
def kitchen_logout():
    return redirect(url_for('admin.admin_logout'))

@kitchen_bp.route('/kitchen/forgot-password', methods=['GET', 'POST'])
@kitchen_bp.route('/staff/kitchen/forgot-password', methods=['GET', 'POST'])
def kitchen_forgot_password():
    result = _portal_forgot_password('Kitchen', KITCHEN_ROLES, 'cashier_portal.staff_login', 'kitchen_portal.kitchen_verify_otp')
    if result:
        return result
    return render_template('portal_auth/forgot_password.html', portal='Kitchen', portal_color='#C62828',
                           form_action=url_for('kitchen_portal.kitchen_forgot_password'),
                           login_url=url_for('cashier_portal.staff_login'))

@kitchen_bp.route('/kitchen/verify-otp/<int:user_id>', methods=['GET', 'POST'])
@kitchen_bp.route('/staff/kitchen/verify-otp/<int:user_id>', methods=['GET', 'POST'])
def kitchen_verify_otp(user_id):
    result = _portal_verify_otp('Kitchen', user_id, 'kitchen_portal.kitchen_forgot_password', 'kitchen_portal.kitchen_reset_password', 'cashier_portal.staff_login')
    if isinstance(result, dict):
        return render_template('portal_auth/verify_otp.html', portal='Kitchen', portal_color='#C62828',
                               user=result['user'], cooldown_remaining=result['cooldown_remaining'],
                               verify_action=url_for('kitchen_portal.kitchen_verify_otp', user_id=user_id),
                               resend_action=url_for('kitchen_portal.kitchen_resend_otp', user_id=user_id),
                               login_url=url_for('cashier_portal.staff_login'))
    return result

@kitchen_bp.route('/kitchen/resend-otp/<int:user_id>', methods=['POST'])
def kitchen_resend_otp(user_id):
    return _portal_resend_otp('Kitchen', user_id, 'kitchen_portal.kitchen_forgot_password', 'kitchen_portal.kitchen_verify_otp')

@kitchen_bp.route('/kitchen/reset-password', methods=['GET', 'POST'])
def kitchen_reset_password():
    result = _portal_reset_password('Kitchen', 'cashier_portal.staff_login')
    if result:
        return result
    return render_template('portal_auth/reset_password.html', portal='Kitchen', portal_color='#C62828',
                           form_action=url_for('kitchen_portal.kitchen_reset_password'),
                           login_url=url_for('cashier_portal.staff_login'))


# ══════════════════════════════════════════════════════════════════
# ── Inventory Portal ──────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════

INVENTORY_ROLES = ['INVENTORY_STAFF', 'INVENTORY', 'ADMIN']

@inventory_bp.route('/inventory/login', methods=['GET', 'POST'])
@inventory_bp.route('/staff/inventory/login', methods=['GET', 'POST'])
def inventory_login():
    # Redirect to unified staff login
    return redirect(url_for('cashier_portal.staff_login'))

@inventory_bp.route('/staff/inventory')
def inventory_dashboard():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
        
    all_ingredients = Ingredient.query.order_by(Ingredient.category, Ingredient.name).all()
    total_items = len(all_ingredients)
    low_stock_count = db.session.query(db.func.count(Ingredient.id)).filter(Ingredient.stock_qty <= Ingredient.reorder_level).scalar()
    
    suppliers = Supplier.query.order_by(Supplier.name).all()
    
    from itertools import groupby
    
    grouped_ingredients = {}
    for category, group in groupby(all_ingredients, lambda x: x.category or 'General'):
        grouped_ingredients[category] = list(group)
        
    return render_template('inventory/dashboard.html',
                           portal_name=f"{current_user.first_name} {current_user.last_name}",
                           total_items=total_items,
                           low_stock=low_stock_count,
                           ingredients=all_ingredients,
                           grouped_ingredients=grouped_ingredients,
                           suppliers=suppliers)

@inventory_bp.route('/staff/inventory/recipes')
def inventory_recipes():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    from itertools import groupby
    all_menu_items = MenuItem.query.filter_by(is_deleted=False).order_by(MenuItem.category, MenuItem.name).all()
    grouped_items = {}
    for category, group in groupby(all_menu_items, lambda x: x.category or 'General'):
        grouped_items[category] = list(group)
        
    menu_categories = [r[0] for r in db.session.query(MenuItem.category).filter(MenuItem.is_deleted == False).distinct().order_by(MenuItem.category).all()]
    
    return render_template('inventory/recipes.html',
                           portal_name=f"{current_user.first_name} {current_user.last_name}",
                           grouped_items=grouped_items,
                           menu_categories=menu_categories)

@inventory_bp.route('/staff/inventory/batches')
def inventory_ingredient_batches():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    from datetime import date
    from sqlalchemy.orm import selectinload
    
    # Pre-fetch data for the staff FIFO dashboard
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    today = date.today()
    batches = (
        IngredientBatch.query.filter_by(is_exhausted=False)
        .options(selectinload(IngredientBatch.ingredient))
        .order_by(IngredientBatch.purchase_date.asc())
        .all()
    )

    menu_categories = [r[0] for r in db.session.query(MenuItem.category)
                       .filter(MenuItem.is_deleted == False)
                       .distinct().order_by(MenuItem.category).all()]

    # Mapping ingredients to their menu categories for client-side filtering
    ing_menu_cats = {}
    for ing in ingredients:
        cats = db.session.query(MenuItem.category).join(MenuItemIngredient, MenuItem.id == MenuItemIngredient.menu_item_id).filter(
            MenuItemIngredient.ingredient_id == ing.id
        ).distinct().all()
        ing_menu_cats[ing.id] = [c[0] for c in cats if c[0]]

    return render_template('staff/batches.html',
                           batches=batches,
                           ingredients=ingredients,
                           today=today,
                           menu_categories=menu_categories,
                           ing_menu_cats=ing_menu_cats)


@inventory_bp.route('/staff/inventory/batches/add', methods=['POST'])
def inventory_add_ingredient_batch():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
        
    ing_id = request.form.get('ingredient_id', type=int)
    batch_qty = request.form.get('batch_qty', type=float)
    cost = request.form.get('cost_per_unit', type=float, default=0.0)
    exp_date_str = request.form.get('expiration_date')
    
    from datetime import datetime
    exp_date = None
    if exp_date_str:
        try:
            exp_date = datetime.strptime(exp_date_str, '%Y-%m-%d').date()
        except: pass
        
    from routes.admin import process_fifo_transaction, log_inventory_change
    
    ing = Ingredient.query.get_or_404(ing_id)
    prev_stock = float(ing.stock_qty)
    ing.stock_qty = prev_stock + batch_qty
    
    # 1. Log overall inventory
    log_inventory_change(ing.id, 'ADD', batch_qty, prev_stock, "Manual Batch Receipt (Portal)")
    
    # 2. Process FIFO logic (Creates the individual batch record)
    process_fifo_transaction(ing.id, 'ADD', batch_qty, cost_per_unit=cost, expiration_date=exp_date)
    
    db.session.commit()
    flash(f"Inventory record updated. {batch_qty} {ing.unit} added to FIFO queue.", "success")
    return redirect(url_for('inventory_portal.inventory_ingredient_batches'))

@inventory_bp.route('/staff/inventory/full')
def inventory_full():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    # We fetch all ingredients to allow for instant client-side filtering as requested
    all_ingredients = Ingredient.query.order_by(Ingredient.category, Ingredient.name).all()
    
    # Get all unique categories for the filter buttons
    categories = [r[0] for r in db.session.query(Ingredient.category).distinct().all() if r[0]]
    
    suppliers = Supplier.query.order_by(Supplier.name).all()
    
    return render_template('inventory/full.html', 
                           ingredients=all_ingredients,
                           categories=categories,
                           suppliers=suppliers,
                           portal_name=f"{current_user.first_name} {current_user.last_name}")

@inventory_bp.route('/staff/inventory/suppliers')
def inventory_suppliers():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    from collections import defaultdict
    suppliers_list = Supplier.query.order_by(Supplier.name).all()
    
    # Enrich suppliers with category metadata (matching admin logic to satisfy template)
    sup_ids = [s.id for s in suppliers_list]
    if sup_ids:
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
            
        for sup in suppliers_list:
            # The template uses sup.category, so we pick the first one if available
            mapped_cats = cats_by_sup.get(sup.id, [])
            sup.category = mapped_cats[0] if mapped_cats else "General"
    
    return render_template('inventory/suppliers.html', 
                           suppliers=suppliers_list,
                           portal_name=f"{current_user.first_name} {current_user.last_name}")

@inventory_bp.route('/staff/inventory/ingredients/add', methods=['POST'])
def inventory_add_ingredient():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    name = request.form.get('name', '').strip()
    unit = request.form.get('unit', 'grams')
    category = request.form.get('category', 'General')
    stock_qty = request.form.get('stock_qty', 0, type=float)
    reorder_level = request.form.get('reorder_level', 0, type=float)
    cost_per_unit = request.form.get('cost_per_unit', 0, type=float)
    supplier_id = request.form.get('supplier_id', type=int)
    expiration_date_str = request.form.get('expiration_date')
    
    expiration_date = None
    if expiration_date_str:
        try:
            from datetime import datetime
            expiration_date = datetime.strptime(expiration_date_str, '%Y-%m-%d')
        except:
            pass
            
    if not name:
        flash('Ingredient name is required.', 'danger')
        return redirect(url_for('inventory_portal.inventory_dashboard'))
        
    ing = Ingredient(
        name=name, unit=unit, category=category, 
        stock_qty=stock_qty, reorder_level=reorder_level,
        cost_per_unit=cost_per_unit, supplier_id=supplier_id,
        expiration_date=expiration_date
    )
    db.session.add(ing)
    db.session.commit()
    flash(f'Ingredient "{name}" added successfully!', 'success')
    return redirect(url_for('inventory_portal.inventory_full'))

@inventory_bp.route('/staff/inventory/ingredients/edit/<int:ing_id>', methods=['POST'])
def inventory_edit_ingredient(ing_id):
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    ing = Ingredient.query.get_or_404(ing_id)
    
    name = request.form.get('name', '').strip()
    category = request.form.get('category', 'General')
    reorder_level = request.form.get('reorder_level', 0, type=float)
    
    if not name:
        flash('Ingredient name is required.', 'danger')
        return redirect(url_for('inventory_portal.inventory_full'))
        
    ing.name = name
    ing.category = category
    ing.reorder_level = reorder_level
    
    db.session.commit()
    flash(f'Changes saved for "{name}".', 'success')
    return redirect(url_for('inventory_portal.inventory_full'))

@inventory_bp.route('/staff/inventory/suppliers/add', methods=['POST'])
def inventory_add_supplier():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
        
    name = request.form.get('name', '').strip()
    contact_person = request.form.get('contact_person', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    address = request.form.get('address', '').strip()
    
    if not name:
        flash('Supplier name is required.', 'danger')
        return redirect(url_for('inventory_portal.inventory_suppliers'))
        
    sup = Supplier(name=name, contact_person=contact_person, phone=phone, email=email, address=address)
    db.session.add(sup)
    db.session.commit()
    
    new_ingredients_str = request.form.get('new_ingredients', '').strip()
    if new_ingredients_str:
        sup.catalog_items = new_ingredients_str
        db.session.commit()
        
    flash(f'Supplier "{name}" added successfully!', 'success')
    return redirect(url_for('inventory_portal.inventory_suppliers'))

@inventory_bp.route('/staff/inventory/ingredients/restock/<int:ing_id>', methods=['POST'])
def inventory_restock(ing_id):
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    ing = Ingredient.query.get_or_404(ing_id)
    add_qty = request.form.get('add_qty', 0, type=float)
    if add_qty > 0:
        ing.stock_qty += add_qty
        db.session.commit()
        flash(f'Restocked {add_qty} {ing.unit} to {ing.name}.', 'success')
    return redirect(url_for('inventory_portal.inventory_dashboard'))

@inventory_bp.route('/staff/inventory/ingredients/waste/add', methods=['POST'])
def inventory_add_waste():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
        
    ing_id = request.form.get('ingredient_id', type=int)
    qty = request.form.get('quantity_wasted', type=float)
    reason = request.form.get('reason', 'Other')
    notes = request.form.get('notes', '').strip()
    
    from routes.admin import log_inventory_change, process_fifo_transaction
    
    ing = Ingredient.query.get_or_404(ing_id)
    prev_stock = float(ing.stock_qty)
    cost_lost = qty * float(ing.cost_per_unit or 0)
    ing.stock_qty = max(0, prev_stock - qty)
    
    # 1. Log change and update FIFO
    log_inventory_change(ing.id, 'WASTE', qty, prev_stock, f"Waste Recorded: {reason}")
    process_fifo_transaction(ing.id, 'WASTE', qty)
    
    waste = WasteRecord(
        ingredient_id=ing_id,
        quantity_wasted=qty,
        reason=reason,
        notes=notes,
        cost_lost=cost_lost,
        recorded_by_id=current_user.id
    )
    db.session.add(waste)
    db.session.commit()
    
    flash(f'Recorded waste for {ing.name}.', 'warning')
    return redirect(url_for('inventory_portal.inventory_dashboard'))


@inventory_bp.route('/staff/inventory/waste')
def inventory_waste_records():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    waste_records_list = WasteRecord.query.order_by(WasteRecord.created_at.desc()).limit(100).all()
    return render_template('inventory/waste.html', 
                           waste_records=waste_records_list,
                           portal_name=f"{current_user.first_name} {current_user.last_name}")

@inventory_bp.route('/staff/inventory/stock-requests')
def inventory_stock_requests():
    from routes.admin import stock_requests
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    return stock_requests()

@inventory_bp.route('/staff/inventory/audit')
def inventory_audit():
    from routes.admin import inventory_audit
    return inventory_audit()

@inventory_bp.route('/staff/inventory/suppliers/<int:sup_id>/ingredients')
def supplier_ingredients_api(sup_id):
    """API: Return all ingredients linked to a supplier as JSON (for the receive modal)."""
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    
    ingredients = Ingredient.query.filter_by(supplier_id=sup_id).order_by(Ingredient.category, Ingredient.name).all()
    result = []
    for ing in ingredients:
        result.append({
            'id': ing.id,
            'name': ing.name,
            'unit': ing.unit,
            'category': ing.category or 'General',
            'stock_qty': float(ing.stock_qty),
            'cost_per_unit': float(ing.cost_per_unit or 0),
        })
    return jsonify({'success': True, 'ingredients': result})

@inventory_bp.route('/staff/inventory/suppliers/<int:sup_id>/receive', methods=['POST'])
def supplier_receive_delivery(sup_id):
    """Process a supply delivery: add stock to warehouse inventory for each received ingredient."""
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    
    from routes.admin import log_inventory_change, process_fifo_transaction
    
    supplier = Supplier.query.get_or_404(sup_id)
    data = request.get_json()
    
    if not data or 'items' not in data:
        return jsonify({'success': False, 'message': 'No items provided.'})
    
    received_items = data['items']  # list of {ingredient_id, qty_received}
    total_received = 0
    details = []
    
    for item in received_items:
        ing_id = item.get('ingredient_id')
        qty = float(item.get('qty_received', 0))
        
        if qty <= 0:
            continue
            
        ing = Ingredient.query.get(ing_id)
        if not ing or ing.supplier_id != sup_id:
            continue
        
        # 1. Update overall stock
        prev_stock = float(ing.stock_qty)
        ing.stock_qty = prev_stock + qty
        log_inventory_change(ing.id, 'ADD', qty, prev_stock, f'Supply Received from {supplier.name}')
        
        # 2. Create FIFO Batch
        process_fifo_transaction(ing.id, 'ADD', qty)
        
        total_received += 1
        details.append(f'+{qty} {ing.unit} {ing.name}')
    
    if total_received == 0:
        return jsonify({'success': False, 'message': 'No valid items to receive. Please enter quantities.'})
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'✅ Received {total_received} item(s) from {supplier.name}!',
        'details': details
    })

@inventory_bp.route('/inventory/logout')
def inventory_logout():
    return redirect(url_for('admin.admin_logout'))

@inventory_bp.route('/inventory/forgot-password', methods=['GET', 'POST'])
@inventory_bp.route('/staff/inventory/forgot-password', methods=['GET', 'POST'])
def inventory_forgot_password():
    result = _portal_forgot_password('Inventory', INVENTORY_ROLES, 'cashier_portal.staff_login', 'inventory_portal.inventory_verify_otp')
    if result:
        return result
    return render_template('portal_auth/forgot_password.html', portal='Inventory', portal_color='#2E7D32',
                           form_action=url_for('inventory_portal.inventory_forgot_password'),
                           login_url=url_for('cashier_portal.staff_login'))

@inventory_bp.route('/inventory/verify-otp/<int:user_id>', methods=['GET', 'POST'])
@inventory_bp.route('/staff/inventory/verify-otp/<int:user_id>', methods=['GET', 'POST'])
def inventory_verify_otp(user_id):
    result = _portal_verify_otp('Inventory', user_id, 'inventory_portal.inventory_forgot_password', 'inventory_portal.inventory_reset_password', 'cashier_portal.staff_login')
    if isinstance(result, dict):
        return render_template('portal_auth/verify_otp.html', portal='Inventory', portal_color='#2E7D32',
                               user=result['user'], cooldown_remaining=result['cooldown_remaining'],
                               verify_action=url_for('inventory_portal.inventory_verify_otp', user_id=user_id),
                               resend_action=url_for('inventory_portal.inventory_resend_otp', user_id=user_id),
                               login_url=url_for('cashier_portal.staff_login'))
    return result

@inventory_bp.route('/inventory/resend-otp/<int:user_id>', methods=['POST'])
def inventory_resend_otp(user_id):
    return _portal_resend_otp('Inventory', user_id, 'inventory_portal.inventory_forgot_password', 'inventory_portal.inventory_verify_otp')

@inventory_bp.route('/inventory/reset-password', methods=['GET', 'POST'])
def inventory_reset_password():
    result = _portal_reset_password('Inventory', 'cashier_portal.staff_login')
    if result:
        return result
    return render_template('portal_auth/reset_password.html', portal='Inventory', portal_color='#2E7D32',
                           form_action=url_for('inventory_portal.inventory_reset_password'),
                           login_url=url_for('cashier_portal.staff_login'))


# ══════════════════════════════════════════════════════════════════
# ── Shared Staff Profile Handler ─────────────────────────────────
# ══════════════════════════════════════════════════════════════════

def _handle_profile_post(user):
    """Shared handler for profile update and password change POST requests."""
    form_type = request.form.get('form_type')
    
    if form_type == 'profile':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        phone_number = request.form.get('phone_number', '').strip()
        
        if not first_name or not last_name:
            flash('First name and last name are required.', 'danger')
            return False
        
        user.first_name = first_name
        user.last_name = last_name
        user.phone_number = phone_number if phone_number else None
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return True
        
    elif form_type == 'password':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not user.check_password(current_password):
            flash('Current password is incorrect.', 'danger')
            return False
        
        err = validate_password(new_password, confirm_password)
        if err:
            flash(err, 'danger')
            return False
        
        user.set_password(new_password)
        db.session.commit()
        flash('Password changed successfully!', 'success')
        return True
    
    return False


# ── Kitchen Profile ──
@kitchen_bp.route('/staff/kitchen/profile', methods=['GET', 'POST'])
def kitchen_profile():
    if not current_user.is_authenticated or current_user.role not in KITCHEN_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    if request.method == 'POST':
        _handle_profile_post(current_user)
        return redirect(url_for('kitchen_portal.kitchen_profile'))
    
    sidebar_items = [
        {'url': url_for('kitchen_portal.kitchen_dashboard'), 'icon': 'fire', 'label': 'Order Board'},
        {'url': url_for('kitchen_portal.kitchen_pantry'), 'icon': 'archive', 'label': 'Kitchen Pantry'},
    ]
    ref_items = [
        {'url': url_for('kitchen_portal.kitchen_recipes'), 'icon': 'utensils', 'label': 'Menu Recipes'},
        {'url': url_for('kitchen_portal.kitchen_stock_requests'), 'icon': 'file-invoice', 'label': 'Stock Requests'},
    ]
    
    return render_template('staff/profile.html',
                           portal_label='Kitchen',
                           role_label='Kitchen Staff',
                           logout_url=url_for('kitchen_portal.kitchen_logout'),
                           profile_action=url_for('kitchen_portal.kitchen_profile'),
                           sidebar_items=sidebar_items,
                           ref_items=ref_items)


# ── Inventory Profile ──
@inventory_bp.route('/staff/inventory/profile', methods=['GET', 'POST'])
def inventory_profile():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    if request.method == 'POST':
        _handle_profile_post(current_user)
        return redirect(url_for('inventory_portal.inventory_profile'))
    
    sidebar_items = [
        {'url': url_for('inventory_portal.inventory_dashboard'), 'icon': 'boxes-stacked', 'label': 'Stock Levels'},
        {'url': url_for('inventory_portal.inventory_full'), 'icon': 'warehouse', 'label': 'Full Inventory'},
        {'url': url_for('inventory_portal.inventory_suppliers'), 'icon': 'truck', 'label': 'Suppliers'},
        {'url': url_for('inventory_portal.inventory_waste_records'), 'icon': 'trash-can', 'label': 'Waste Log'},
        {'url': url_for('inventory_portal.inventory_stock_requests'), 'icon': 'file-invoice', 'label': 'Stock Requests'},
    ]
    ref_items = [
        {'url': url_for('inventory_portal.inventory_recipes'), 'icon': 'utensils', 'label': 'Menu Recipes'},
    ]
    
    return render_template('staff/profile.html',
                           portal_label='Inventory',
                           role_label='Inventory Staff',
                           logout_url=url_for('inventory_portal.inventory_logout'),
                           profile_action=url_for('inventory_portal.inventory_profile'),
                           sidebar_items=sidebar_items,
                           ref_items=ref_items)


# ── Cashier Profile ──
@cashier_bp.route('/staff/cashier/profile', methods=['GET', 'POST'])
def cashier_profile():
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    if request.method == 'POST':
        _handle_profile_post(current_user)
        return redirect(url_for('cashier_portal.cashier_profile'))
    
    sidebar_items = [
        {'url': url_for('cashier_portal.cashier_dashboard'), 'icon': 'shopping-bag', 'label': 'Orders'},
        {'url': url_for('cashier_portal.cashier_walkin_order'), 'icon': 'walking', 'label': 'Walk-In Order'},
        {'url': url_for('cashier_portal.cashier_billing'), 'icon': 'file-invoice-dollar', 'label': 'Billing'},
        {'url': url_for('cashier_portal.cashier_orders_history'), 'icon': 'clock-rotate-left', 'label': 'Order History'},
        {'url': url_for('cashier_portal.cashier_chats'), 'icon': 'comments', 'label': 'Customer Chat'},
    ]
    
    return render_template('staff/profile.html',
                           portal_label='Cashier',
                           role_label='Cashier Staff',
                           logout_url=url_for('cashier_portal.cashier_logout'),
                           profile_action=url_for('cashier_portal.cashier_profile'),
                           sidebar_items=sidebar_items,
                           ref_items=[])


# ══════════════════════════════════════════════════════════════════
# ── Rider Portal ────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════

RIDER_ROLES = ['RIDER', 'ADMIN', 'CASHIER', 'STAFF']

@rider_bp.route('/rider/login', methods=['GET', 'POST'])
@rider_bp.route('/staff/rider/login', methods=['GET', 'POST'])
def rider_login():
    if current_user.is_authenticated and current_user.role in RIDER_ROLES:
        return redirect(url_for('rider_portal.rider_dashboard'))
        
    if request.method == 'POST':
        user = _authenticate_portal(request.form.get('email'), request.form.get('password'), RIDER_ROLES)
        if user:
            session['logged_in_portal'] = 'rider'
            login_user(user)
            return redirect(url_for('rider_portal.rider_dashboard'))
        flash('Invalid credentials or insufficient permissions for Rider Portal.', 'error')
    return render_template('rider/login.html')

@rider_bp.route('/staff/rider')
def rider_dashboard():
    from routes.admin import deliveries
    if not current_user.is_authenticated or current_user.role not in RIDER_ROLES:
        return redirect(url_for('rider_portal.rider_login'))
    return deliveries()

@rider_bp.route('/rider/logout')
def rider_logout():
    return redirect(url_for('admin.admin_logout'))

@rider_bp.route('/rider/forgot-password', methods=['GET', 'POST'])
@rider_bp.route('/staff/rider/forgot-password', methods=['GET', 'POST'])
def rider_forgot_password():
    result = _portal_forgot_password('Rider', RIDER_ROLES, 'rider_portal.rider_login', 'rider_portal.rider_verify_otp')
    if result:
        return result
    return render_template('portal_auth/forgot_password.html', portal='Rider', portal_color='#E65100',
                           form_action=url_for('rider_portal.rider_forgot_password'),
                           login_url=url_for('rider_portal.rider_login'))

@rider_bp.route('/rider/verify-otp/<int:user_id>', methods=['GET', 'POST'])
@rider_bp.route('/staff/rider/verify-otp/<int:user_id>', methods=['GET', 'POST'])
def rider_verify_otp(user_id):
    result = _portal_verify_otp('Rider', user_id, 'rider_portal.rider_forgot_password', 'rider_portal.rider_reset_password', 'rider_portal.rider_login')
    if isinstance(result, dict):
        return render_template('portal_auth/verify_otp.html', portal='Rider', portal_color='#E65100',
                               user=result['user'], cooldown_remaining=result['cooldown_remaining'],
                               verify_action=url_for('rider_portal.rider_verify_otp', user_id=user_id),
                               resend_action=url_for('rider_portal.rider_resend_otp', user_id=user_id),
                               login_url=url_for('rider_portal.rider_login'))
    return result

@rider_bp.route('/rider/resend-otp/<int:user_id>', methods=['POST'])
def rider_resend_otp(user_id):
    return _portal_resend_otp('Rider', user_id, 'rider_portal.rider_forgot_password', 'rider_portal.rider_verify_otp')

@rider_bp.route('/rider/reset-password', methods=['GET', 'POST'])
def rider_reset_password():
    result = _portal_reset_password('Rider', 'rider_portal.rider_login')
    if result:
        return result
    return render_template('portal_auth/reset_password.html', portal='Rider', portal_color='#E65100',
                           form_action=url_for('rider_portal.rider_reset_password'),
                           login_url=url_for('rider_portal.rider_login'))
