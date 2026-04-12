from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_user, current_user, login_required
from flask_mail import Message
from models import db, User, Order, Ingredient, MenuItemIngredient, Supplier, WasteRecord
from utils import get_ph_time, validate_password, safe_elapsed
import random
import threading
import traceback

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
# ── Cashier Portal ────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════

CASHIER_ROLES = ['CASHIER', 'STAFF', 'ADMIN']

@cashier_bp.route('/cashier/login', methods=['GET', 'POST'])
def cashier_login():
    if current_user.is_authenticated and current_user.role in CASHIER_ROLES:
        return redirect(url_for('cashier_portal.cashier_dashboard'))
        
    if request.method == 'POST':
        user = _authenticate_portal(request.form.get('email'), request.form.get('password'), CASHIER_ROLES)
        if user:
            session['logged_in_portal'] = 'cashier'
            login_user(user)
            return redirect(url_for('cashier_portal.cashier_dashboard'))
        flash('Invalid credentials or insufficient permissions for Cashier Portal.', 'error')
    return render_template('cashier/login.html')

@cashier_bp.route('/staff/cashier')
def cashier_dashboard():
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return redirect(url_for('cashier_portal.cashier_login'))
    
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
    from routes.admin import walkin_order
    return walkin_order()

@cashier_bp.route('/staff/cashier/billing')
def cashier_billing():
    from routes.admin import billing
    return billing()

@cashier_bp.route('/staff/cashier/history')
def cashier_orders_history():
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return redirect(url_for('cashier_portal.cashier_login'))
    
    page = request.args.get('page', 1, type=int)
    orders_pg = Order.query.order_by(Order.created_at.desc()).paginate(page=page, per_page=20)
    
    return render_template('cashier/orders_history.html', 
                           orders=orders_pg, 
                           portal_name=f"{current_user.first_name} {current_user.last_name}")

@cashier_bp.route('/staff/cashier/chats')
def cashier_chats():
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return redirect(url_for('cashier_portal.cashier_login'))
    from routes.admin import chats
    return chats()

@cashier_bp.route('/cashier/logout')
def cashier_logout():
    return redirect(url_for('admin.admin_logout'))

@cashier_bp.route('/cashier/forgot-password', methods=['GET', 'POST'])
def cashier_forgot_password():
    result = _portal_forgot_password('Cashier', CASHIER_ROLES, 'cashier_portal.cashier_login', 'cashier_portal.cashier_verify_otp')
    if result:
        return result
    return render_template('portal_auth/forgot_password.html', portal='Cashier', portal_color='#16A085',
                           form_action=url_for('cashier_portal.cashier_forgot_password'),
                           login_url=url_for('cashier_portal.cashier_login'))

@cashier_bp.route('/cashier/verify-otp/<int:user_id>', methods=['GET', 'POST'])
def cashier_verify_otp(user_id):
    result = _portal_verify_otp('Cashier', user_id, 'cashier_portal.cashier_forgot_password', 'cashier_portal.cashier_reset_password', 'cashier_portal.cashier_login')
    if isinstance(result, dict):
        return render_template('portal_auth/verify_otp.html', portal='Cashier', portal_color='#16A085',
                               user=result['user'], cooldown_remaining=result['cooldown_remaining'],
                               verify_action=url_for('cashier_portal.cashier_verify_otp', user_id=user_id),
                               resend_action=url_for('cashier_portal.cashier_resend_otp', user_id=user_id),
                               login_url=url_for('cashier_portal.cashier_login'))
    return result

@cashier_bp.route('/cashier/resend-otp/<int:user_id>', methods=['POST'])
def cashier_resend_otp(user_id):
    return _portal_resend_otp('Cashier', user_id, 'cashier_portal.cashier_forgot_password', 'cashier_portal.cashier_verify_otp')

@cashier_bp.route('/cashier/reset-password', methods=['GET', 'POST'])
def cashier_reset_password():
    result = _portal_reset_password('Cashier', 'cashier_portal.cashier_login')
    if result:
        return result
    return render_template('portal_auth/reset_password.html', portal='Cashier', portal_color='#16A085',
                           form_action=url_for('cashier_portal.cashier_reset_password'),
                           login_url=url_for('cashier_portal.cashier_login'))


# ══════════════════════════════════════════════════════════════════
# ── Kitchen Portal ────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════

KITCHEN_ROLES = ['KITCHEN', 'ADMIN', 'CASHIER']

@kitchen_bp.route('/kitchen/login', methods=['GET', 'POST'])
def kitchen_login():
    if current_user.is_authenticated and current_user.role in KITCHEN_ROLES:
        return redirect(url_for('kitchen_portal.kitchen_dashboard'))
        
    if request.method == 'POST':
        user = _authenticate_portal(request.form.get('email'), request.form.get('password'), KITCHEN_ROLES)
        if user:
            session['logged_in_portal'] = 'kitchen'
            login_user(user)
            return redirect(url_for('kitchen_portal.kitchen_dashboard'))
        flash('Invalid credentials or insufficient permissions for Kitchen Portal.', 'error')
    return render_template('kitchen view/login.html')

@kitchen_bp.route('/staff/kitchen')
def kitchen_dashboard():
    if not current_user.is_authenticated or current_user.role not in KITCHEN_ROLES:
        return redirect(url_for('kitchen_portal.kitchen_login'))
        
    # Required by templates/kitchen/dashboard.html:
    # pending_orders, preparing_orders, ready_orders
    
    pending_orders = Order.query.filter_by(status='PENDING').order_by(Order.created_at.asc()).all()
    preparing_orders = Order.query.filter_by(status='PREPARING').order_by(Order.created_at.asc()).all()
    # If the system uses COMPLETED as "done from kitchen", we use it for Ready column
    # But if it uses READY, we fetch those. We'll fetch both to be safe or just READY if we implement it.
    ready_orders = Order.query.filter_by(status='READY').order_by(Order.created_at.desc()).limit(20).all()
    
    return render_template('kitchen/dashboard.html',
                           portal_name=f"{current_user.first_name} {current_user.last_name}",
                           pending_orders=pending_orders,
                           preparing_orders=preparing_orders,
                           ready_orders=ready_orders)

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
                        ing.stock_qty = max(0.0, float(ing.stock_qty) - float(deduction))
            
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
        return redirect(url_for('kitchen_portal.kitchen_login'))
    
    from itertools import groupby
    ingredients = Ingredient.query.order_by(Ingredient.category, Ingredient.name).all()
    grouped_ingredients = {}
    for category, group in groupby(ingredients, lambda x: x.category or 'General'):
        grouped_ingredients[category] = list(group)
        
    return render_template('kitchen/pantry.html', 
                           grouped_ingredients=grouped_ingredients,
                           portal_name=f"{current_user.first_name} {current_user.last_name}")

@kitchen_bp.route('/staff/kitchen/stock-requests')
def kitchen_stock_requests():
    from routes.admin import stock_requests
    return stock_requests()

@kitchen_bp.route('/kitchen/logout')
def kitchen_logout():
    return redirect(url_for('admin.admin_logout'))

@kitchen_bp.route('/kitchen/forgot-password', methods=['GET', 'POST'])
def kitchen_forgot_password():
    result = _portal_forgot_password('Kitchen', KITCHEN_ROLES, 'kitchen_portal.kitchen_login', 'kitchen_portal.kitchen_verify_otp')
    if result:
        return result
    return render_template('portal_auth/forgot_password.html', portal='Kitchen', portal_color='#C62828',
                           form_action=url_for('kitchen_portal.kitchen_forgot_password'),
                           login_url=url_for('kitchen_portal.kitchen_login'))

@kitchen_bp.route('/kitchen/verify-otp/<int:user_id>', methods=['GET', 'POST'])
def kitchen_verify_otp(user_id):
    result = _portal_verify_otp('Kitchen', user_id, 'kitchen_portal.kitchen_forgot_password', 'kitchen_portal.kitchen_reset_password', 'kitchen_portal.kitchen_login')
    if isinstance(result, dict):
        return render_template('portal_auth/verify_otp.html', portal='Kitchen', portal_color='#C62828',
                               user=result['user'], cooldown_remaining=result['cooldown_remaining'],
                               verify_action=url_for('kitchen_portal.kitchen_verify_otp', user_id=user_id),
                               resend_action=url_for('kitchen_portal.kitchen_resend_otp', user_id=user_id),
                               login_url=url_for('kitchen_portal.kitchen_login'))
    return result

@kitchen_bp.route('/kitchen/resend-otp/<int:user_id>', methods=['POST'])
def kitchen_resend_otp(user_id):
    return _portal_resend_otp('Kitchen', user_id, 'kitchen_portal.kitchen_forgot_password', 'kitchen_portal.kitchen_verify_otp')

@kitchen_bp.route('/kitchen/reset-password', methods=['GET', 'POST'])
def kitchen_reset_password():
    result = _portal_reset_password('Kitchen', 'kitchen_portal.kitchen_login')
    if result:
        return result
    return render_template('portal_auth/reset_password.html', portal='Kitchen', portal_color='#C62828',
                           form_action=url_for('kitchen_portal.kitchen_reset_password'),
                           login_url=url_for('kitchen_portal.kitchen_login'))


# ══════════════════════════════════════════════════════════════════
# ── Inventory Portal ──────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════

INVENTORY_ROLES = ['INVENTORY_STAFF', 'INVENTORY', 'ADMIN']

@inventory_bp.route('/inventory/login', methods=['GET', 'POST'])
def inventory_login():
    if current_user.is_authenticated and current_user.role in INVENTORY_ROLES:
        return redirect(url_for('inventory_portal.inventory_dashboard'))
        
    if request.method == 'POST':
        user = _authenticate_portal(request.form.get('email'), request.form.get('password'), INVENTORY_ROLES)
        if user:
            session['logged_in_portal'] = 'inventory'
            login_user(user)
            return redirect(url_for('inventory_portal.inventory_dashboard'))
        flash('Invalid credentials or insufficient permissions for Inventory Portal.', 'error')
    return render_template('inventory/login.html')

@inventory_bp.route('/staff/inventory')
def inventory_dashboard():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('inventory_portal.inventory_login'))
        
    # Required by templates/inventory/dashboard.html:
    # total_items, low_stock, ingredients
    
    all_ingredients = Ingredient.query.order_by(Ingredient.name).all()
    total_items = len(all_ingredients)
    low_stock_count = Ingredient.query.filter(Ingredient.stock_qty <= Ingredient.reorder_level).count()
    
    return render_template('inventory/dashboard.html',
                           portal_name=f"{current_user.first_name} {current_user.last_name}",
                           total_items=total_items,
                           low_stock=low_stock_count,
                           ingredients=all_ingredients)

@inventory_bp.route('/staff/inventory/batches')
def inventory_ingredient_batches():
    from routes.admin import ingredient_batches
    return ingredient_batches()

@inventory_bp.route('/staff/inventory/full')
def inventory_full():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('inventory_portal.inventory_login'))
    
    from collections import defaultdict
    page = request.args.get('page', 1, type=int)
    ingredients_pg = Ingredient.query.order_by(Ingredient.category, Ingredient.name).paginate(page=page, per_page=50)
    
    return render_template('inventory/full.html', 
                           ingredients=ingredients_pg,
                           portal_name=f"{current_user.first_name} {current_user.last_name}")

@inventory_bp.route('/staff/inventory/suppliers')
def inventory_suppliers():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('inventory_portal.inventory_login'))
    
    suppliers_list = Supplier.query.order_by(Supplier.name).all()
    return render_template('inventory/suppliers.html', 
                           suppliers=suppliers_list,
                           portal_name=f"{current_user.first_name} {current_user.last_name}")

@inventory_bp.route('/staff/inventory/waste')
def inventory_waste_records():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('inventory_portal.inventory_login'))
    
    waste_records_list = WasteRecord.query.order_by(WasteRecord.created_at.desc()).limit(100).all()
    return render_template('inventory/waste.html', 
                           waste_records=waste_records_list,
                           portal_name=f"{current_user.first_name} {current_user.last_name}")

@inventory_bp.route('/staff/inventory/stock-requests')
def inventory_stock_requests():
    from routes.admin import stock_requests
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('inventory_portal.inventory_login'))
    return stock_requests()

@inventory_bp.route('/staff/inventory/audit')
def inventory_audit():
    from routes.admin import inventory_audit
    return inventory_audit()

@inventory_bp.route('/inventory/logout')
def inventory_logout():
    return redirect(url_for('admin.admin_logout'))

@inventory_bp.route('/inventory/forgot-password', methods=['GET', 'POST'])
def inventory_forgot_password():
    result = _portal_forgot_password('Inventory', INVENTORY_ROLES, 'inventory_portal.inventory_login', 'inventory_portal.inventory_verify_otp')
    if result:
        return result
    return render_template('portal_auth/forgot_password.html', portal='Inventory', portal_color='#2E7D32',
                           form_action=url_for('inventory_portal.inventory_forgot_password'),
                           login_url=url_for('inventory_portal.inventory_login'))

@inventory_bp.route('/inventory/verify-otp/<int:user_id>', methods=['GET', 'POST'])
def inventory_verify_otp(user_id):
    result = _portal_verify_otp('Inventory', user_id, 'inventory_portal.inventory_forgot_password', 'inventory_portal.inventory_reset_password', 'inventory_portal.inventory_login')
    if isinstance(result, dict):
        return render_template('portal_auth/verify_otp.html', portal='Inventory', portal_color='#2E7D32',
                               user=result['user'], cooldown_remaining=result['cooldown_remaining'],
                               verify_action=url_for('inventory_portal.inventory_verify_otp', user_id=user_id),
                               resend_action=url_for('inventory_portal.inventory_resend_otp', user_id=user_id),
                               login_url=url_for('inventory_portal.inventory_login'))
    return result

@inventory_bp.route('/inventory/resend-otp/<int:user_id>', methods=['POST'])
def inventory_resend_otp(user_id):
    return _portal_resend_otp('Inventory', user_id, 'inventory_portal.inventory_forgot_password', 'inventory_portal.inventory_verify_otp')

@inventory_bp.route('/inventory/reset-password', methods=['GET', 'POST'])
def inventory_reset_password():
    result = _portal_reset_password('Inventory', 'inventory_portal.inventory_login')
    if result:
        return result
    return render_template('portal_auth/reset_password.html', portal='Inventory', portal_color='#2E7D32',
                           form_action=url_for('inventory_portal.inventory_reset_password'),
                           login_url=url_for('inventory_portal.inventory_login'))


# ══════════════════════════════════════════════════════════════════
# ── Rider Portal ────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════

RIDER_ROLES = ['RIDER', 'ADMIN', 'CASHIER', 'STAFF']

@rider_bp.route('/rider/login', methods=['GET', 'POST'])
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
def rider_forgot_password():
    result = _portal_forgot_password('Rider', RIDER_ROLES, 'rider_portal.rider_login', 'rider_portal.rider_verify_otp')
    if result:
        return result
    return render_template('portal_auth/forgot_password.html', portal='Rider', portal_color='#E65100',
                           form_action=url_for('rider_portal.rider_forgot_password'),
                           login_url=url_for('rider_portal.rider_login'))

@rider_bp.route('/rider/verify-otp/<int:user_id>', methods=['GET', 'POST'])
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
