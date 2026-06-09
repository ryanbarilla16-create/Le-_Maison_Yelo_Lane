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
    
    # Required by templates/cashier/dashboard.html: 
    # active_orders (count), completed_today (count), unpaid_orders (count), orders (list)
    
    today = get_ph_time().date()
    from models import Reservation
    
    active_orders_count = Order.query.outerjoin(Reservation).filter(
        Order.status.in_(['PENDING', 'PREPARING', 'READY']),
        db.or_(
            Order.reservation_id.is_(None),
            Reservation.date <= today
        )
    ).count()
    completed_today_count = Order.query.filter(Order.status == 'COMPLETED', db.func.date(Order.created_at) == today).count()
    unpaid_orders_count = Order.query.outerjoin(Reservation).filter(
        Order.payment_status == 'UNPAID',
        db.or_(
            Order.reservation_id.is_(None),
            Reservation.date <= today
        )
    ).count()
    
    # Recent active orders for the live queue (filter out future event pre-orders)
    live_orders = Order.query.outerjoin(Reservation).filter(
        Order.status.in_(['PENDING', 'PREPARING', 'READY']),
        db.or_(
            Order.reservation_id.is_(None),
            Reservation.date <= today
        )
    ).order_by(Order.created_at.desc()).limit(50).all()
    
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
        'order_code': o.order_code or f'#{o.id}',
        'customer': customer,
        'total_amount': float(o.total_amount or 0),
        'dining_option': o.dining_option or 'DINE_IN',
        'dining_label': dining,
        'status': o.status,
        'payment_status': o.payment_status,
        'table_number': o.table_number,
        'table_status': o.table_status or 'AVAILABLE',
        'created_at': o.created_at.strftime('%I:%M %p') if o.created_at else '',
    }


@cashier_bp.route('/staff/cashier/api/dashboard')
def cashier_api_dashboard():
    """JSON endpoint for real-time cashier dashboard updates."""
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return jsonify({'error': 'Unauthorized'}), 401

    today = get_ph_time().date()
    from models import Reservation
    
    live_orders = (
        Order.query.outerjoin(Reservation)
        .filter(
            Order.is_archived.is_(False),
            Order.status.in_(['PENDING', 'PREPARING', 'READY']),
            db.or_(
                Order.reservation_id.is_(None),
                Reservation.date <= today
            )
        )
        .order_by(Order.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify({
        'success': True,
        'time': get_ph_time().strftime('%I:%M:%S %p'),
        'stats': {
            'active_orders': Order.query.outerjoin(Reservation).filter(
                Order.is_archived.is_(False),
                Order.status.in_(['PENDING', 'PREPARING', 'READY']),
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


@cashier_bp.route('/staff/cashier/api/tables')
def cashier_api_tables():
    """Real-time table availability for staff (tables 1–17)."""
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return jsonify({'error': 'Unauthorized'}), 401

    from models import Reservation
    import datetime as py_datetime
    import re

    # 1. Query occupied tables (only active order statuses should count)
    from models import User as UserModel
    occupied_rows = (
        db.session.query(Order.table_number, Order.id, Order.customer_name, Order.status, UserModel.first_name, UserModel.last_name)
        .outerjoin(UserModel, Order.user_id == UserModel.id)
        .filter(
            Order.table_status == 'OCCUPIED',
            Order.table_number.isnot(None),
            Order.is_archived.is_(False),
            Order.status.in_(['PENDING', 'PREPARING', 'READY', 'COMPLETED'])
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
                for t_num in range(1, 18):
                    reserved_tables[t_num] = {
                        'reservation_id': res.id,
                        'customer': customer_name,
                        'time': res.time.strftime('%I:%M %p'),
                        'duration': res.duration,
                    }
            else:
                nums = [int(n) for n in re.findall(r'\d+', res.table_number)]
                for num in nums:
                    if 1 <= num <= 17:
                        reserved_tables[num] = {
                            'reservation_id': res.id,
                            'customer': customer_name,
                            'time': res.time.strftime('%I:%M %p'),
                            'duration': res.duration,
                        }

    # 3. Construct 1-17 tables availability map
    tables = {}
    occupied_count = 0
    reserved_count = 0
    available_count = 0
    for i in range(1, 18):
        if i in occupied_map:
            tables[i] = {'status': 'OCCUPIED', **occupied_map[i]}
            occupied_count += 1
        elif i in reserved_tables:
            tables[i] = {'status': 'RESERVED', **reserved_tables[i]}
            reserved_count += 1
        else:
            tables[i] = {'status': 'AVAILABLE'}
            available_count += 1

    return jsonify({
        'success': True,
        'time': get_ph_time().strftime('%I:%M:%S %p'),
        'tables': tables,
        'occupied_count': occupied_count,
        'reserved_count': reserved_count,
        'available_count': available_count,
    })


@cashier_bp.route('/staff/cashier/tables/<int:table_num>/release', methods=['POST'])
def cashier_release_table(table_num):
    """Release occupied table by setting occupying order's table_status to AVAILABLE."""
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    try:
        # Fetch ALL orders occupying this table to release them all in one click
        orders = Order.query.filter(
            Order.table_number == table_num,
            Order.table_status == 'OCCUPIED',
            Order.is_archived.is_(False)
        ).all()
        
        if not orders:
            return jsonify({'success': False, 'message': f'Table {table_num} is not currently occupied.'}), 400
            
        for order in orders:
            order.table_status = 'AVAILABLE'
            if order.status in ('READY', 'PREPARING', 'PENDING') and order.payment_status == 'PAID':
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
            'order_code': o.order_code or f'#{o.id}',
            'customer': customer,
            'dining_option': o.dining_option,
            'status': o.status,
            'total_amount': float(o.total_amount or 0),
            'created_at': o.created_at.strftime('%I:%M %p') if o.created_at else '',
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
            
        # Check if table is occupied
        occupied_order = Order.query.filter(
            Order.table_number == table_number,
            Order.table_status == 'OCCUPIED',
            Order.is_archived.is_(False),
            Order.status.in_(['PENDING', 'PREPARING', 'READY', 'COMPLETED'])
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

@cashier_bp.route('/staff/cashier/billing')
def cashier_billing():
    if not current_user.is_authenticated or current_user.role not in CASHIER_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))

    status_filter = request.args.get('status', 'UNPAID')
    page = request.args.get('page', 1, type=int)

    query = Order.query.filter(Order.is_archived.is_(False))
    user_branch = getattr(current_user, 'branch', None)
    if user_branch and user_branch != 'ALL':
        query = query.filter_by(branch=user_branch)
    if status_filter != 'ALL':
        query = query.filter_by(payment_status=status_filter)

    pagination = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=20, error_out=False)

    today = get_ph_time().date()
    # Stats for TODAY (for sales performance)
    today_stats_q = db.session.query(
        Order.payment_status, Order.payment_method,
        db.func.count(Order.id), db.func.sum(Order.total_amount)
    ).filter(db.func.date(Order.created_at) == today, Order.is_archived.is_(False))
    if user_branch and user_branch != 'ALL':
        today_stats_q = today_stats_q.filter(Order.branch == user_branch)
    today_stats = today_stats_q.group_by(Order.payment_status, Order.payment_method).all()

    # Stats for ALL UNPAID (for balance tracking)
    all_unpaid_q = db.session.query(
        db.func.count(Order.id), db.func.sum(Order.total_amount)
    ).filter(Order.payment_status == 'UNPAID', Order.is_archived.is_(False))
    if user_branch and user_branch != 'ALL':
        all_unpaid_q = all_unpaid_q.filter(Order.branch == user_branch)
    all_unpaid_stats = all_unpaid_q.first()

    total_sales_today = 0
    cash_sales = 0
    online_sales = 0

    for ps, pm, cnt, total in today_stats:
        total_val = float(total or 0)
        if ps == 'PAID':
            total_sales_today += total_val
            if pm == 'COUNTER': cash_sales += total_val
            if pm == 'ONLINE': online_sales += total_val

    unpaid_count = int(all_unpaid_stats[0] or 0)
    unpaid_total = float(all_unpaid_stats[1] or 0)

    return render_template('cashier/billing.html',
                           orders=pagination,
                           status_filter=status_filter,
                           total_sales_today=total_sales_today,
                           unpaid_count=unpaid_count,
                           unpaid_total=unpaid_total,
                           cash_sales=cash_sales,
                           online_sales=online_sales)

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
        'items': [{'qty': i.quantity, 'name': i.menu_item.name if i.menu_item else 'Item'} for i in o.items]
    }

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
    pending = Order.query.options(*base_opts).filter(
        Order.status == 'PENDING', Order.reservation_id.is_(None)
    ).order_by(Order.created_at.asc()).all()
    preparing = Order.query.options(*base_opts).filter(
        Order.status == 'PREPARING', Order.reservation_id.is_(None)
    ).order_by(Order.created_at.asc()).all()
    ready = Order.query.options(*base_opts).filter(
        Order.status == 'READY', Order.reservation_id.is_(None)
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

INVENTORY_ROLES = ['INVENTORY_STAFF', 'INVENTORY']

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
def inventory_dashboard():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
        
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
    return jsonify({
        'success': True,
        'count': len(alerts),
        'alerts': alerts,
        'time': get_ph_time().strftime('%I:%M:%S %p'),
    })


@inventory_bp.route('/staff/inventory/recipes')
def inventory_recipes():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
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
def inventory_ingredient_batches():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
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
def inventory_full():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
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
                           ingredients=all_ingredients,
                           categories=categories,
                           suppliers=suppliers,
                           portal_name=f"{current_user.first_name} {current_user.last_name}")

@inventory_bp.route('/staff/inventory/ingredient-setup')
def inventory_ingredient_setup():
    """Dedicated page to assign supplier, category, and code to unsetup ingredients."""
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))

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
def inventory_suppliers():
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
    
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
def inventory_edit_ingredient(ing_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        return redirect(url_for('cashier_portal.staff_login'))
    
    ing = Ingredient.query.get_or_404(ing_id)
    
    name = request.form.get('name', '').strip()
    category = request.form.get('category', 'General')
    reorder_level = request.form.get('reorder_level', 0, type=float)
    stock_qty = request.form.get('stock_qty', type=float)
    supplier_id = request.form.get('supplier_id')
    
    if not name:
        msg = 'Ingredient name is required.'
        if is_ajax:
            return jsonify({'success': False, 'message': msg}), 400
        flash(msg, 'danger')
        return redirect(url_for('inventory_portal.inventory_full'))
        
    ing.name = name
    ing.category = category
    ing.reorder_level = reorder_level
    if stock_qty is not None:
        ing.stock_qty = stock_qty
        
    if supplier_id:
        try:
            ing.supplier_id = int(supplier_id)
        except (ValueError, TypeError):
            ing.supplier_id = None
    else:
        ing.supplier_id = None
    
    db.session.commit()
    msg = f'Changes saved for "{name}".'
    if is_ajax:
        return jsonify({
            'success': True,
            'message': msg,
            'ingredient': {
                'id': ing.id,
                'name': ing.name,
                'category': ing.category,
                'stock_qty': float(ing.stock_qty),
                'reorder_level': float(ing.reorder_level)
            }
        })
    flash(msg, 'success')
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
    if not current_user.is_authenticated or current_user.role not in INVENTORY_ROLES:
        return redirect(url_for('cashier_portal.staff_login'))
        
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

RIDER_ROLES = ['RIDER']

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
