from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from flask_login import login_user, current_user, login_required
from flask_mail import Message
from models import db, User, Order, OrderItem, Ingredient, MenuItemIngredient, Supplier, WasteRecord, MenuItem, IngredientBatch
from sqlalchemy import func
from utils import get_ph_time, validate_password, safe_elapsed
import random
import threading
import traceback
from collections import defaultdict
from itertools import groupby

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
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if not user or not user.role or user.role.upper() not in allowed_roles:
            msg = f"If an account exists for {email}, a reset code has been sent."
            if is_ajax:
                return jsonify({'success': True, 'redirect': url_for(login_url_name), 'message': msg})
            flash(msg, "info")
            return redirect(url_for(login_url_name))

        if user.otp_created_at:
            elapsed = safe_elapsed(user.otp_created_at)
            if elapsed < 60:
                msg = f"Please wait {int(60 - elapsed)}s before requesting a new code."
                if is_ajax:
                    return jsonify({'success': False, 'message': msg})
                flash(msg, "warning")
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
        if is_ajax:
            return jsonify({'success': True, 'redirect': url_for(verify_url_name, user_id=user.id)})
        return redirect(url_for(verify_url_name, user_id=user.id))

    return None  # Let caller render template


def _portal_verify_otp(portal_name, user_id, forgot_url_name, reset_url_name, login_url_name):
    """
    Reusable OTP verification handler for all portals.
    Step 2: Accept OTP code, verify against DB.
    """
    session_key = f'{portal_name.lower()}_reset_user_id'
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if session.get(session_key) != user_id:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Invalid session.'}), 400
        flash("Invalid session.", "danger")
        return redirect(url_for(forgot_url_name))

    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        otp_input = request.form.get('otp', '').strip()
        if user.otp_created_at and safe_elapsed(user.otp_created_at) > 300:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Code expired. Please request a new one.'}), 400
            flash("Code expired. Please request a new one.", "danger")
            return redirect(url_for(forgot_url_name))

        if user.otp_code == otp_input:
            session[f'{portal_name.lower()}_reset_verified_id'] = user.id
            if is_ajax:
                return jsonify({'success': True, 'redirect': url_for(reset_url_name)})
            flash("Code verified. Set your new password.", "success")
            return redirect(url_for(reset_url_name))
        else:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Invalid code.'}), 400
            flash("Invalid code.", "danger")

    cooldown = 0
    if user.otp_created_at:
        cooldown = max(0, int(60 - safe_elapsed(user.otp_created_at)))

    return {'user': user, 'cooldown_remaining': cooldown}


def _portal_resend_otp(portal_name, user_id, forgot_url_name, verify_url_name):
    """Resend OTP for any portal."""
    session_key = f'{portal_name.lower()}_reset_user_id'
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if session.get(session_key) != user_id:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Invalid session.'}), 400
        return redirect(url_for(forgot_url_name))

    user = User.query.get_or_404(user_id)
    if user.otp_created_at and safe_elapsed(user.otp_created_at) < 60:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Please wait before requesting a new code.'}), 400
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

    if is_ajax:
        return jsonify({'success': True, 'message': 'New code sent.', 'cooldown_remaining': 60})
    flash("New code sent.", "success")
    return redirect(url_for(verify_url_name, user_id=user.id))


def _portal_reset_password(portal_name, login_url_name):
    """
    Reusable password reset handler for all portals.
    Step 3: Accept new password and confirm.
    """
    verified_key = f'{portal_name.lower()}_reset_verified_id'
    session_key = f'{portal_name.lower()}_reset_user_id'
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    user_id = session.get(verified_key)
    if not user_id:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Session expired.'}), 400
        return redirect(url_for(login_url_name))

    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        err = validate_password(new_password, confirm_password)
        if err:
            if is_ajax:
                return jsonify({'success': False, 'message': err}), 400
            flash(err, "danger")
            return None  # Caller re-renders

        user.set_password(new_password)
        user.otp_code = None
        user.otp_created_at = None
        db.session.commit()

        session.pop(session_key, None)
        session.pop(verified_key, None)

        if is_ajax:
            return jsonify({'success': True, 'redirect': url_for(login_url_name)})
        flash("Password updated successfully. Please log in.", "success")
        return redirect(url_for(login_url_name))


# ══════════════════════════════════════════════════════════════════
# ── UNIFIED STAFF LOGIN (/staff/login) ────────────────────────────
# ══════════════════════════════════════════════════════════════════

ALL_STAFF_ROLES = ['CASHIER', 'STAFF', 'KITCHEN', 'INVENTORY_STAFF', 'INVENTORY', 'ADMIN', 'SUPER_ADMIN']

def _get_dashboard_for_role(role):
    """Return the correct dashboard URL name based on user role."""
    role_upper = (role or '').upper()
    if role_upper in ('CASHIER', 'STAFF'):
        return 'cashier_portal.cashier_dashboard'
    elif role_upper == 'KITCHEN':
        return 'kitchen_portal.kitchen_dashboard'
    elif role_upper in ('INVENTORY_STAFF', 'INVENTORY'):
        return 'inventory_portal.inventory_dashboard'
    elif role_upper in ('ADMIN', 'SUPER_ADMIN'):
        return 'admin.overview'
    return 'cashier_portal.staff_login'

@cashier_bp.route('/staff/login', methods=['GET', 'POST'])
def staff_login():
    # If already logged in as staff, redirect to their dashboard
    if current_user.is_authenticated and current_user.role and current_user.role.upper() in ALL_STAFF_ROLES:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'redirect': url_for(_get_dashboard_for_role(current_user.role))})
        return redirect(url_for(_get_dashboard_for_role(current_user.role)))

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        selected_branch = request.form.get('branch', '').strip()

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            role_upper = (user.role or '').upper()
            if role_upper not in ALL_STAFF_ROLES:
                msg = 'Insufficient permissions.'
                if is_ajax: return jsonify({'success': False, 'message': msg}), 401
                flash(msg, 'error')
                return render_template('staff/login.html')

            if user.status == 'PENDING':
                msg = 'Your account is pending admin approval.'
                if is_ajax: return jsonify({'success': False, 'message': msg}), 401
                flash(msg, 'error')
                return render_template('staff/login.html')
            elif user.status != 'ACTIVE':
                msg = 'Your account is not active.'
                if is_ajax: return jsonify({'success': False, 'message': msg}), 401
                flash(msg, 'error')
                return render_template('staff/login.html')

            # Validate branch (Super Admin and users with branch='ALL' can access any branch)
            if role_upper != 'SUPER_ADMIN' and user.branch != 'ALL':
                if not selected_branch or user.branch != selected_branch:
                    msg = f'You are registered under the {user.branch} branch and cannot log in to {selected_branch or "this"} branch.'
                    if is_ajax: return jsonify({'success': False, 'message': msg}), 401
                    flash(msg, 'error')
                    return render_template('staff/login.html')

            # Success
            if role_upper in ('CASHIER', 'STAFF'):
                session['logged_in_portal'] = 'cashier'
            elif role_upper == 'KITCHEN':
                session['logged_in_portal'] = 'kitchen'
            elif role_upper in ('INVENTORY_STAFF', 'INVENTORY'):
                session['logged_in_portal'] = 'inventory'
            else:
                session['logged_in_portal'] = 'admin'

            login_user(user)
            redirect_url = url_for(_get_dashboard_for_role(user.role))

            if is_ajax:
                return jsonify({'success': True, 'redirect': redirect_url})
            return redirect(redirect_url)

        msg = 'Invalid email, password, or insufficient permissions.'
        if is_ajax:
            return jsonify({'success': False, 'message': msg}), 401
        flash(msg, 'error')
    return render_template('staff/login.html')


@cashier_bp.route('/staff/register', methods=['GET', 'POST'])
def staff_register():
    if current_user.is_authenticated:
        return redirect(url_for('cashier_portal.staff_login'))

    if request.method == 'POST':
        from datetime import datetime
        from routes.auth import validate_name, validate_email, validate_username, calculate_age, validate_password as auth_validate_password

        first_name = request.form.get('first_name', '').strip()
        middle_name = request.form.get('middle_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        phone_number = request.form.get('phone_number', '').strip()
        birthday_str = request.form.get('birthday', '')
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        terms = request.form.get('terms')
        gender = request.form.get('gender', '').strip()
        role = request.form.get('role', '').strip()
        branch = request.form.get('branch', '').strip()

        if not all([first_name, last_name, username, email, phone_number, birthday_str, password, confirm_password, terms, role, branch]):
            flash("All required fields must be filled and terms accepted.", "danger")
            return render_template('staff/register.html', get_ph_time=get_ph_time)

        # Run validation checks
        for name, label in [(first_name, 'First Name'), (last_name, 'Last Name')]:
            err = validate_name(name, label)
            if err: flash(err, "danger"); return render_template('staff/register.html', get_ph_time=get_ph_time)
        if middle_name:
            err = validate_name(middle_name, 'Middle Name')
            if err: flash(err, "danger"); return render_template('staff/register.html', get_ph_time=get_ph_time)

        err = validate_email(email)
        if err: flash(err, "danger"); return render_template('staff/register.html', get_ph_time=get_ph_time)

        err = validate_username(username, first_name, last_name)
        if err: flash(err, "danger"); return render_template('staff/register.html', get_ph_time=get_ph_time)

        full_identity = f"{first_name} {last_name}".lower()
        if username.lower() == full_identity:
            flash("Username cannot be identical to Full Name.", "danger"); return render_template('staff/register.html', get_ph_time=get_ph_time)

        try:
            birthday = datetime.strptime(birthday_str, '%Y-%m-%d').date()
            age = calculate_age(birthday)
            if age < 18:
                flash("You must be at least 18 years old to register.", "danger"); return render_template('staff/register.html', get_ph_time=get_ph_time)
            if age > 70:
                flash("Please enter a valid birthday. Maximum age is 70 years.", "danger"); return render_template('staff/register.html', get_ph_time=get_ph_time)
        except ValueError:
            flash("Invalid birthday format.", "danger"); return render_template('staff/register.html', get_ph_time=get_ph_time)

        err = auth_validate_password(password, confirm_password)
        if err: flash(err, "danger"); return render_template('staff/register.html', get_ph_time=get_ph_time)

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "danger"); return render_template('staff/register.html', get_ph_time=get_ph_time)
        if User.query.filter_by(username=username).first():
            flash("Username already taken.", "danger"); return render_template('staff/register.html', get_ph_time=get_ph_time)
        if User.query.filter_by(first_name=first_name, last_name=last_name).first():
            flash("User with this First and Last name already exists.", "danger"); return render_template('staff/register.html', get_ph_time=get_ph_time)
        if phone_number and User.query.filter_by(phone_number=phone_number).first():
            flash("Phone number already registered to another account.", "danger"); return render_template('staff/register.html', get_ph_time=get_ph_time)

        new_user = User(
            first_name=first_name, middle_name=middle_name, last_name=last_name,
            username=username, email=email, phone_number=phone_number, birthday=birthday, 
            status='PENDING', is_verified=True, gender=gender, age=age, role=role, branch=branch
        )
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful! Your staff account is pending admin approval.", "success")
        return redirect(url_for('cashier_portal.staff_login'))

    return render_template('staff/register.html', get_ph_time=get_ph_time)


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

CASHIER_ROLES = ['CASHIER', 'STAFF']

@cashier_bp.route('/cashier/login', methods=['GET', 'POST'])
@cashier_bp.route('/staff/cashier/login', methods=['GET', 'POST'])
def cashier_login():
    # Redirect to unified staff login
    return redirect(url_for('cashier_portal.staff_login'))

@cashier_bp.route('/staff/cashier')
def cashier_dashboard():
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    today = get_ph_time().date()
    from datetime import datetime, time
    today_start = datetime.combine(today, time.min)
    from models import Reservation
    
    active_orders_count = Order.query.outerjoin(Reservation).filter(
        Order.is_archived.is_(False),
        Order.status.in_(['PENDING', 'ACCEPTED', 'PREPARING', 'READY']),
        db.or_(
            Order.reservation_id.is_(None),
            Reservation.date <= today
        )
    ).count()
    completed_today_count = Order.query.filter(
        Order.is_archived.is_(False),
        Order.status == 'COMPLETED',
        db.func.date(Order.created_at) == today
    ).count()
    unpaid_orders_count = Order.query.outerjoin(Reservation).filter(
        Order.is_archived.is_(False),
        Order.payment_status == 'UNPAID',
        db.or_(
            Order.reservation_id.is_(None),
            Reservation.date <= today
        )
    ).count()
    
    # Recent active orders plus completed/cancelled orders from today
    live_orders = Order.query.outerjoin(Reservation).filter(
        Order.is_archived.is_(False),
        db.or_(
            Order.status.in_(['PENDING', 'ACCEPTED', 'PREPARING', 'READY']),
            db.and_(
                Order.status.in_(['COMPLETED', 'CANCELLED']),
                db.func.date(Order.created_at) == today
            )
        ),
        db.or_(
            Order.reservation_id.is_(None),
            Reservation.date <= today
        )
    ).order_by(Order.created_at.desc()).limit(100).all()
    
    # Live Auto-Verify Xendit online payment status for any UNPAID orders with a xendit_invoice_id
    import os, base64, requests
    xendit_secret_key = os.environ.get('XENDIT_SECRET_KEY')
    if xendit_secret_key and xendit_secret_key.strip() not in ('add_your_xendit_secret_key_here', ''):
        api_key_b64 = base64.b64encode(f"{xendit_secret_key.strip()}:".encode('utf-8')).decode('utf-8')
        headers = { 'Authorization': f'Basic {api_key_b64}' }
        unpaid_xendit_orders = [o for o in live_orders if o.payment_status == 'UNPAID' and o.xendit_invoice_id]
        status_updated = False
        for ord_obj in unpaid_xendit_orders:
            try:
                resp = requests.get(f'https://api.xendit.co/v2/invoices/{ord_obj.xendit_invoice_id}', headers=headers, timeout=5)
                if resp.status_code == 200:
                    inv_data = resp.json()
                    inv_status = str(inv_data.get('status', '')).upper()
                    if inv_status in ['PAID', 'SETTLED']:
                        ord_obj.payment_status = 'PAID'
                        if not ord_obj.amount_tendered:
                            ord_obj.amount_tendered = ord_obj.total_amount
                        if ord_obj.change_amount is None:
                            ord_obj.change_amount = 0.0
                        status_updated = True
            except Exception as ex:
                print(f"Xendit Auto-Verify Error for order #{ord_obj.id}: {ex}")
        if status_updated:
            db.session.commit()
            unpaid_orders_count = Order.query.outerjoin(Reservation).filter(
                Order.is_archived.is_(False),
                Order.payment_status == 'UNPAID',
                db.or_(
                    Order.reservation_id.is_(None),
                    Reservation.date <= today
                )
            ).count()
    
    return render_template('cashier/dashboard.html', 
                           portal_name=f"{current_user.first_name} {current_user.last_name}",
                           active_orders=active_orders_count,
                           completed_today=completed_today_count,
                           unpaid_orders=unpaid_orders_count,
                           orders=live_orders)


def _serialize_cashier_order(o):
    """Lightweight order payload for cashier dashboard polling."""
    if o.user:
        customer = f"{o.user.first_name} {o.user.last_name}".strip()
    elif o.customer_name:
        customer = o.customer_name
    else:
        customer = 'Walk-in Guest'
    dining = (o.dining_option or 'DINE_IN').replace('_', ' ').title()
    return {
        'id': o.id,
        'order_code': o.display_code,
        'customer': customer,
        'total_amount': float(o.total_amount or 0),
        'dining_option': o.dining_option or 'DINE_IN',
        'dining_label': dining,
        'status': o.status,
        'payment_status': o.payment_status,
        'table_number': o.table_number,
        'table_status': o.table_status or 'AVAILABLE',
        'created_at': o.display_date_time,
    }


@cashier_bp.route('/staff/cashier/api/dashboard')
def cashier_api_dashboard():
    """JSON endpoint for real-time cashier dashboard updates."""
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return jsonify({'error': 'Unauthorized'}), 401

    today = get_ph_time().date()
    from datetime import datetime, time
    today_start = datetime.combine(today, time.min)
    from models import Reservation
    
    live_orders = (
        Order.query.outerjoin(Reservation)
        .filter(
            Order.is_archived.is_(False),
            db.or_(
                Order.status.in_(['PENDING', 'ACCEPTED', 'PREPARING', 'READY']),
                db.and_(
                    Order.status.in_(['COMPLETED', 'CANCELLED']),
                    db.func.date(Order.created_at) == today
                )
            ),
            db.or_(
                Order.reservation_id.is_(None),
                Reservation.date <= today
            )
        )
        .order_by(Order.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify({
        'success': True,
        'time': get_ph_time().strftime('%I:%M:%S %p'),
        'stats': {
            'active_orders': Order.query.outerjoin(Reservation).filter(
                Order.is_archived.is_(False),
                Order.status.in_(['PENDING', 'ACCEPTED', 'PREPARING', 'READY']),
                db.or_(
                    Order.reservation_id.is_(None),
                    Reservation.date <= today
                )
            ).count(),
            'completed_today': Order.query.filter(
                Order.is_archived.is_(False),
                Order.status == 'COMPLETED',
                db.func.date(Order.created_at) == today
            ).count(),
            'unpaid_orders': Order.query.outerjoin(Reservation).filter(
                Order.payment_status == 'UNPAID',
                Order.is_archived.is_(False),
                db.or_(
                    Order.reservation_id.is_(None),
                    Reservation.date <= today
                )
            ).count(),
        },
        'orders': [_serialize_cashier_order(o) for o in live_orders],
    })


# In-memory table configurations store (with default 1–17 tables)
TABLE_CONFIGS = {
    i: {
        'id': i,
        'name': f'Table {i}',
        'area': 'Main Dining' if i <= 10 else ('Patio Area' if i <= 14 else 'VIP Lounge'),
        'capacity': 4 if i % 3 != 0 else (6 if i % 2 == 0 else 2)
    }
    for i in range(1, 18)
}


@cashier_bp.route('/staff/cashier/api/tables')
def cashier_api_tables():
    """Real-time table availability for staff."""
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return jsonify({'error': 'Unauthorized'}), 401

    from models import Reservation
    import datetime as py_datetime
    import re

    # 1. Query occupied tables — any non-archived order where table_status is OCCUPIED stays occupied until explicitly released
    from models import User as UserModel
    occupied_rows = (
        db.session.query(Order.table_number, Order.id, Order.customer_name, Order.status, UserModel.first_name, UserModel.last_name)
        .outerjoin(UserModel, Order.user_id == UserModel.id)
        .filter(
            Order.table_status == 'OCCUPIED',
            Order.table_number.isnot(None),
            Order.is_archived.is_(False)
        )
        .all()
    )
    occupied_map = {}
    for table_num, order_id, customer_name, status, first_name, last_name in occupied_rows:
        display_name = (
            f"{first_name} {last_name}".strip() if first_name
            else customer_name
            or f'Order #{order_id}'
        )
        occupied_map[int(table_num)] = {
            'order_id': order_id,
            'customer': display_name,
            'order_status': status,
        }

    # 2. Query today's active reservations
    current_dt = get_ph_time()
    today_date = current_dt.date()
    today_reservations = Reservation.query.filter(
        Reservation.date == today_date,
        Reservation.status == 'CONFIRMED'
    ).all()

    reserved_tables = {}
    for res in today_reservations:
        if not res.table_number:
            continue
        start_dt = py_datetime.datetime.combine(res.date, res.time)
        end_dt = start_dt + py_datetime.timedelta(hours=res.duration or 2)
        if start_dt <= current_dt <= end_dt:
            customer_name = f"{res.user.first_name} {res.user.last_name}" if res.user else "Guest"
            # Check for exclusive booking
            if "exclusive" in res.booking_type.lower() or "exclusive" in (res.table_number or '').lower():
                for t_num in TABLE_CONFIGS.keys():
                    reserved_tables[t_num] = {
                        'reservation_id': res.id,
                        'customer': customer_name,
                        'time': res.time.strftime('%I:%M %p'),
                        'duration': res.duration,
                    }
            else:
                nums = [int(n) for n in re.findall(r'\d+', res.table_number)]
                for num in nums:
                    if num in TABLE_CONFIGS:
                        reserved_tables[num] = {
                            'reservation_id': res.id,
                            'customer': customer_name,
                            'time': res.time.strftime('%I:%M %p'),
                            'duration': res.duration,
                        }

    # 3. Construct tables availability map
    tables = {}
    occupied_count = 0
    reserved_count = 0
    available_count = 0
    sorted_ids = sorted(list(TABLE_CONFIGS.keys()))
    for i in sorted_ids:
        config = TABLE_CONFIGS[i]
        if i in occupied_map:
            tables[i] = {'status': 'OCCUPIED', **config, **occupied_map[i]}
            occupied_count += 1
        elif i in reserved_tables:
            tables[i] = {'status': 'RESERVED', **config, **reserved_tables[i]}
            reserved_count += 1
        else:
            tables[i] = {'status': 'AVAILABLE', **config}
            available_count += 1

    return jsonify({
        'success': True,
        'time': get_ph_time().strftime('%I:%M:%S %p'),
        'tables': tables,
        'total_count': len(sorted_ids),
        'occupied_count': occupied_count,
        'reserved_count': reserved_count,
        'available_count': available_count,
    })


@cashier_bp.route('/staff/cashier/api/tables/<int:table_num>/update', methods=['POST'])
def cashier_update_table(table_num):
    """Update table details."""
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    data = request.get_json() or {}
    name = str(data.get('name') or f'Table {table_num}').strip()
    area = str(data.get('area') or 'Main Dining').strip()
    
    try:
        capacity = int(data.get('capacity', 4))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid capacity. Must be a valid integer.'}), 400
        
    if capacity < 1:
        return jsonify({'success': False, 'message': 'Capacity must be at least 1 pax.'}), 400
        
    if table_num not in TABLE_CONFIGS:
        TABLE_CONFIGS[table_num] = {'id': table_num}
        
    TABLE_CONFIGS[table_num].update({
        'id': table_num,
        'name': name,
        'area': area,
        'capacity': capacity
    })
    
    return jsonify({
        'success': True,
        'message': f'"{name}" updated successfully ({capacity} Pax, {area}).',
        'table': TABLE_CONFIGS[table_num]
    })


@cashier_bp.route('/staff/cashier/api/tables/add', methods=['POST'])
def cashier_add_table():
    """Add a new dining table."""
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    data = request.get_json() or {}
    new_id = max(TABLE_CONFIGS.keys(), default=0) + 1
    name = str(data.get('name') or f'Table {new_id}').strip()
    area = str(data.get('area') or 'Main Dining').strip()
    
    try:
        capacity = int(data.get('capacity', 4))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid capacity. Must be a valid integer.'}), 400
        
    if capacity < 1:
        return jsonify({'success': False, 'message': 'Capacity must be at least 1 pax.'}), 400
        
    TABLE_CONFIGS[new_id] = {
        'id': new_id,
        'name': name,
        'area': area,
        'capacity': capacity
    }
    
    return jsonify({
        'success': True,
        'message': f'"{name}" added successfully ({capacity} Pax, {area}).',
        'table': TABLE_CONFIGS[new_id]
    })



@cashier_bp.route('/staff/cashier/tables/<int:table_num>/release', methods=['POST'])
def cashier_release_table(table_num):
    """Release occupied table when customer finishes dining and leaves."""
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    try:
        # Find all non-archived OCCUPIED orders for this table
        orders = Order.query.filter(
            Order.table_number == table_num,
            Order.table_status == 'OCCUPIED',
            Order.is_archived.is_(False)
        ).all()
        
        if not orders:
            return jsonify({'success': False, 'message': f'Table {table_num} is not currently occupied.'}), 400
        
        # Release table and mark active order as COMPLETED
        for order in orders:
            order.table_status = 'AVAILABLE'
            if order.status in ('PENDING', 'PREPARING', 'READY'):
                order.status = 'COMPLETED'
                
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Table {table_num} released successfully.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@cashier_bp.route('/staff/cashier/tables/<int:table_num>/release-reservation', methods=['POST'])
def cashier_release_reservation(table_num):
    """Release reserved table by marking active reservation as COMPLETED."""
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    try:
        from models import Reservation
        import datetime as py_datetime
        current_dt = get_ph_time()
        today_date = current_dt.date()
        
        reservations = Reservation.query.filter(
            Reservation.date == today_date,
            Reservation.status == 'CONFIRMED'
        ).all()
        
        target_res = None
        for res in reservations:
            if not res.table_number:
                continue
            
            # Check time overlap
            start_dt = py_datetime.datetime.combine(res.date, res.time)
            end_dt = start_dt + py_datetime.timedelta(hours=res.duration or 2)
            if start_dt <= current_dt <= end_dt:
                if "exclusive" in res.booking_type.lower() or "exclusive" in (res.table_number or '').lower():
                    target_res = res
                    break
                else:
                    import re
                    nums = [int(n) for n in re.findall(r'\d+', res.table_number)]
                    if table_num in nums:
                        target_res = res
                        break
        
        if not target_res:
            return jsonify({'success': False, 'message': f'No active reservation found for Table {table_num} today.'}), 400
            
        target_res.status = 'COMPLETED'
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Reservation for Table {table_num} marked as COMPLETED.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@cashier_bp.route('/staff/cashier/orders/<int:order_id>/complete', methods=['POST'])
def cashier_complete_order(order_id):
    """Mark an order as COMPLETED from the cashier dashboard."""
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    try:
        order = Order.query.get_or_404(order_id)
        
        # We do NOT release the table automatically when serving/completing the order.
        # The table remains occupied/unavailable until the cashier explicitly releases it.
        order.status = 'COMPLETED'
        
        # Notify user
        if order.user_id:
            from utils import create_notification
            create_notification(
                order.user_id,
                'Order Completed',
                f'Your order #{order.id} has been served. Enjoy! ✨',
                'ORDER',
                link='/my-orders'
            )
            
        # Notify via SocketIO if available
        try:
            from extensions import socketio
            socketio.emit('order_status_update', {'id': order.id, 'status': 'COMPLETED'}, namespace='/')
        except:
            pass
            
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Order #{order.id} has been marked as COMPLETED.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@cashier_bp.route('/staff/cashier/orders/<int:order_id>/accept', methods=['POST'])
def cashier_accept_order(order_id):
    """Accept an incoming PENDING order and send it to the kitchen (status = ACCEPTED)."""
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    try:
        order = Order.query.get_or_404(order_id)
        order.status = 'ACCEPTED'
        
        # Notify user
        if order.user_id:
            from utils import create_notification
            create_notification(
                order.user_id,
                'Order Accepted',
                f'Your order {order.display_code} has been accepted by Cashier and sent to Kitchen! 🍳',
                'ORDER',
                link='/my-orders'
            )
            
        # Notify via SocketIO if available
        try:
            from extensions import socketio
            socketio.emit('order_status_update', {'id': order.id, 'status': 'ACCEPTED'}, namespace='/')
        except:
            pass
            
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Order {order.display_code} accepted and sent to kitchen!'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@cashier_bp.route('/staff/cashier/orders/update_payment/<int:order_id>', methods=['POST'])
def cashier_update_payment_status(order_id):
    """Settle bill payment for an order from Cashier Dashboard."""
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    try:
        order = Order.query.get_or_404(order_id)
        new_payment_status = request.form.get('payment_status', 'PAID')

        if new_payment_status == 'PAID':
            amount_tendered_raw = request.form.get('amount_tendered', '').strip()
            try:
                amount_tendered = float(amount_tendered_raw)
            except (ValueError, TypeError):
                if order.payment_method == 'ONLINE' or order.xendit_invoice_id:
                    amount_tendered = float(order.total_amount)
                else:
                    return jsonify({'success': False, 'message': 'Invalid amount tendered.'}), 400

            actual_due = float(order.total_amount)
            if amount_tendered < actual_due:
                return jsonify({'success': False, 'message': f'Amount tendered (₱{amount_tendered:,.2f}) is less than total bill (₱{actual_due:,.2f}).'}), 400

            change_amount = round(amount_tendered - actual_due, 2)
            order.payment_status = 'PAID'
            order.amount_tendered = amount_tendered
            order.change_amount = change_amount
            order.processed_by_id = current_user.id

            # Auto-complete order if it's already READY
            if order.status == 'READY':
                if order.dining_option != 'DINE_IN' or order.table_status == 'AVAILABLE' or not order.table_number:
                    order.status = 'COMPLETED'

            if order.user_id:
                from utils import create_notification
                create_notification(
                    order.user_id,
                    'Payment Confirmed',
                    f'Payment of ₱{amount_tendered:,.2f} confirmed for order {order.display_code}. Change: ₱{change_amount:,.2f}. Thank you! ✨',
                    'ORDER',
                    link='/my-orders'
                )

            db.session.commit()
            return jsonify({
                'success': True,
                'message': f'Payment of ₱{amount_tendered:,.2f} confirmed! Change: ₱{change_amount:,.2f}',
                'change_amount': change_amount
            })

        elif new_payment_status == 'UNPAID':
            order.payment_status = 'UNPAID'
            order.amount_tendered = None
            order.change_amount = None
            db.session.commit()
            return jsonify({'success': True, 'message': f'Order {order.display_code} marked as UNPAID.'})

        return jsonify({'success': False, 'message': 'Invalid status'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@cashier_bp.route('/staff/cashier/api/orders/<int:order_id>/details')
def cashier_order_details_api(order_id):
    """Fetch complete details of an order for Cashier modal."""
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    try:
        from sqlalchemy.orm import selectinload
        order = Order.query.options(selectinload(Order.items).selectinload(OrderItem.menu_item)).get_or_404(order_id)
        
        customer = 'Walk-in Guest'
        email = 'N/A'
        if order.user:
            customer = f"{order.user.first_name} {order.user.last_name}".strip()
            email = order.user.email or 'N/A'
        elif order.customer_name:
            customer = order.customer_name

        items = []
        for item in order.items:
            items.append({
                'name': item.menu_item.name if item.menu_item else 'Item',
                'qty': item.quantity,
                'price': float(item.price_at_time or 0)
            })

        return jsonify({
            'success': True,
            'order': {
                'id': order.id,
                'code': order.display_code,
                'customer': customer,
                'email': email,
                'notes': order.notes or 'No special instructions',
                'dining_option': (order.dining_option or 'DINE_IN').replace('_', ' ').title(),
                'payment_method': order.payment_method or 'COUNTER',
                'payment_status': order.payment_status or 'UNPAID',
                'status': order.status or 'PENDING',
                'table_number': order.table_number if order.dining_option == 'DINE_IN' else None,
                'created_at': order.display_date_time,
                'total': float(order.total_amount or 0),
                'items': items
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@cashier_bp.route('/staff/cashier/tables')
def cashier_table_management():
    """Visual table management board for staff."""
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    return render_template(
        'cashier/table_management.html',
        portal_name=f"{current_user.first_name} {current_user.last_name}",
    )


@cashier_bp.route('/staff/cashier/api/unassigned-orders')
def cashier_api_unassigned_orders():
    """Get all active orders (PENDING, PREPARING, READY) that do not currently occupy a table."""
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return jsonify({'error': 'Unauthorized'}), 401
        
    # Get all active orders that do not occupy a table
    orders = Order.query.filter(
        Order.status.in_(['PENDING', 'PREPARING', 'READY']),
        Order.is_archived.is_(False),
        db.or_(
            Order.table_number.is_(None),
            Order.table_status != 'OCCUPIED'
        )
    ).order_by(Order.created_at.desc()).all()
    
    serialized = []
    for o in orders:
        if o.user:
            customer = f"{o.user.first_name} {o.user.last_name}".strip()
        elif o.customer_name:
            customer = o.customer_name
        else:
            customer = 'Walk-in Guest'
            
        serialized.append({
            'id': o.id,
            'order_code': o.display_code,
            'customer': customer,
            'dining_option': o.dining_option,
            'status': o.status,
            'total_amount': float(o.total_amount or 0),
            'created_at': o.display_date_time,
        })
        
    return jsonify({
        'success': True,
        'orders': serialized
    })


@cashier_bp.route('/staff/cashier/orders/<int:order_id>/assign-table', methods=['POST'])
def cashier_assign_table(order_id):
    """Assign a table to an order from the cashier dashboard/table management."""
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    try:
        data = request.get_json() or {}
        table_number = data.get('table_number')
        if not table_number:
            return jsonify({'success': False, 'message': 'Table number is required.'}), 400
            
        try:
            table_number = int(table_number)
            if table_number < 1 or table_number > 17:
                return jsonify({'success': False, 'message': 'Invalid table number.'}), 400
        except ValueError:
            return jsonify({'success': False, 'message': 'Table number must be an integer.'}), 400
            
        # Check if table is currently occupied by an active order
        occupied_order = Order.query.filter(
            Order.table_number == table_number,
            Order.table_status == 'OCCUPIED',
            Order.is_archived.is_(False)
        ).first()
        
        if occupied_order:
            return jsonify({'success': False, 'message': f'Table {table_number} is already occupied by Order #{occupied_order.id}.'}), 400
            
        order = Order.query.get_or_404(order_id)
        
        # Assign table
        order.table_number = table_number
        order.table_status = 'OCCUPIED'
        order.dining_option = 'DINE_IN' # Force to DINE_IN since they are assigned to a table
        
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Order {order.order_code or order.id} has been assigned to Table {table_number}.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@cashier_bp.route('/staff/cashier/api/history-summary')
def cashier_api_history_summary():
    """Lightweight stats for order history auto-refresh."""
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return jsonify({'error': 'Unauthorized'}), 401

    today = get_ph_time().date()
    completed_today = Order.query.filter(
        Order.is_archived.is_(False),
        Order.status == 'COMPLETED',
        db.func.date(Order.created_at) == today,
    ).count()
    latest = (
        Order.query.filter(Order.is_archived.is_(False))
        .order_by(Order.created_at.desc())
        .limit(5)
        .all()
    )
    return jsonify({
        'success': True,
        'time': get_ph_time().strftime('%I:%M:%S %p'),
        'completed_today': completed_today,
        'total_records': Order.query.filter(Order.is_archived.is_(False)).count(),
        'latest': [{
            'id': o.id,
            'order_code': o.order_code or f'#{o.id}',
            'status': o.status,
            'created_at': o.created_at.isoformat() if o.created_at else None,
        } for o in latest],
    })


@cashier_bp.route('/staff/cashier/walkin-order')
def cashier_walkin_order():
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    items = MenuItem.query.filter_by(is_available=True, is_deleted=False).order_by(MenuItem.category, MenuItem.name).all()
    categories = sorted(set(i.category for i in items))
    return render_template('cashier/walkin_order.html', items=items, categories=categories)

@cashier_bp.route('/staff/cashier/reservations')
def cashier_reservations():
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    from models import Reservation
    query = Reservation.query
    user_branch = getattr(current_user, 'branch', None)
    if user_branch and user_branch != 'ALL':
        query = query.filter_by(branch=user_branch)
    all_reservations = query.order_by(Reservation.created_at.desc()).all()
    
    class MockPagination:
        def __init__(self, items):
            self.items = items
            self.total = len(items)
            self.pages = 1
            self.page = 1
    
    pagination = MockPagination(all_reservations)
    return render_template('cashier/reservations.html', reservations=pagination, status_filter='ALL')

@cashier_bp.route('/staff/cashier/reservations/update/<int:res_id>', methods=['POST'])
def cashier_update_reservation(res_id):
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': False, 'message': 'Session expired or unauthorized.'}), 403
        return redirect(url_for('cashier_portal.staff_login'))

    from models import Reservation

    res = Reservation.query.get_or_404(res_id)
    user_branch = getattr(current_user, 'branch', None)
    
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    
    if user_branch and user_branch != 'ALL' and res.branch != user_branch:
        msg = "Access denied."
        if is_ajax:
            return jsonify({'success': False, 'message': msg}), 403
        flash(msg, "danger")
        return redirect(url_for('cashier_portal.cashier_reservations'))

    new_status = request.form.get('status')
    table_number = request.form.get('table_number')

    if new_status == 'CONFIRMED' and table_number:
        conflict = Reservation.query.filter(
            Reservation.id != res.id,
            Reservation.branch == res.branch,
            Reservation.date == res.date,
            Reservation.time == res.time,
            Reservation.table_number == table_number,
            Reservation.status == 'CONFIRMED'
        ).first()
        if conflict:
            msg = f"{table_number} is already booked for this date and time."
            if is_ajax:
                return jsonify({'success': False, 'message': msg}), 400
            flash(msg, "danger")
            return redirect(url_for('cashier_portal.cashier_reservations'))

    res.status = new_status
    if table_number:
        res.table_number = table_number
    db.session.commit()

    msg = f"Reservation #{res.id} updated to {new_status}."
    if is_ajax:
        return jsonify({'success': True, 'message': msg})
    flash(msg, "success")
    return redirect(url_for('cashier_portal.cashier_reservations'))

@cashier_bp.route('/staff/cashier/reservations/bulk-complete', methods=['POST'])
def cashier_bulk_complete_reservations():
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': False, 'message': 'Session expired or unauthorized.'}), 403
        return redirect(url_for('cashier_portal.staff_login'))

    from models import Reservation

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json

    ids_raw = (request.form.get('reservation_ids') or '').strip()
    if not ids_raw:
        msg = "No reservations selected."
        if is_ajax:
            return jsonify({'success': False, 'message': msg}), 400
        flash(msg, "warning")
        return redirect(url_for('cashier_portal.cashier_reservations'))

    try:
        res_ids = [int(x) for x in ids_raw.split(',') if x.strip().isdigit()]
    except Exception:
        msg = "Invalid selection."
        if is_ajax:
            return jsonify({'success': False, 'message': msg}), 400
        flash(msg, "danger")
        return redirect(url_for('cashier_portal.cashier_reservations'))

    if not res_ids:
        msg = "No reservations selected."
        if is_ajax:
            return jsonify({'success': False, 'message': msg}), 400
        flash(msg, "warning")
        return redirect(url_for('cashier_portal.cashier_reservations'))

    user_branch = getattr(current_user, 'branch', None)
    q = Reservation.query.filter(Reservation.id.in_(res_ids), Reservation.status == 'CONFIRMED')
    if user_branch and user_branch != 'ALL':
        q = q.filter(Reservation.branch == user_branch)
    rows = q.all()

    if not rows:
        msg = "No eligible reservations to complete."
        if is_ajax:
            return jsonify({'success': False, 'message': msg}), 400
        flash(msg, "warning")
        return redirect(url_for('cashier_portal.cashier_reservations'))

    for r in rows:
        r.status = 'COMPLETED'
    db.session.commit()

    msg = f"{len(rows)} reservation(s) marked as COMPLETED."
    if is_ajax:
        return jsonify({'success': True, 'message': msg})
    flash(msg, "success")
    return redirect(url_for('cashier_portal.cashier_reservations'))



@cashier_bp.route('/staff/cashier/history')
def cashier_orders_history():
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    page = request.args.get('page', 1, type=int)
    orders_pg = Order.query.filter(Order.is_archived.is_(False)).order_by(Order.created_at.desc()).paginate(page=page, per_page=20)
    
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

KITCHEN_ROLES = ['KITCHEN']

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
        # Kitchen receives ACCEPTED orders in TO COOK, PREPARING orders in COOKING
        pending_orders = Order.query.options(selectinload(Order.items)).filter(Order.status == 'ACCEPTED', Order.reservation_id.is_(None)).order_by(Order.created_at.asc()).all()
        preparing_orders = Order.query.options(selectinload(Order.items)).filter(Order.status == 'PREPARING').order_by(Order.created_at.asc()).all()
        # For ready orders, we want to see the last 20
        ready_orders = Order.query.options(selectinload(Order.items)).filter(Order.status == 'READY').order_by(Order.created_at.desc()).limit(20).all()
        
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


def _serialize_reserve_order(o):
    from models import Reservation
    res = o.reservation
    items = [{'qty': i.quantity, 'name': i.menu_item.name if i.menu_item else 'Item'} for i in o.items]
    return {
        'id': o.id,
        'status': o.status,
        'customer': (o.user.first_name if o.user else None) or o.customer_name or 'Guest',
        'reservation_date': res.date.strftime('%b %d, %Y') if res and res.date else '',
        'reservation_time': res.time.strftime('%I:%M %p') if res and res.time else '',
        'guest_count': res.guest_count if res else 0,
        'booking_type': res.booking_type if res else '',
        'items': items,
    }


@kitchen_bp.route('/staff/kitchen/api/reservations')
def kitchen_api_reservations():
    """JSON endpoint for kitchen event pre-order polling."""
    if not current_user.is_authenticated or current_user.role not in KITCHEN_ROLES:
        return jsonify({'error': 'Unauthorized'}), 401

    from sqlalchemy.orm import selectinload
    from models import Reservation
    reserve_orders = (
        Order.query.options(selectinload(Order.items).selectinload(OrderItem.menu_item), selectinload(Order.user))
        .join(Reservation)
        .filter(Order.reservation_id.isnot(None), ~Order.status.in_(['COMPLETED', 'CANCELLED']))
        .order_by(Reservation.date.asc(), Reservation.time.asc())
        .all()
    )
    return jsonify({
        'success': True,
        'time': get_ph_time().strftime('%I:%M:%S %p'),
        'count': len(reserve_orders),
        'orders': [_serialize_reserve_order(o) for o in reserve_orders],
    })


@kitchen_bp.route('/staff/kitchen/update/<int:order_id>', methods=['POST'])
@login_required
def kitchen_update_order(order_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if current_user.role not in KITCHEN_ROLES:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        flash("Unauthorized", "error")
        return redirect(url_for('main.index'))
        
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    
    # Statuses allowed by kitchen: PREPARING, READY, COMPLETED
    if new_status in ['PREPARING', 'READY', 'COMPLETED']:
        # Auto-deduct ingredients when order moves to PREPARING
        if new_status == 'PREPARING' and order.status != 'PREPARING':
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
                        ing.kitchen_qty = max(0.0, float(ing.kitchen_qty or 0) - float(deduction))

                # Batch availability sync — single pass instead of N+1 queries
                affected_ing_ids = list(deduction_by_ingredient_id.keys())
                if affected_ing_ids:
                    all_links = MenuItemIngredient.query.filter(
                        MenuItemIngredient.ingredient_id.in_(affected_ing_ids)
                    ).all()
                    affected_mi_ids = list({lnk.menu_item_id for lnk in all_links})
                    if affected_mi_ids:
                        from sqlalchemy.orm import selectinload
                        affected_mis = MenuItem.query.options(
                            selectinload(MenuItem.ingredients).selectinload(MenuItemIngredient.ingredient)
                        ).filter(MenuItem.id.in_(affected_mi_ids)).all()
                        for mi in affected_mis:
                            can_make = True
                            for recipe_item in mi.ingredients:
                                ing_obj = ingredients_by_id.get(recipe_item.ingredient_id, recipe_item.ingredient)
                                qty_in_kitchen = float(ing_obj.kitchen_qty or 0)
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

        # Notify user
        if order.user_id:
            from utils import create_notification
            msgs = {
                'PREPARING': f'Your order #{order.id} is now being prepared! 🍳',
                'READY': f'Your order #{order.id} is ready! 🍱',
                'COMPLETED': f'Your order #{order.id} has been served. Enjoy! ✨'
            }
            if new_status in msgs:
                create_notification(order.user_id, f'Order {new_status.capitalize()}', msgs[new_status], 'ORDER', link='/my-orders')
        
        # Notify via SocketIO if available
        try:
            from extensions import socketio
            socketio.emit('order_status_update', {'id': order.id, 'status': new_status}, namespace='/')
        except:
            pass
        
        if is_ajax:
            return jsonify({'success': True, 'order_id': order.id, 'status': new_status})
            
        flash(f"Order #{order.id} updated to {new_status}.", "success")
    else:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Invalid status'}), 400
        
    return redirect(url_for('kitchen_portal.kitchen_dashboard'))

@kitchen_bp.route('/staff/kitchen/pantry')
def kitchen_pantry():
    if not current_user.is_authenticated or current_user.role not in KITCHEN_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    grouped_ingredients = _build_pantry_grouped()
        
    return render_template('kitchen/pantry.html', 
                           grouped_ingredients=grouped_ingredients,
                           portal_name=f"{current_user.first_name} {current_user.last_name}")

def _build_pantry_grouped():
    """Build ingredient-to-category grouping in ONE query instead of N+1."""
    all_ingredients = Ingredient.query.order_by(Ingredient.name).all()
    ing_by_id = {ing.id: ing for ing in all_ingredients}

    # Single query: get all ingredient→menu category mappings at once
    cat_mappings = db.session.query(
        MenuItemIngredient.ingredient_id, MenuItem.category
    ).join(MenuItem, MenuItem.id == MenuItemIngredient.menu_item_id).filter(
        MenuItem.category.isnot(None)
    ).distinct().all()

    cats_by_ing = defaultdict(set)
    for ing_id, cat in cat_mappings:
        cats_by_ing[ing_id].add(cat)

    grouped_ingredients = {}
    for ing in all_ingredients:
        cat_names = list(cats_by_ing.get(ing.id, set())) or ['General / Uncategorized']
        for cat in cat_names:
            if cat not in grouped_ingredients:
                grouped_ingredients[cat] = []
            grouped_ingredients[cat].append(ing)

    return dict(sorted(grouped_ingredients.items()))

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
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        return redirect(url_for('cashier_portal.staff_login'))
    
    ing_id = request.form.get('ingredient_id', type=int)
    new_qty = request.form.get('kitchen_qty', type=float)
    
    if ing_id is not None and new_qty is not None:
        ing = Ingredient.query.get(ing_id)
        if ing:
            ing.kitchen_qty = new_qty
            db.session.commit()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'new_qty': new_qty, 'name': ing.name, 'unit': ing.unit})
            flash(f"Updated {ing.name} kitchen stock to {new_qty} {ing.unit}.", "success")
            
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': False, 'message': 'Invalid data'}), 400
    return redirect(url_for('kitchen_portal.kitchen_pantry'))

# ── Lightning-fast JSON APIs for kitchen polling (no template rendering) ──

def _serialize_order(o):
    """Serialize an order to a lightweight dict. Orders are pre-loaded with selectinload."""
    dining = (o.dining_option or 'DINE_IN')
    if dining == 'DINE_IN':
        icon = 'utensils'
    elif dining == 'TAKE_OUT':
        icon = 'bag-shopping'
    else:
        icon = 'truck'
    return {
        'id': o.id,
        'id_fmt': f'{o.id:04d}',
        'status': o.status,
        'created_at': o.created_at.strftime('%I:%M %p') if o.created_at else '',
        'customer': (o.user.first_name if o.user else None) or o.customer_name or 'Walk-in Guest',
        'dining_label': dining.replace('_', ' ').title(),
        'dining_icon': icon,
        'is_pre_order': o.reservation_id is not None,
        'items': [{'qty': i.quantity, 'name': i.menu_item.name if i.menu_item else 'Item'} for i in o.items]
    }

@cashier_bp.route('/staff/kitchen/api/orders')
@kitchen_bp.route('/staff/kitchen/api/orders')
def kitchen_api_orders():
    """Ultra-fast JSON endpoint for dashboard polling — no template rendering."""
    if not current_user.is_authenticated or current_user.role not in KITCHEN_ROLES:
        return jsonify({'error': 'Unauthorized'}), 401
    from sqlalchemy.orm import selectinload
    base_opts = [
        selectinload(Order.items).selectinload(OrderItem.menu_item),
        selectinload(Order.user)
    ]
    # Kitchen 'TO COOK' tab shows orders that Cashier has ACCEPTED (status == 'ACCEPTED')
    pending = Order.query.options(*base_opts).filter(
        Order.status == 'ACCEPTED', Order.reservation_id.is_(None)
    ).order_by(Order.created_at.asc()).all()
    preparing = Order.query.options(*base_opts).filter(
        Order.status == 'PREPARING'
    ).order_by(Order.created_at.asc()).all()
    ready = Order.query.options(*base_opts).filter(
        Order.status == 'READY'
    ).order_by(Order.created_at.desc()).limit(20).all()
    return jsonify({
        'pending': [_serialize_order(o) for o in pending],
        'preparing': [_serialize_order(o) for o in preparing],
        'ready': [_serialize_order(o) for o in ready],
        'counts': {'pending': len(pending), 'preparing': len(preparing), 'ready': len(ready)},
        'time': get_ph_time().strftime('%I:%M:%S %p')
    })

@kitchen_bp.route('/staff/kitchen/api/pantry')
def kitchen_api_pantry():
    """Ultra-fast JSON endpoint for pantry polling — no template rendering."""
    if not current_user.is_authenticated or current_user.role not in KITCHEN_ROLES:
        return jsonify({'error': 'Unauthorized'}), 401
    all_ingredients = Ingredient.query.order_by(Ingredient.name).all()
    data = []
    for ing in all_ingredients:
        data.append({
            'id': ing.id,
            'name': ing.name,
            'kitchen_qty': float(ing.kitchen_qty or 0),
            'unit': ing.unit,
            'reorder_level': float(ing.reorder_level or 0)
        })
    return jsonify({'ingredients': data, 'time': get_ph_time().strftime('%I:%M:%S %p')})

@kitchen_bp.route('/staff/kitchen/api/sidebar')
def kitchen_api_sidebar():
    """Lightweight polling endpoint for kitchen sidebar badge counts."""
    if not current_user.is_authenticated or current_user.role not in KITCHEN_ROLES:
        return jsonify({'error': 'Unauthorized'}), 401
    # Kitchen sidebar tracks ACCEPTED orders in TO COOK and PREPARING orders in COOKING
    pending_orders = Order.query.filter(
        Order.status == 'ACCEPTED', Order.reservation_id.is_(None)
    ).count()
    preparing_orders = Order.query.filter(
        Order.status == 'PREPARING', Order.reservation_id.is_(None)
    ).count()
    from models import StockRequest as _SR
    my_pending_requests = _SR.query.filter_by(
        requested_by_id=current_user.id, status='PENDING'
    ).count()
    fulfilled_requests = _SR.query.filter_by(
        requested_by_id=current_user.id, status='FULFILLED'
    ).count()
    return jsonify({
        'success': True,
        'pending_orders': pending_orders,
        'preparing_orders': preparing_orders,
        'my_pending_requests': my_pending_requests,
        'fulfilled_requests': fulfilled_requests,
        'time': get_ph_time().strftime('%I:%M:%S %p'),
    })

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

INVENTORY_ROLES = ['INVENTORY_STAFF', 'INVENTORY', 'ADMIN', 'SUPER_ADMIN']

@inventory_bp.before_request
def enforce_inventory_role_access():
    if not current_user.is_authenticated:
        return
        
    # Skip API, AJAX, and login routes
    if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return
    if request.path in ['/inventory/login', '/staff/inventory/login']:
        return

    user_role = (getattr(current_user, 'role', '') or '').upper()
    is_admin = user_role in ['ADMIN', 'SUPER_ADMIN']

    if request.path.startswith('/admin'):
        if not is_admin:
            if '/inventory' in request.path:
                staff_path = request.path.replace('/admin', '/staff', 1)
                return redirect(staff_path)
            else:
                return redirect(url_for('inventory_portal.inventory_dashboard'))
    elif request.path.startswith('/staff'):
        if is_admin:
            admin_path = request.path.replace('/staff', '/admin', 1)
            return redirect(admin_path)

@inventory_bp.route('/inventory/login', methods=['GET', 'POST'])
@inventory_bp.route('/staff/inventory/login', methods=['GET', 'POST'])
def inventory_login():
    # Redirect to unified staff login
    return redirect(url_for('cashier_portal.staff_login'))

def _get_ingredient_food_categories():
    """Returns a dict mapping ingredient_id -> list of food categories."""
    cat_mappings = db.session.query(
        MenuItemIngredient.ingredient_id, MenuItem.category
    ).join(MenuItem, MenuItem.id == MenuItemIngredient.menu_item_id).filter(
        MenuItem.category.isnot(None),
        MenuItem.is_deleted == False
    ).distinct().all()

    cats_by_ing = defaultdict(list)
    for ing_id, cat in cat_mappings:
        if cat not in cats_by_ing[ing_id]:
            cats_by_ing[ing_id].append(cat)
    return cats_by_ing

@inventory_bp.route('/staff/inventory')
@inventory_bp.route('/staff/inventory/levels')
@inventory_bp.route('/admin/inventory')
@inventory_bp.route('/admin/inventory/levels')
def inventory_dashboard():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    base_layout = 'admin/base.html' if request.path.startswith('/admin') else 'layouts/staff_layout.html'
    user_branch = getattr(current_user, 'branch', None)
    query = Ingredient.query
    if user_branch and user_branch != 'ALL':
        query = query.filter_by(branch=user_branch)
    all_ingredients = query.order_by(Ingredient.name).all()
    total_items = len(all_ingredients)
    
    low_stock_q = db.session.query(db.func.count(Ingredient.id)).filter(Ingredient.stock_qty <= Ingredient.reorder_level)
    if user_branch and user_branch != 'ALL':
        low_stock_q = low_stock_q.filter(Ingredient.branch == user_branch)
    low_stock_count = low_stock_q.scalar()
    
    suppliers = Supplier.query.order_by(Supplier.name).all()
    
    cats_by_ing = _get_ingredient_food_categories()
    
    grouped_ingredients = {}
    for ing in all_ingredients:
        ing_cats = cats_by_ing.get(ing.id) or [ing.category or 'General']
        for cat in ing_cats:
            if cat not in grouped_ingredients:
                grouped_ingredients[cat] = []
            grouped_ingredients[cat].append(ing)
            
    # Sort categories alphabetically
    grouped_ingredients = dict(sorted(grouped_ingredients.items()))
        
    return render_template('inventory/dashboard.html',
                           base_layout=base_layout,
                           portal_name=f"{current_user.first_name} {current_user.last_name}",
                           total_items=total_items,
                           low_stock=low_stock_count,
                           ingredients=all_ingredients,
                           grouped_ingredients=grouped_ingredients,
                           suppliers=suppliers)


@inventory_bp.route('/staff/inventory/api/alerts')
def inventory_api_alerts():
    """Low-stock alerts for inventory staff polling."""
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return jsonify({'error': 'Unauthorized'}), 401

    user_branch = getattr(current_user, 'branch', None)
    query = Ingredient.query.filter(Ingredient.stock_qty <= Ingredient.reorder_level)
    if user_branch and user_branch != 'ALL':
        query = query.filter(Ingredient.branch == user_branch)
    low_stock = query.order_by(Ingredient.stock_qty.asc()).limit(50).all()
    alerts = [{
        'id': ing.id,
        'name': ing.name,
        'stock_qty': float(ing.stock_qty or 0),
        'reorder_level': float(ing.reorder_level or 0),
        'unit': ing.unit,
        'status': 'OUT_OF_STOCK' if float(ing.stock_qty or 0) == 0 else 'LOW_STOCK',
    } for ing in low_stock]
    from models import StockRequest as _SR
    pending_stock = _SR.query.filter_by(status='PENDING').count()
    return jsonify({
        'success': True,
        'count': len(alerts),
        'alerts': alerts,
        'pending_stock_requests': pending_stock,
        'time': get_ph_time().strftime('%I:%M:%S %p'),
    })


@inventory_bp.route('/staff/inventory/recipes')
@inventory_bp.route('/admin/inventory/recipes')
def inventory_recipes():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    base_layout = 'admin/base.html' if request.path.startswith('/admin') else 'layouts/staff_layout.html'
    from itertools import groupby
    user_branch = getattr(current_user, 'branch', None)
    
    menu_q = MenuItem.query.filter_by(is_deleted=False)
    if user_branch and user_branch != 'ALL':
        menu_q = menu_q.filter(MenuItem.branch == user_branch)
        
    all_menu_items = menu_q.order_by(MenuItem.category, MenuItem.name).all()
    grouped_items = {}
    for category, group in groupby(all_menu_items, lambda x: x.category or 'General'):
        grouped_items[category] = list(group)
        
    category_q = db.session.query(MenuItem.category).filter(MenuItem.is_deleted == False)
    if user_branch and user_branch != 'ALL':
        category_q = category_q.filter(MenuItem.branch == user_branch)
    menu_categories = [r[0] for r in category_q.distinct().order_by(MenuItem.category).all()]
    
    ing_q = Ingredient.query
    if user_branch and user_branch != 'ALL':
        ing_q = ing_q.filter_by(branch=user_branch)
    all_ingredients = ing_q.order_by(Ingredient.name).all()
    
    return render_template('inventory/recipes.html',
                           base_layout=base_layout,
                           portal_name=f"{current_user.first_name} {current_user.last_name}",
                           grouped_items=grouped_items,
                           menu_categories=menu_categories,
                           all_ingredients=all_ingredients)


@inventory_bp.route('/staff/inventory/recipes/<int:item_id>/ingredients', methods=['GET'])
def recipe_get_ingredients(item_id):
    """Return current recipe ingredients for a menu item as JSON."""
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    item = MenuItem.query.get_or_404(item_id)
    data = []
    for r in item.ingredients:
        data.append({
            'id': r.id,
            'ingredient_id': r.ingredient_id,
            'name': r.ingredient.name,
            'unit': r.ingredient.unit,
            'quantity_needed': float(r.quantity_needed),
        })
    return jsonify({'success': True, 'ingredients': data})


@inventory_bp.route('/staff/inventory/recipes/<int:item_id>/save', methods=['POST'])
def recipe_save_ingredients(item_id):
    """Save (replace) recipe ingredients for a menu item."""
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    item = MenuItem.query.get_or_404(item_id)
    data = request.get_json()
    if data is None:
        return jsonify({'success': False, 'message': 'No data provided.'}), 400

    rows = data.get('ingredients', [])

    # Delete existing recipe rows for this item
    MenuItemIngredient.query.filter_by(menu_item_id=item_id).delete()

    for row in rows:
        ing_id = row.get('ingredient_id')
        qty = row.get('quantity_needed', 0)
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            qty = 0
        if not ing_id or qty <= 0:
            continue
        ing = Ingredient.query.get(ing_id)
        if not ing:
            continue
        db.session.add(MenuItemIngredient(
            menu_item_id=item_id,
            ingredient_id=ing_id,
            quantity_needed=qty,
        ))

    db.session.commit()
    return jsonify({'success': True, 'message': f'Recipe for "{item.name}" saved successfully!'})


@inventory_bp.route('/staff/inventory/recipes/add', methods=['POST'])
def inventory_add_recipe_item():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': False, 'message': 'Session expired or unauthorized.'}), 403
        return redirect(url_for('cashier_portal.staff_login'))
        
    name = request.form.get('name', '').strip()
    category = request.form.get('category', '').strip() or 'General'
    description = request.form.get('description', '').strip()
    
    try:
        price = float(request.form.get('price', 0))
    except (ValueError, TypeError):
        price = 0.0
        
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    
    if not name:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Menu item name is required.'}), 400
        flash('Menu item name is required.', 'danger')
        return redirect(url_for('inventory_portal.inventory_recipes'))
        
    item = MenuItem(
        name=name,
        category=category,
        price=price,
        description=description,
        is_available=False
    )
    db.session.add(item)
    db.session.commit()
    
    from routes.admin import log_audit
    try:
        log_audit('CREATE', 'MenuItem', item.id, f'Added new menu item via Inventory: {item.name}')
    except:
        pass
        
    msg = f'Menu item "{name}" added successfully! You can now add its recipe ingredients.'
    if is_ajax:
        return jsonify({'success': True, 'message': msg})
    flash(msg, 'success')
    return redirect(url_for('inventory_portal.inventory_recipes'))


@inventory_bp.route('/staff/inventory/recipes/<int:item_id>/delete', methods=['POST'])
def inventory_delete_recipe_item(item_id):
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': False, 'message': 'Session expired or unauthorized.'}), 403
        return redirect(url_for('cashier_portal.staff_login'))
        
    item = MenuItem.query.get_or_404(item_id)
    item.is_deleted = True
    db.session.commit()
    
    from routes.admin import log_audit
    try:
        log_audit('DELETE', 'MenuItem', item.id, f'Trashed menu item via Inventory: {item.name}')
    except:
        pass
        
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    msg = f'Menu item "{item.name}" deleted successfully.'
    if is_ajax:
        return jsonify({'success': True, 'message': msg})
    flash(msg, 'success')
    return redirect(url_for('inventory_portal.inventory_recipes'))


@inventory_bp.route('/staff/inventory/batches')
@inventory_bp.route('/admin/inventory/batches')
def inventory_ingredient_batches():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    base_layout = 'admin/base.html' if request.path.startswith('/admin') else 'layouts/staff_layout.html'
    from datetime import date
    from sqlalchemy.orm import selectinload
    
    user_branch = getattr(current_user, 'branch', None)
    ing_q = Ingredient.query
    batch_q = IngredientBatch.query.filter_by(is_exhausted=False)
    
    if user_branch and user_branch != 'ALL':
        ing_q = ing_q.filter_by(branch=user_branch)
        batch_q = batch_q.join(Ingredient).filter(Ingredient.branch == user_branch)
        
    ingredients = ing_q.order_by(Ingredient.name).all()
    today = date.today()
    batches = (
        batch_q
        .options(selectinload(IngredientBatch.ingredient))
        .order_by(IngredientBatch.purchase_date.asc())
        .all()
    )

    category_q = db.session.query(MenuItem.category).filter(MenuItem.is_deleted == False)
    if user_branch and user_branch != 'ALL':
        category_q = category_q.filter(MenuItem.branch == user_branch)
    menu_categories = [r[0] for r in category_q.distinct().order_by(MenuItem.category).all()]

    # Mapping ingredients to their menu categories for client-side filtering
    ing_menu_cats = {}
    for ing in ingredients:
        cats = db.session.query(MenuItem.category).join(MenuItemIngredient, MenuItem.id == MenuItemIngredient.menu_item_id).filter(
            MenuItemIngredient.ingredient_id == ing.id
        ).distinct().all()
        ing_menu_cats[ing.id] = [c[0] for c in cats if c[0]]

    return render_template('staff/batches.html',
                           base_layout=base_layout,
                           batches=batches,
                           ingredients=ingredients,
                           today=today,
                           menu_categories=menu_categories,
                           ing_menu_cats=ing_menu_cats)


@inventory_bp.route('/staff/inventory/batches/add', methods=['POST'])
def inventory_add_ingredient_batch():
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
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
    msg = f"Inventory record updated. {batch_qty} {ing.unit} added to FIFO queue."
    if is_ajax:
        return jsonify({
            'success': True,
            'message': msg,
            'ingredient': {
                'id': ing.id,
                'name': ing.name,
                'stock_qty': float(ing.stock_qty),
                'unit': ing.unit
            }
        })
    flash(msg, "success")
    return redirect(url_for('inventory_portal.inventory_ingredient_batches'))

@inventory_bp.route('/staff/inventory/full')
@inventory_bp.route('/admin/inventory/full')
def inventory_full():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    base_layout = 'admin/base.html' if request.path.startswith('/admin') else 'layouts/staff_layout.html'
    user_branch = getattr(current_user, 'branch', None)
    query = Ingredient.query
    if user_branch and user_branch != 'ALL':
        query = query.filter_by(branch=user_branch)
    all_ingredients = query.order_by(Ingredient.name).all()
    cats_by_ing = _get_ingredient_food_categories()
    
    categories = set()
    for ing in all_ingredients:
        ing_cats = cats_by_ing.get(ing.id) or [ing.category or 'General']
        ing.food_categories = ing_cats
        for c in ing_cats:
            categories.add(c)
            
    categories = sorted(list(categories))
    suppliers = Supplier.query.order_by(Supplier.name).all()
    
    return render_template('inventory/full.html',
                           base_layout=base_layout,
                           ingredients=all_ingredients,
                           categories=categories,
                           suppliers=suppliers,
                           portal_name=f"{current_user.first_name} {current_user.last_name}")

@inventory_bp.route('/staff/inventory/ingredient-setup')
@inventory_bp.route('/admin/inventory/ingredient-setup')
def inventory_ingredient_setup():
    """Dedicated page to assign supplier, category, and code to unsetup ingredients."""
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))

    base_layout = 'admin/base.html' if request.path.startswith('/admin') else 'layouts/staff_layout.html'
    from sqlalchemy import or_

    user_branch = getattr(current_user, 'branch', None)
    query = Ingredient.query.filter(
        or_(
            Ingredient.category == 'Unassigned',
            Ingredient.category == None,
            Ingredient.category == ''
        )
    )
    if user_branch and user_branch != 'ALL':
        query = query.filter_by(branch=user_branch)

    unassigned_ingredients = query.order_by(Ingredient.name).all()

    suppliers_list = Supplier.query.order_by(Supplier.name).all()

    menu_categories = [r[0] for r in db.session.query(MenuItem.category)
                       .filter(MenuItem.is_deleted == False)
                       .distinct().order_by(MenuItem.category).all()]

    return render_template(
        'inventory/ingredient_setup.html',
        base_layout=base_layout,
        ingredients=unassigned_ingredients,
        suppliers=suppliers_list,
        menu_categories=menu_categories,
        portal_name=f"{current_user.first_name} {current_user.last_name}"
    )


@inventory_bp.route('/api/ingredients/<int:ing_id>/setup', methods=['POST'])
def api_ingredient_setup(ing_id):
    """API: Update category, supplier, and code for a single ingredient."""
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()


    ing = Ingredient.query.get(ing_id)
    if not ing:
        return jsonify({'success': False, 'message': 'Ingredient not found.'})

    new_category = data.get('category', '').strip()
    new_supplier_id = data.get('supplier_id')
    new_code = data.get('ingredient_code', '').strip()

    if new_category:
        ing.category = new_category
    if new_supplier_id:
        ing.supplier_id = int(new_supplier_id)
    elif new_supplier_id == 0 or new_supplier_id is None and 'supplier_id' in data:
        ing.supplier_id = None
    if new_code:
        # Check uniqueness
        existing = Ingredient.query.filter(
            Ingredient.ingredient_code == new_code,
            Ingredient.id != ing.id
        ).first()
        if existing:
            return jsonify({'success': False, 'message': f'Code "{new_code}" is already used by "{existing.name}".'})
        ing.ingredient_code = new_code

    db.session.commit()
    return jsonify({
        'success': True,
        'message': f'"{ing.name}" updated successfully.',
        'ingredient': {
            'id': ing.id,
            'name': ing.name,
            'category': ing.category,
            'supplier_id': ing.supplier_id,
            'ingredient_code': ing.ingredient_code
        }
    })


@inventory_bp.route('/staff/inventory/suppliers')
@inventory_bp.route('/admin/inventory/suppliers')
def inventory_suppliers():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    base_layout = 'admin/base.html' if request.path.startswith('/admin') else 'layouts/staff_layout.html'
    from collections import defaultdict
    from models import SupplierPayment
    
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
            # Use explicit category from DB if set, otherwise resolve dynamically or default to "General"
            if sup.category:
                pass  # already set from DB
            else:
                mapped_cats = cats_by_sup.get(sup.id, [])
                sup.category = mapped_cats[0] if mapped_cats else "General"
    
    # Fetch all active menu categories for the dropdown selectors
    menu_categories = [r[0] for r in db.session.query(MenuItem.category)
                       .filter(MenuItem.is_deleted == False)
                       .distinct().order_by(MenuItem.category).all()]
    
    # Kumuha ng mga kamakailang bayad sa supplier para sa branch na ito
    user_branch = getattr(current_user, 'branch', None)
    payment_query = SupplierPayment.query
    if user_branch and user_branch != 'ALL':
        payment_query = payment_query.filter_by(branch=user_branch)
    recent_payments = payment_query.order_by(SupplierPayment.created_at.desc()).limit(15).all()

    # Calculate available branch funds for validation
    from models import Order
    target_branch = user_branch if (user_branch and user_branch != 'ALL') else 'Pagsanjan'
    br_order_revenue = float(db.session.query(func.coalesce(func.sum(Order.total_amount), 0)).filter(Order.branch == target_branch).scalar())
    br_expenses = float(db.session.query(func.coalesce(func.sum(SupplierPayment.amount), 0)).filter(SupplierPayment.branch == target_branch).scalar())
    available_funds = br_order_revenue - br_expenses
    
    return render_template('inventory/suppliers.html',
                           base_layout=base_layout,
                           suppliers=suppliers_list,
                           menu_categories=menu_categories,
                           recent_payments=recent_payments,
                           portal_name=f"{current_user.first_name} {current_user.last_name}",
                           available_funds=available_funds,
                           target_branch=target_branch)

@inventory_bp.route('/staff/inventory/ingredients/add', methods=['POST'])
def inventory_add_ingredient():
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
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
        msg = 'Ingredient name is required.'
        if is_ajax:
            return jsonify({'success': False, 'message': msg}), 400
        flash(msg, 'danger')
        return redirect(url_for('inventory_portal.inventory_dashboard'))
        
    ing = Ingredient(
        name=name, unit=unit, category=category, 
        stock_qty=stock_qty, reorder_level=reorder_level,
        cost_per_unit=cost_per_unit, supplier_id=supplier_id,
        expiration_date=expiration_date
    )
    db.session.add(ing)
    db.session.commit()
    msg = f'Ingredient "{name}" added successfully!'
    if is_ajax:
        return jsonify({
            'success': True,
            'message': msg,
            'ingredient': {
                'id': ing.id,
                'name': ing.name,
                'unit': ing.unit,
                'category': ing.category,
                'stock_qty': float(ing.stock_qty)
            }
        })
    flash(msg, 'success')
    return redirect(url_for('inventory_portal.inventory_full'))

@inventory_bp.route('/staff/inventory/ingredients/edit/<int:ing_id>', methods=['POST'])
@inventory_bp.route('/admin/inventory/ingredients/edit/<int:ing_id>', methods=['POST'])
def inventory_edit_ingredient(ing_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if not current_user.is_authenticated or current_user.role.upper() not in ['ADMIN', 'SUPER_ADMIN']:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Forbidden: Only Administrators can edit ingredient metadata.'}), 403
        flash('Unauthorized: Only Administrators can edit ingredient metadata.', 'danger')
        return redirect(request.referrer or url_for('inventory_portal.inventory_full'))

    ing = Ingredient.query.get_or_404(ing_id)
    old_name = ing.name
    
    name = request.form.get('name', '').strip()
    ingredient_code = request.form.get('ingredient_code', '').strip()
    category = request.form.get('category', '').strip()
    unit = request.form.get('unit', '').strip()
    reorder_level = request.form.get('reorder_level', type=float)

    # CRITICAL ANTI-FRAUD RULE: Stock quantity is kept strictly untouched from this endpoint!

    if name:
        ing.name = name
    if ingredient_code:
        ing.ingredient_code = ingredient_code
    if unit:
        ing.unit = unit
    if reorder_level is not None:
        ing.reorder_level = reorder_level
        
    if category:
        ing.food_categories = [category]

    # Task 3: Audit History Dispatch
    from models import InventoryLog, AuditLog
    
    inv_log = InventoryLog(
        ingredient_id=ing.id,
        user_id=current_user.id,
        action='EDIT',
        quantity_changed=0,
        new_stock_qty=ing.stock_qty,
        notes=f"Updated ingredient metadata ({old_name} -> {ing.name})"
    )
    db.session.add(inv_log)

    audit_log = AuditLog(
        user_id=current_user.id,
        action='EDIT',
        target_type='Ingredient',
        target_id=ing.id,
        description=f"Updated ingredient metadata for '{ing.name}' (Code: {ing.ingredient_code}, Unit: {ing.unit}, Reorder Level: {ing.reorder_level})",
        ip_address=request.remote_addr
    )
    db.session.add(audit_log)
    
    db.session.commit()

    msg = f'Ingredient "{ing.name}" metadata updated successfully.'
    if is_ajax:
        return jsonify({'success': True, 'message': msg})
    flash(msg, 'success')

    referrer = request.referrer
    if referrer and ('/inventory/full' in referrer or '/inventory/levels' in referrer):
        return redirect(referrer)
    return redirect(url_for('inventory_portal.inventory_full'))

@inventory_bp.route('/staff/inventory/suppliers/add', methods=['POST'])
def inventory_add_supplier():
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        return redirect(url_for('cashier_portal.staff_login'))
        
    name = request.form.get('name', '').strip()
    contact_person = request.form.get('contact_person', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    address = request.form.get('address', '').strip()
    category = request.form.get('category', '').strip()
    
    if not name:
        msg = 'Supplier name is required.'
        if is_ajax:
            return jsonify({'success': False, 'message': msg}), 400
        flash(msg, 'danger')
        return redirect(url_for('inventory_portal.inventory_suppliers'))
        
    sup = Supplier(name=name, contact_person=contact_person, phone=phone, email=email, address=address, category=category)
    db.session.add(sup)
    db.session.commit()
    
    new_ingredients_str = request.form.get('new_ingredients', '').strip()
    if new_ingredients_str:
        # Also link/create actual Ingredient records linked to this supplier
        for ing_name in [i.strip() for i in new_ingredients_str.split(',') if i.strip()]:
            # First check if any ingredient with this name already exists in the system (linked or unlinked)
            existing = Ingredient.query.filter(
                db.func.lower(Ingredient.name) == ing_name.lower()
            ).first()
            if existing:
                existing.supplier_id = sup.id
            else:
                new_ing = Ingredient(
                    name=ing_name,
                    unit='pcs',
                    stock_qty=0,
                    supplier_id=sup.id
                )
                db.session.add(new_ing)
        db.session.commit()
        # Update catalog_items to match actual linked ingredients
        names = [i.name for i in sup.ingredients]
        sup.catalog_items = ", ".join(sorted(names)) if names else ""
        db.session.commit()
        
    msg = f'Supplier "{name}" added successfully!'
    if is_ajax:
        return jsonify({
            'success': True,
            'message': msg,
            'supplier': {
                'id': sup.id,
                'name': sup.name,
                'category': sup.category,
                'catalog_items': sup.catalog_items
            }
        })
    flash(msg, 'success')
    return redirect(url_for('inventory_portal.inventory_suppliers'))

@inventory_bp.route('/staff/inventory/suppliers/delete/<int:sup_id>', methods=['POST'])
def inventory_delete_supplier(sup_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        return redirect(url_for('cashier_portal.staff_login'))

    sup = Supplier.query.get_or_404(sup_id)
    sup_name = sup.name
    # Unlink ingredients but don't delete them
    Ingredient.query.filter_by(supplier_id=sup_id).update({'supplier_id': None})
    db.session.delete(sup)
    db.session.commit()
    
    msg = f'Supplier "{sup_name}" deleted.'
    if is_ajax:
        return jsonify({'success': True, 'message': msg})
    flash(msg, 'success')
    return redirect(url_for('inventory_portal.inventory_suppliers'))

@inventory_bp.route('/staff/inventory/suppliers/update/<int:sup_id>', methods=['POST'])
def inventory_update_supplier(sup_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        return redirect(url_for('cashier_portal.staff_login'))

    sup = Supplier.query.get_or_404(sup_id)
    sup.name = request.form.get('name', sup.name).strip()
    sup.contact_person = request.form.get('contact_person', '').strip()
    sup.phone = request.form.get('phone', '').strip()
    sup.email = request.form.get('email', '').strip()
    sup.address = request.form.get('address', '').strip()
    sup.category = request.form.get('category', '').strip()

    new_catalog = request.form.get('new_ingredients', '').strip()
    if new_catalog is not None:
        # Create/Link new Ingredient records for any names not yet linked to this supplier
        for ing_name in [i.strip() for i in new_catalog.split(',') if i.strip()]:
            existing = Ingredient.query.filter(
                db.func.lower(Ingredient.name) == ing_name.lower()
            ).first()
            if existing:
                existing.supplier_id = sup.id
            else:
                db.session.add(Ingredient(
                    name=ing_name,
                    unit='pcs',
                    stock_qty=0,
                    supplier_id=sup.id
                ))
        db.session.commit()
        # Update catalog_items to match actual linked ingredients
        names = [i.name for i in sup.ingredients]
        sup.catalog_items = ", ".join(sorted(names)) if names else ""

    db.session.commit()
    msg = f'Supplier "{sup.name}" updated successfully!'
    if is_ajax:
        return jsonify({
            'success': True,
            'message': msg,
            'supplier': {
                'id': sup.id,
                'name': sup.name,
                'category': sup.category,
                'catalog_items': sup.catalog_items
            }
        })
    flash(msg, 'success')
    return redirect(url_for('inventory_portal.inventory_suppliers'))

@inventory_bp.route('/staff/inventory/ingredients/restock/<int:ing_id>', methods=['POST'])
def inventory_restock(ing_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        return redirect(url_for('cashier_portal.staff_login'))
    
    ing = Ingredient.query.get_or_404(ing_id)
    add_qty = request.form.get('add_qty', 0, type=float)
    if add_qty > 0:
        ing.stock_qty += add_qty
        db.session.commit()
        msg = f'Restocked {add_qty} {ing.unit} to {ing.name}.'
        if is_ajax:
            return jsonify({
                'success': True,
                'message': msg,
                'ingredient': {
                    'id': ing.id,
                    'name': ing.name,
                    'stock_qty': float(ing.stock_qty),
                    'unit': ing.unit
                }
            })
        flash(msg, 'success')
    return redirect(url_for('inventory_portal.inventory_dashboard'))

@inventory_bp.route('/staff/inventory/ingredients/waste/add', methods=['POST'])
def inventory_add_waste():
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
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
    
    msg = f'Recorded waste for {ing.name}.'
    if is_ajax:
        return jsonify({
            'success': True,
            'message': msg,
            'ingredient': {
                'id': ing.id,
                'name': ing.name,
                'stock_qty': float(ing.stock_qty),
                'unit': ing.unit
            }
        })
    flash(msg, 'warning')
    return redirect(url_for('inventory_portal.inventory_dashboard'))


@inventory_bp.route('/staff/inventory/ingredients/delete/<int:ing_id>', methods=['POST'])
def inventory_delete_ingredient(ing_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        return redirect(url_for('cashier_portal.staff_login'))
        
    ing = Ingredient.query.get_or_404(ing_id)
    ing_name = ing.name
    
    # Delete related records due to Foreign Key constraints
    MenuItemIngredient.query.filter_by(ingredient_id=ing_id).delete()
    
    from models import InventoryLog
    InventoryLog.query.filter_by(ingredient_id=ing_id).delete()
    
    WasteRecord.query.filter_by(ingredient_id=ing_id).delete()
    
    IngredientBatch.query.filter_by(ingredient_id=ing_id).delete()
    
    from models import StockRequest
    StockRequest.query.filter_by(ingredient_id=ing_id).delete()
    
    # Log audit entry
    from models import AuditLog
    log = AuditLog(
        user_id=current_user.id,
        action='DELETE',
        target_type='Ingredient',
        target_id=ing_id,
        description=f"Deleted Ingredient: {ing_name}",
        ip_address=request.remote_addr
    )
    db.session.add(log)
    
    # Delete the ingredient
    db.session.delete(ing)
    db.session.commit()
    
    msg = f'Ingredient "{ing_name}" has been permanently deleted from stock levels.'
    if is_ajax:
        return jsonify({'success': True, 'message': msg})
    flash(msg, 'success')
    
    referrer = request.referrer
    if referrer and ('/staff/inventory/full' in referrer):
        return redirect(url_for('inventory_portal.inventory_full'))
    return redirect(url_for('inventory_portal.inventory_dashboard'))



@inventory_bp.route('/staff/inventory/waste')
@inventory_bp.route('/admin/inventory/waste')
def inventory_waste_records():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    base_layout = 'admin/base.html' if request.path.startswith('/admin') else 'layouts/staff_layout.html'
    waste_records_list = WasteRecord.query.order_by(WasteRecord.created_at.desc()).limit(100).all()
    return render_template('inventory/waste.html',
                           base_layout=base_layout,
                           waste_records=waste_records_list,
                           portal_name=f"{current_user.first_name} {current_user.last_name}")

@inventory_bp.route('/staff/inventory/stock-requests')
@inventory_bp.route('/admin/inventory/stock-requests')
def inventory_stock_requests():
    from routes.admin import stock_requests
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    return stock_requests()

@inventory_bp.route('/staff/inventory/audit')
@inventory_bp.route('/admin/inventory/audit')
def inventory_audit():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
        
    base_layout = 'admin/base.html' if request.path.startswith('/admin') else 'layouts/staff_layout.html'
    from models import InventoryLog, Ingredient
    
    ing_filter = request.args.get('ingredient_id', type=int)
    action_filter = request.args.get('action', '')
    query = InventoryLog.query
    if ing_filter:
        query = query.filter_by(ingredient_id=ing_filter)
    if action_filter:
        query = query.filter_by(action=action_filter)
    logs = query.order_by(InventoryLog.created_at.desc()).limit(200).all()
    ingredients = Ingredient.query.order_by(Ingredient.name).limit(500).all()
    
    return render_template('inventory/audit.html',
                           base_layout=base_layout,
                           logs=logs, 
                           ingredients=ingredients,
                           ing_filter=ing_filter, 
                           action_filter=action_filter,
                           portal_name=f"{current_user.first_name} {current_user.last_name}")

@inventory_bp.route('/staff/inventory/suppliers/<int:sup_id>/ingredients')
def supplier_ingredients_api(sup_id):
    """API: Return all ingredients used in this supplier's menu category (for the receive modal).
    
    Instead of filtering by supplier_id (which is a 1:1 assignment and misses shared ingredients),
    we look up the supplier's category and return ALL ingredients used in recipes for that category.
    This ensures the modal always shows the correct, complete list matching the supplier's role.
    """
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    
    supplier = Supplier.query.get_or_404(sup_id)
    sup_category = supplier.category  # e.g. "Milkshakes & Smoothies"
    
    ingredients_dict = {}
    
    # 1. Fetch ingredients directly assigned to the supplier by supplier_id
    direct_ings = Ingredient.query.filter_by(supplier_id=sup_id).all()
    for ing in direct_ings:
        ingredients_dict[ing.id] = ing
        
    # 2. Fetch ingredients associated with recipes in the supplier's category
    if sup_category:
        linked_ing_ids = (
            db.session.query(MenuItemIngredient.ingredient_id)
            .join(MenuItem, MenuItem.id == MenuItemIngredient.menu_item_id)
            .filter(MenuItem.category == sup_category, MenuItem.is_deleted == False)
            .distinct()
            .all()
        )
        linked_ing_ids = [r[0] for r in linked_ing_ids]
        if linked_ing_ids:
            cat_ings = Ingredient.query.filter(Ingredient.id.in_(linked_ing_ids)).all()
            for ing in cat_ings:
                ingredients_dict[ing.id] = ing
                
    # Sort ingredients by category, then name
    ingredients = sorted(ingredients_dict.values(), key=lambda x: (x.category or 'General', x.name))
    
    result = []
    user_branch = getattr(current_user, 'branch', None)
    for ing in ingredients:
        stock_qty = float(ing.stock_qty)
        ing_id = ing.id
        # If user is a branch staff, resolve branch-specific stock levels
        if user_branch and user_branch != 'ALL' and ing.branch != user_branch:
            br_ing = Ingredient.query.filter_by(name=ing.name, branch=user_branch).first()
            if br_ing:
                stock_qty = float(br_ing.stock_qty)
                ing_id = br_ing.id
            else:
                stock_qty = 0.0
                
        result.append({
            'id': ing_id,
            'name': ing.name,
            'ingredient_code': ing.ingredient_code,
            'unit': ing.unit,
            'category': ing.category or 'General',
            'stock_qty': stock_qty,
            'cost_per_unit': float(ing.cost_per_unit or 0),
        })
    return jsonify({'success': True, 'ingredients': result})


@inventory_bp.route('/api/ingredients/all')
def get_all_ingredients():
    """API: Return all ingredients in the system for dropdown population."""
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    
    user_branch = getattr(current_user, 'branch', None)
    query = Ingredient.query
    
    # Filter by branch if applicable
    if user_branch and user_branch != 'ALL':
        query = query.filter_by(branch=user_branch)
    
    ingredients = query.order_by(Ingredient.name).all()
    
    result = [{
        'id': ing.id,
        'name': ing.name,
        'unit': ing.unit,
        'category': ing.category or 'General',
        'supplier_id': ing.supplier_id
    } for ing in ingredients]
    
    return jsonify({'success': True, 'ingredients': result})


@inventory_bp.route('/api/suppliers/<int:sup_id>/ingredients')
def get_supplier_ingredients(sup_id):
    """API: Return only ingredients linked to this specific supplier."""
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get only ingredients assigned to this supplier
    ingredients = Ingredient.query.filter_by(supplier_id=sup_id).order_by(Ingredient.name).all()
    
    result = [{
        'id': ing.id,
        'name': ing.name,
        'unit': ing.unit,
        'category': ing.category or 'General',
        'supplier_id': ing.supplier_id
    } for ing in ingredients]
    
    return jsonify({'success': True, 'ingredients': result})


@inventory_bp.route('/api/ingredients/add', methods=['POST'])
def add_ingredient_api():
    """API: Add a new ingredient to the system."""
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    name = data.get('name', '').strip()
    unit = data.get('unit', 'pcs').strip()
    category = data.get('category', 'General').strip()
    cost_per_unit = float(data.get('cost_per_unit', 0))
    reorder_level = float(data.get('reorder_level', 10))
    
    if not name:
        return jsonify({'success': False, 'message': 'Ingredient name is required.'})
    
    # Check if ingredient already exists
    existing = Ingredient.query.filter(db.func.lower(Ingredient.name) == name.lower()).first()
    if existing:
        return jsonify({'success': False, 'message': 'Ingredient already exists.'})
    
    # Get user's branch
    user_branch = getattr(current_user, 'branch', 'Pagsanjan')
    if user_branch == 'ALL':
        user_branch = 'Pagsanjan'  # Default for super admin
    
    # Create new ingredient
    new_ing = Ingredient(
        name=name,
        unit=unit,
        category=category,
        cost_per_unit=cost_per_unit,
        reorder_level=reorder_level,
        stock_qty=0,
        kitchen_qty=0,
        branch=user_branch,
        supplier_id=None
    )
    
    db.session.add(new_ing)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Ingredient added successfully!',
        'ingredient': {
            'id': new_ing.id,
            'name': new_ing.name,
            'unit': new_ing.unit,
            'category': new_ing.category,
            'supplier_id': new_ing.supplier_id
        }
    })


@inventory_bp.route('/api/ingredients/assign-supplier', methods=['POST'])
def assign_ingredient_supplier():
    """API: Assign an ingredient to a supplier (or unassign by passing supplier_id=null)."""
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    ingredient_id = data.get('ingredient_id')
    supplier_id = data.get('supplier_id')  # None means unassign

    if not ingredient_id:
        return jsonify({'success': False, 'message': 'ingredient_id is required.'})

    ing = Ingredient.query.get(ingredient_id)
    if not ing:
        return jsonify({'success': False, 'message': 'Ingredient not found.'})

    if supplier_id:
        sup = Supplier.query.get(supplier_id)
        if not sup:
            return jsonify({'success': False, 'message': 'Supplier not found.'})
        ing.supplier_id = int(supplier_id)
    else:
        ing.supplier_id = None

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Ingredient "{ing.name}" assigned successfully.',
        'ingredient': {
            'id': ing.id,
            'name': ing.name,
            'supplier_id': ing.supplier_id
        }
    })


@inventory_bp.route('/api/ingredients/unassigned')
def get_unassigned_ingredients():
    """API: Return all ingredients with no supplier assigned."""
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403

    user_branch = getattr(current_user, 'branch', None)
    query = Ingredient.query.filter(Ingredient.supplier_id == None)

    if user_branch and user_branch != 'ALL':
        query = query.filter_by(branch=user_branch)

    ingredients = query.order_by(Ingredient.name).all()

    result = [{
        'id': ing.id,
        'name': ing.name,
        'unit': ing.unit,
        'category': ing.category or 'Unassigned',
        'stock_qty': float(ing.stock_qty or 0),
        'cost_per_unit': float(ing.cost_per_unit or 0)
    } for ing in ingredients]

    return jsonify({'success': True, 'ingredients': result})


@inventory_bp.route('/staff/inventory/suppliers/<int:sup_id>/receive', methods=['POST'])
def supplier_receive_delivery(sup_id):
    """Process a supply delivery: add stock to warehouse inventory for each received ingredient."""
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    
    from routes.admin import log_inventory_change, process_fifo_transaction
    from models import SupplierPayment, Ingredient
    
    supplier = Supplier.query.get_or_404(sup_id)
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'message': 'No data provided.'})
    
    user_branch = getattr(current_user, 'branch', None)
    target_branch = user_branch if (user_branch and user_branch != 'ALL') else 'Pagsanjan'
    
    received_items = data.get('items', [])  # Existing ingredients
    new_items = data.get('new_items', [])  # New ingredients to create
    
    total_received = 0
    total_cost = 0
    details = []
    
    # Process NEW ingredients first (create them)
    for new_item in new_items:
        name = new_item.get('name', '').strip()
        unit = new_item.get('unit', 'pcs')
        cost_per_unit = float(new_item.get('cost_per_unit', 0))
        qty = float(new_item.get('qty_received', 0))
        
        if not name or qty <= 0:
            continue
        
        # Check if ingredient already exists
        existing_ing = Ingredient.query.filter(
            db.func.lower(Ingredient.name) == name.lower(),
            Ingredient.branch == target_branch
        ).first()
        
        if existing_ing:
            # Use existing ingredient
            target_ing = existing_ing
        else:
            # Create new ingredient with "Unassigned" category
            target_ing = Ingredient(
                name=name,
                branch=target_branch,
                unit=unit,
                stock_qty=0,
                kitchen_qty=0,
                reorder_level=10,
                cost_per_unit=cost_per_unit,
                category='Unassigned',  # ← KEY! Will appear in sidebar
                supplier_id=sup_id
            )
            db.session.add(target_ing)
            db.session.flush()  # Get the ID
        
        # Update stock
        prev_stock = float(target_ing.stock_qty)
        target_ing.stock_qty = prev_stock + qty
        log_inventory_change(target_ing.id, 'ADD', qty, prev_stock, f'New Supply from {supplier.name} (First Delivery)')
        
        # Create FIFO Batch
        process_fifo_transaction(target_ing.id, 'ADD', qty, cost_per_unit=cost_per_unit)
        
        item_cost = qty * cost_per_unit
        total_cost += item_cost
        total_received += 1
        details.append(f'🆕 +{qty} {unit} {name} (₱{item_cost:,.2f}) - NEW!')
    
    # Process EXISTING ingredients
    for item in received_items:
        ing_id = item.get('ingredient_id')
        qty = float(item.get('qty_received', 0))
        
        if qty <= 0:
            continue
            
        ing = Ingredient.query.get(ing_id)
        if not ing:
            continue
        
        # Check if delivery is for different branch
        target_ing = ing
        if ing.branch != target_branch:
            existing = Ingredient.query.filter_by(name=ing.name, branch=target_branch).first()
            if existing:
                target_ing = existing
            else:
                # Clone ingredient for this branch
                target_ing = Ingredient(
                    name=ing.name,
                    branch=target_branch,
                    unit=ing.unit,
                    stock_qty=0,
                    kitchen_qty=0,
                    reorder_level=ing.reorder_level,
                    cost_per_unit=ing.cost_per_unit,
                    category=ing.category or 'General',
                    supplier_id=sup_id
                )
                db.session.add(target_ing)
                db.session.flush()
        
        # Update stock
        prev_stock = float(target_ing.stock_qty)
        target_ing.stock_qty = prev_stock + qty
        log_inventory_change(target_ing.id, 'ADD', qty, prev_stock, f'Supply Received from {supplier.name} for {target_branch}')
        
        # Create FIFO Batch
        unit_cost = float(target_ing.cost_per_unit or 0)
        process_fifo_transaction(target_ing.id, 'ADD', qty, cost_per_unit=unit_cost)
        
        item_cost = qty * unit_cost
        total_cost += item_cost
        total_received += 1
        details.append(f'+{qty} {target_ing.unit} {target_ing.name} (₱{item_cost:,.2f})')
    
    if total_received == 0:
        return jsonify({'success': False, 'message': 'No valid items to receive. Please enter quantities.'})

    # Calculate available branch funds and validate
    from models import Order
    br_order_revenue = float(db.session.query(func.coalesce(func.sum(Order.total_amount), 0)).filter(Order.branch == target_branch).scalar())
    br_expenses = float(db.session.query(func.coalesce(func.sum(SupplierPayment.amount), 0)).filter(SupplierPayment.branch == target_branch).scalar())
    available_funds = br_order_revenue - br_expenses

    if total_cost > available_funds:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'❌ Failed to receive: Insufficient funds in {target_branch} branch. (Available: ₱{available_funds:,.2f}, Required: ₱{total_cost:,.2f})'
        })
    
    # Record Supplier Payment / Expense
    payment = SupplierPayment(
        supplier_id=sup_id,
        branch=target_branch,
        amount=total_cost,
        details="; ".join(details),
        processed_by_id=current_user.id
    )
    db.session.add(payment)
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'✅ Received {total_received} item(s) from {supplier.name}! Total cost: ₱{total_cost:,.2f}',
        'details': details
    })


# ─── OCR DELIVERY RECEIPT UPLOAD ─────────────────────────────────────────────
@inventory_bp.route('/staff/inventory/suppliers/ocr-scan', methods=['POST'])
@login_required
def supplier_ocr_scan():
    """
    Upload a delivery receipt image (jpg/png/pdf).
    Uses Tesseract OCR to extract text, then parses supplier name and items.
    Validates: supplier name match, today-only date, supplier-item ownership.
    Returns JSON with extracted data for preview before confirming.
    """
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    if 'receipt_file' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded.'})

    file = request.files['receipt_file']
    if not file or file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected.'})

    allowed_ext = {'png', 'jpg', 'jpeg', 'bmp', 'tiff', 'tif', 'webp', 'pdf'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed_ext:
        return jsonify({'success': False, 'message': f'File type .{ext} not supported. Use PNG, JPG, or PDF.'})

    try:
        import pytesseract
        from PIL import Image, ImageEnhance, ImageFilter
        import io, re
        from datetime import date as _date, timedelta

        pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

        file_bytes = file.read()

        # Handle PDF
        if ext == 'pdf':
            try:
                import fitz
                pdf_doc = fitz.open(stream=file_bytes, filetype='pdf')
                pix = pdf_doc[0].get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                image = Image.open(io.BytesIO(pix.tobytes('png')))
            except ImportError:
                return jsonify({'success': False, 'message': 'PDF support requires PyMuPDF. Please upload an image instead.'})
        else:
            image = Image.open(io.BytesIO(file_bytes))

        image = image.convert('L')
        image = ImageEnhance.Contrast(image).enhance(2.0)
        image = image.filter(ImageFilter.SHARPEN)

        raw_text = pytesseract.image_to_string(image, config='--psm 6')
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]

        today = _date.today()

        # ── MONTH NAMES & DATE REGEX ─────────────────────────────
        month_names = {
            'january','february','march','april','may','june','july','august',
            'september','october','november','december',
            'jan','feb','mar','apr','jun','jul','aug','sep','oct','nov','dec'
        }
        month_num = {
            'january':1,'february':2,'march':3,'april':4,'may':5,'june':6,
            'july':7,'august':8,'september':9,'october':10,'november':11,'december':12,
            'jan':1,'feb':2,'mar':3,'apr':4,'jun':6,'jul':7,'aug':8,
            'sep':9,'oct':10,'nov':11,'dec':12
        }
        date_line_re = re.compile(
            r'\b(january|february|march|april|may|june|july|august|september|october|'
            r'november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec|'
            r'\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})\b', re.IGNORECASE)

        # ── 1. EXTRACT DATE from receipt ─────────────────────────
        receipt_date = None
        # Pattern: "Month Day, Year"  e.g. "July 15, 2026" or "Jul 15 2026"
        date_full_re = re.compile(
            r'\b(january|february|march|april|may|june|july|august|september|october|'
            r'november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\s+'
            r'(\d{1,2})[,\s]+(\d{4})\b', re.IGNORECASE)
        # Pattern: numeric  "15/07/2026" or "07-15-2026"
        date_num_re = re.compile(
            r'\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{4})\b')

        for line in lines[:20]:
            m = date_full_re.search(line)
            if m:
                try:
                    mon = month_num.get(m.group(1).lower()[:3]) or month_num.get(m.group(1).lower())
                    if mon:
                        receipt_date = _date(int(m.group(3)), mon, int(m.group(2)))
                        break
                except Exception:
                    pass
            m2 = date_num_re.search(line)
            if m2:
                try:
                    d1, d2, yr = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
                    # Try MM/DD/YYYY first, then DD/MM/YYYY
                    try:
                        receipt_date = _date(yr, d1, d2)
                    except ValueError:
                        receipt_date = _date(yr, d2, d1)
                    break
                except Exception:
                    pass

        # VALIDATION 1 — Date must exist
        if receipt_date is None:
            return jsonify({
                'success': False,
                'message': '❌ Date not found in receipt. Please make sure the receipt has today\'s date (e.g. "Date: July 16, 2026").'
            })

        # VALIDATION 2 — Date must be today only (no future, no past)
        if receipt_date != today:
            return jsonify({
                'success': False,
                'message': f'❌ Invalid date on receipt. Receipt date is {receipt_date.strftime("%B %d, %Y")} but today is {today.strftime("%B %d, %Y")}. Only today\'s receipts are accepted.'
            })

        # ── 2. EXTRACT SUPPLIER NAME ─────────────────────────────
        supplier_name_raw = None
        supplier_keywords = ['supplier', 'from:', 'vendor', 'company', 'farm', 'trading',
                             'enterprises', 'corp', 'inc', 'aling', 'manong', 'store', 'panaderia']
        for line in lines[:15]:
            ll = line.lower()
            if date_line_re.search(line):
                continue
            for kw in supplier_keywords:
                if kw in ll:
                    supplier_name_raw = line.split(':', 1)[1].strip() if ':' in line else line.strip()
                    break
            if supplier_name_raw:
                break

        if not supplier_name_raw:
            for line in lines[:8]:
                if len(line) > 3 and not date_line_re.search(line) \
                        and not re.match(r'^[\d\s\-\/\.\,₱]+$', line):
                    supplier_name_raw = line
                    break

        # VALIDATION 3 — Supplier must exist in DB (fuzzy match)
        all_suppliers = Supplier.query.all()
        matched_supplier = None
        raw_lower = (supplier_name_raw or '').lower().strip()

        for sup in all_suppliers:
            sup_lower = sup.name.lower().strip()
            # Exact match or one name contains the other (first 5+ chars)
            if sup_lower == raw_lower or sup_lower in raw_lower or raw_lower in sup_lower:
                matched_supplier = sup
                break
            # Word-by-word match — if 2+ significant words match
            sup_words = set(sup_lower.split())
            raw_words = set(raw_lower.split())
            common = sup_words & raw_words - {'the','ni','ng','at','and','of','de','na'}
            if len(common) >= 2:
                matched_supplier = sup
                break

        if matched_supplier is None:
            known = ', '.join([s.name for s in all_suppliers]) or 'None registered'
            return jsonify({
                'success': False,
                'message': f'❌ Supplier "{supplier_name_raw}" not found. Registered suppliers: {known}. Please match the name exactly.'
            })

        # ── 3. PARSE ITEMS ───────────────────────────────────────
        item_re = re.compile(
            r'^([A-Za-z][A-Za-z\s\-\/]{1,40}?)\s+(\d+(?:\.\d+)?)\s*'
            r'(kg|g|liter|litre|L|pcs|pc|pack|bag|box|bottle|gallon|ml|oz|lb|kl|sack)\b',
            re.IGNORECASE
        )
        skip_words = {'total', 'date', 'invoice', 'receipt', 'delivery receipt',
                      'subtotal', 'vat', 'tax', 'amount', 'paid', 'change',
                      'cash', 'balance', 'supplier', 'vendor', 'from'}

        # Get all ingredients belonging to this supplier
        supplier_ingredients = {
            ing.name.lower(): ing
            for ing in Ingredient.query.filter_by(supplier_id=matched_supplier.id).all()
        }

        items = []
        seen_names = set()

        for line in lines:
            if date_line_re.search(line):
                continue
            m = item_re.match(line)
            if not m:
                continue

            name      = m.group(1).strip().title()
            qty       = float(m.group(2))
            unit      = m.group(3).lower()
            name_lower = name.lower().strip()

            if name_lower in month_names:
                continue
            if any(sw in name_lower for sw in skip_words):
                continue
            if len(name_lower) < 2 or qty <= 0 or name_lower in seen_names:
                continue

            seen_names.add(name_lower)

            first_word = name_lower.split()[0]

            # Try to match: 1) supplier's own ingredients first
            existing = (
                supplier_ingredients.get(name_lower)
                or next((v for k, v in supplier_ingredients.items() if name_lower in k or k in name_lower), None)
                or Ingredient.query.filter(db.func.lower(Ingredient.name) == name_lower).first()
                or Ingredient.query.filter(db.func.lower(Ingredient.name).contains(name_lower)).first()
                or Ingredient.query.filter(db.func.lower(Ingredient.name).contains(first_word)).first()
            )

            cost = float(existing.cost_per_unit) if existing and existing.cost_per_unit else 0.0

            # Determine if this is a new item not yet assigned to supplier
            is_supplier_item = existing and existing.supplier_id == matched_supplier.id
            is_new = existing is None
            # If item exists but belongs to different supplier, flag it
            is_wrong_supplier = existing and existing.supplier_id and existing.supplier_id != matched_supplier.id

            if is_wrong_supplier:
                # Still allow but flag as warning
                items.append({
                    'name': name,
                    'qty': qty,
                    'unit': unit,
                    'price': cost,
                    'line_total': round(qty * cost, 2),
                    'matched': existing.name,
                    'ingredient_id': existing.id,
                    'status': 'warning',  # belongs to different supplier
                    'status_label': 'Other Supplier',
                })
            elif is_new:
                items.append({
                    'name': name,
                    'qty': qty,
                    'unit': unit,
                    'price': 0.0,
                    'line_total': 0.0,
                    'matched': None,
                    'ingredient_id': None,
                    'status': 'new',
                    'status_label': 'NEW',
                })
            else:
                items.append({
                    'name': name,
                    'qty': qty,
                    'unit': unit,
                    'price': cost,
                    'line_total': round(qty * cost, 2),
                    'matched': existing.name,
                    'ingredient_id': existing.id,
                    'status': 'matched',
                    'status_label': existing.name,
                })

        if not items:
            return jsonify({
                'success': False,
                'message': '❌ No items found in receipt. Make sure items have a unit (e.g. "Tea Leaves 10 kg").'
            })

        return jsonify({
            'success': True,
            'raw_text': raw_text[:500],
            'supplier_name': matched_supplier.name,
            'supplier_id': matched_supplier.id,
            'receipt_date': receipt_date.strftime('%B %d, %Y'),
            'items': items,
            'item_count': len(items),
            'message': f'Extracted {len(items)} item(s) from receipt.'
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'OCR Error: {str(e)}'})


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
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if form_type == 'profile':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        phone_number = request.form.get('phone_number', '').strip()
        
        if not first_name or not last_name:
            if is_ajax:
                return jsonify({'success': False, 'message': 'First name and last name are required.'}), 400
            flash('First name and last name are required.', 'danger')
            return False
        
        user.first_name = first_name
        user.last_name = last_name
        user.phone_number = phone_number if phone_number else None
        db.session.commit()
        if is_ajax:
            return jsonify({'success': True, 'message': 'Profile updated successfully!'})
        flash('Profile updated successfully!', 'success')
        return True
        
    elif form_type == 'password':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not user.check_password(current_password):
            if is_ajax:
                return jsonify({'success': False, 'message': 'Current password is incorrect.'}), 400
            flash('Current password is incorrect.', 'danger')
            return False
        
        err = validate_password(new_password, confirm_password)
        if err:
            if is_ajax:
                return jsonify({'success': False, 'message': err}), 400
            flash(err, 'danger')
            return False
        
        user.set_password(new_password)
        db.session.commit()
        if is_ajax:
            return jsonify({'success': True, 'message': 'Password changed successfully!'})
        flash('Password changed successfully!', 'success')
        return True
    
    if is_ajax:
        return jsonify({'success': False, 'message': 'Invalid request.'}), 400
    return False


# ── Kitchen Profile ──
@kitchen_bp.route('/staff/kitchen/profile', methods=['GET', 'POST'])
def kitchen_profile():
    if not current_user.is_authenticated or current_user.role not in KITCHEN_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
    if request.method == 'POST':
        res = _handle_profile_post(current_user)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return res
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
        res = _handle_profile_post(current_user)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return res
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
        res = _handle_profile_post(current_user)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return res
        return redirect(url_for('cashier_portal.cashier_profile'))
    
    sidebar_items = [
        {'url': url_for('cashier_portal.cashier_dashboard'), 'icon': 'shopping-bag', 'label': 'Orders'},
        {'url': url_for('cashier_portal.cashier_walkin_order'), 'icon': 'walking', 'label': 'Walk-In Order'},
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

RIDER_ROLES = ['RIDER']

@rider_bp.route('/rider/login', methods=['GET', 'POST'])
@rider_bp.route('/staff/rider/login', methods=['GET', 'POST'])
def rider_login():
    if current_user.is_authenticated and current_user.role in RIDER_ROLES:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'redirect': url_for('rider_portal.rider_dashboard')})
        return redirect(url_for('rider_portal.rider_dashboard'))
        
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if request.method == 'POST':
        user = _authenticate_portal(request.form.get('email'), request.form.get('password'), RIDER_ROLES)
        if user:
            session['logged_in_portal'] = 'rider'
            login_user(user)
            if is_ajax:
                return jsonify({'success': True, 'redirect': url_for('rider_portal.rider_dashboard')})
            return redirect(url_for('rider_portal.rider_dashboard'))
        if is_ajax:
            return jsonify({'success': False, 'message': 'Invalid credentials or insufficient permissions for Rider Portal.'}), 401
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
