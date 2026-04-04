from flask import Blueprint, jsonify, request, current_app, render_template, url_for
from flask_mail import Message
from models import db, MenuItem, User, Reservation, Order, OrderItem, Review, Notification, ChatMessage, Voucher
from werkzeug.security import generate_password_hash
from datetime import datetime, date, time as dtime
from utils import get_ph_time, safe_elapsed, create_notification
import re
import random
import traceback
import os
import base64
import requests as http_requests
import threading
from flask import current_app

def send_async_email(app, msg):
    """Sends email in a background thread to avoid blocking the API response."""
    with app.app_context():
        try:
            mail = app.extensions.get('mail')
            if mail:
                mail.send(msg)
        except Exception as e:
            print(f"Async Email Error: {e}")
            import traceback
            traceback.print_exc()

api_bp = Blueprint('api', __name__, url_prefix='/api')

# Setup Xendit (direct HTTP - SDK has urllib3 compatibility issues)
XENDIT_SECRET_KEY = os.environ.get('XENDIT_SECRET_KEY')
XENDIT_API_URL = 'https://api.xendit.co/v2/invoices'

# ═══ VALIDATION HELPERS (same as web) ═══
def has_repeated_chars(s, limit=4):
    if not s: return False
    return bool(re.search(r'(.)\1{' + str(limit - 1) + r',}', s))

def has_repeated_words(s):
    words = s.lower().split()
    return len(words) != len(set(words))

def validate_name(name, field_name):
    if not name: return None
    if len(name) > 50: return f"{field_name} must be 50 characters or less."
    if not re.match(r'^[A-Za-z\s\-]+$', name): return f"{field_name} can only contain letters, spaces, and dashes."
    if has_repeated_chars(name, 5): return f"{field_name} contains too many repeated characters."
    if has_repeated_words(name): return f"{field_name} cannot contain repeated words."
    return None

def validate_email(email):
    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    if not re.match(pattern, email): return "Please enter a valid email address."
    return None

def validate_username(username, first, last):
    if not (5 <= len(username) <= 20): return "Username must be 5-20 characters."
    if not re.match(r'^[A-Za-z0-9_]+$', username): return "Username can only contain letters, numbers, and underscores."
    if has_repeated_chars(username, 5): return "Username contains too many repeated characters."
    if username.lower() == first.lower() or username.lower() == last.lower():
        return "Username cannot be identical to your first or last name."
    return None

def calculate_age(born):
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

def validate_password(password, confirm):
    if len(password) < 6: return "Password must be at least 6 characters."
    if password.startswith(' ') or password.endswith(' '): return "Password cannot start or end with spaces."
    if '   ' in password: return "Password cannot contain too many consecutive spaces."
    if not re.search(r'[A-Z]', password): return "Password must contain an uppercase letter."
    if not re.search(r'[0-9]', password): return "Password must contain a number."
    if not re.search(r'[^A-Za-z0-9\s]', password): return "Password must contain a special character."
    if password != confirm: return "Passwords do not match."
    return None

def check_reservation_time(t):
    if not (dtime(11, 30) <= t <= dtime(20, 30)):
        return False
    if t.minute not in (0, 30):
        return False
    return True

# ═══ MENU API ═══
@api_bp.route('/menu', methods=['GET'])
def get_menu():
    """
    Get all available menu items
    ---
    responses:
      200:
        description: A list of menu items
        schema:
          type: array
          items:
            properties:
              id: {type: integer}
              name: {type: string}
              price: {type: number}
              category: {type: string}
              image_url: {type: string}
    """
    try:
        items = MenuItem.query.filter_by(is_available=True).all()
        menu_list = []
        for item in items:
            menu_list.append({
                'id': item.id,
                'name': item.name,
                'description': item.description,
                'price': float(item.price),
                'category': item.category,
                'image_url': item.image_url
            })
        return jsonify(menu_list), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/menu/categories', methods=['GET'])
def get_categories():
    """
    Get all menu categories
    ---
    responses:
      200:
        description: List of categories with item counts
    """
    try:
        from sqlalchemy import func
        cats = db.session.query(
            MenuItem.category,
            func.count(MenuItem.id).label('count'),
            func.min(MenuItem.image_url).label('sample_image')
        ).filter(MenuItem.is_available == True).group_by(MenuItem.category).all()
        
        result = [{'category': c.category, 'count': c.count, 'sample_image': c.sample_image} for c in cats]
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/menu/bestsellers', methods=['GET'])
def get_bestsellers():
    try:
        items = MenuItem.query.filter_by(is_available=True, category='Best Sellers').all()
        result = [{'id': i.id, 'name': i.name, 'description': i.description, 'price': float(i.price), 'category': i.category, 'image_url': i.image_url} for i in items]
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/menu/featured', methods=['GET'])
def get_featured():
    try:
        from sqlalchemy import func
        items = MenuItem.query.filter_by(is_available=True).order_by(func.random()).limit(6).all()
        result = [{'id': i.id, 'name': i.name, 'description': i.description, 'price': float(i.price), 'category': i.category, 'image_url': i.image_url} for i in items]
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ═══ AUTH API ═══
@api_bp.route('/auth/signup', methods=['POST'])
def api_signup():
    """
    Register a new customer account
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            first_name: {type: string}
            last_name: {type: string}
            username: {type: string}
            email: {type: string}
            phone_number: {type: string}
            birthday: {type: string, example: "1990-01-01"}
            password: {type: string}
            confirm_password: {type: string}
    responses:
      201:
        description: User created, OTP sent
      400:
        description: Validation error
    """
    data = request.json
    if not data:
        return jsonify({'success': False, 'message': 'No data provided.'}), 400

    first_name = (data.get('first_name') or '').strip()
    middle_name = (data.get('middle_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip()
    phone_number = (data.get('phone_number') or '').strip()
    birthday_str = data.get('birthday', '')
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    if not all([first_name, last_name, username, email, phone_number, birthday_str, password, confirm_password]):
        return jsonify({'success': False, 'message': 'All required fields must be filled.'}), 400

    for name, label in [(first_name, 'First Name'), (last_name, 'Last Name')]:
        err = validate_name(name, label)
        if err: return jsonify({'success': False, 'message': err}), 400
    if middle_name:
        err = validate_name(middle_name, 'Middle Name')
        if err: return jsonify({'success': False, 'message': err}), 400

    err = validate_email(email)
    if err: return jsonify({'success': False, 'message': err}), 400

    err = validate_username(username, first_name, last_name)
    if err: return jsonify({'success': False, 'message': err}), 400

    full_identity = f"{first_name} {last_name}".lower()
    if username.lower() == full_identity:
        return jsonify({'success': False, 'message': 'Username cannot be identical to Full Name.'}), 400

    try:
        birthday = datetime.strptime(birthday_str, '%Y-%m-%d').date()
        age = calculate_age(birthday)
        if age < 18:
            return jsonify({'success': False, 'message': 'You must be at least 18 years old to register.'}), 400
        if age > 70:
            return jsonify({'success': False, 'message': 'Maximum age is 70 years.'}), 400
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid birthday format.'}), 400

    err = validate_password(password, confirm_password)
    if err: return jsonify({'success': False, 'message': err}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'message': 'Email already registered.'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'Username already taken.'}), 400
    if User.query.filter_by(first_name=first_name, last_name=last_name).first():
        return jsonify({'success': False, 'message': 'User with this First and Last name already exists.'}), 400

    new_user = User(
        first_name=first_name, middle_name=middle_name, last_name=last_name,
        username=username, email=email, phone_number=phone_number, birthday=birthday, status='PENDING'
    )
    new_user.set_password(password)

    otp = f"{random.randint(100000, 999999)}"
    new_user.otp_code = otp
    new_user.otp_created_at = get_ph_time()
    new_user.is_verified = False

    db.session.add(new_user)
    db.session.commit()

    print(f"--- OTP FOR {email} IS: {otp} ---")

    # Send OTP via Gmail
    try:
        msg = Message(
            subject='Le Maison Yelo Lane - Your OTP Verification Code',
            sender=current_app.config.get('MAIL_DEFAULT_SENDER') or 'ryanbarilla16@gmail.com',
            recipients=[email]
        )
        msg.html = f"""
        <div style="font-family: 'Georgia', serif; max-width: 500px; margin: 0 auto; padding: 40px 30px; background: #ffffff; border-radius: 12px; border: 1px solid #e0d5c7;">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #8B4513; margin: 0; font-size: 1.5rem;">Le Maison Yelo Lane</h1>
                <p style="color: #999; font-size: 0.85rem; margin-top: 5px;">Email Verification</p>
            </div>
            <p style="color: #333;">Hello <strong>{first_name}</strong>,</p>
            <p style="color: #555;">Please use the following OTP code to verify your email:</p>
            <div style="text-align: center; margin: 30px 0;">
                <span style="display: inline-block; background: linear-gradient(135deg, #8B4513, #A0522D); color: #fff; font-size: 2rem; font-weight: bold; letter-spacing: 8px; padding: 15px 35px; border-radius: 10px;">{otp}</span>
            </div>
            <p style="color: #999; font-size: 0.8rem; text-align: center;">This code will expire in 5 minutes.</p>
        </div>
        """
        app = current_app._get_current_object()
        threading.Thread(target=send_async_email, args=(app, msg)).start()
    except Exception as e:
        print(f"Email queuing failed: {e}")
        traceback.print_exc()

    return jsonify({'success': True, 'user_id': new_user.id, 'message': f'OTP sent to {email}.'}), 201

@api_bp.route('/auth/verify_otp', methods=['POST'])
def api_verify_otp():
    data = request.json
    user_id = data.get('user_id')
    otp_input = (data.get('otp') or '').strip()
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404
    
    if user.otp_code == otp_input:
        user.is_verified = True
        user.otp_code = None
        db.session.commit()
        return jsonify({'success': True, 'message': 'Account verified! Please wait for admin approval.'}), 200
    
    return jsonify({'success': False, 'message': 'Invalid OTP.'}), 400

@api_bp.route('/auth/resend_otp', methods=['POST'])
def api_resend_otp():
    data = request.json
    user_id = data.get('user_id')
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404
    
    if user.is_verified:
        return jsonify({'success': False, 'message': 'Account already verified.'}), 400
    
    if user.otp_created_at:
        elapsed = safe_elapsed(user.otp_created_at)
        if elapsed < 300:
            remaining = int(300 - elapsed)
            return jsonify({'success': False, 'message': f'Please wait {remaining // 60}m {remaining % 60}s before requesting a new code.'}), 429
    
    otp = f"{random.randint(100000, 999999)}"
    user.otp_code = otp
    user.otp_created_at = get_ph_time()
    db.session.commit()
    
    print(f"--- RESEND OTP FOR {user.email} IS: {otp} ---")
    
    try:
        msg = Message(
            subject='Le Maison Yelo Lane - Your New OTP Code',
            sender=current_app.config.get('MAIL_DEFAULT_SENDER') or 'ryanbarilla16@gmail.com',
            recipients=[user.email]
        )
        msg.html = f"""
        <div style="font-family: 'Georgia', serif; max-width: 500px; margin: 0 auto; padding: 40px 30px; background: #ffffff; border-radius: 12px; border: 1px solid #e0d5c7;">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #8B4513; margin: 0; font-size: 1.5rem;">Le Maison Yelo Lane</h1>
            </div>
            <p style="color: #333;">Hello <strong>{user.first_name}</strong>,</p>
            <p style="color: #555;">Here is your new OTP verification code:</p>
            <div style="text-align: center; margin: 30px 0;">
                <span style="display: inline-block; background: linear-gradient(135deg, #8B4513, #A0522D); color: #fff; font-size: 2rem; font-weight: bold; letter-spacing: 8px; padding: 15px 35px; border-radius: 10px;">{otp}</span>
            </div>
        </div>
        """
        app = current_app._get_current_object()
        threading.Thread(target=send_async_email, args=(app, msg)).start()
    except Exception as e:
        print(f"Email queuing failed: {e}")
    
    return jsonify({'success': True, 'message': f'New OTP sent to {user.email}.'}), 200

@api_bp.route('/auth/login', methods=['POST'])
def api_login():
    data = request.json
    email = data.get('email', '')
    password = data.get('password', '')
    
    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({'success': False, 'message': 'Invalid email or password.'}), 401
    
    if not user.is_verified:
        return jsonify({'success': False, 'message': 'Please complete your OTP verification first.', 'needs_otp': True, 'user_id': user.id}), 403
    
    if user.status != 'ACTIVE' and user.role not in ['ADMIN', 'CASHIER', 'INVENTORY_STAFF']:
        return jsonify({'success': False, 'message': 'Your account is pending admin approval.'}), 403
    
    if user.role in ['ADMIN', 'CASHIER', 'INVENTORY_STAFF']:
        return jsonify({'success': False, 'message': 'Staff/Admin accounts cannot login via the mobile app.'}), 403
    
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'first_name': user.first_name,
            'middle_name': user.middle_name,
            'last_name': user.last_name,
            'username': user.username,
            'email': user.email,
            'phone_number': user.phone_number,
            'profile_picture_url': user.profile_picture_url,
            'role': user.role,
        }
    }), 200

# ═══ SOCIAL AUTH API (Mobile) ═══
@api_bp.route('/auth/social', methods=['POST'])
def api_social_auth():
    import secrets
    data = request.json
    if not data:
        return jsonify({'success': False, 'message': 'No data provided.'}), 400

    email = data.get('email')
    first_name = data.get('first_name', '')
    last_name = data.get('last_name', '')
    provider = data.get('provider', '')
    picture_url = data.get('picture_url')

    if not email:
        return jsonify({'success': False, 'message': 'Email is required from social provider.'}), 400

    user = User.query.filter_by(email=email).first()

    if user:
        # Update profile picture if missing
        if picture_url and not user.profile_picture_url:
            user.profile_picture_url = picture_url
            db.session.commit()

        # Block staff/admin from mobile login
        if user.role in ['ADMIN', 'CASHIER', 'INVENTORY_STAFF']:
            return jsonify({'success': False, 'message': 'Staff/Admin accounts cannot login via the mobile app.'}), 403

        if user.status != 'ACTIVE':
            return jsonify({'success': False, 'message': f'Your {provider} login was successful, but your account is pending admin approval.'}), 403

        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'first_name': user.first_name,
                'middle_name': user.middle_name,
                'last_name': user.last_name,
                'username': user.username,
                'email': user.email,
                'phone_number': user.phone_number,
                'profile_picture_url': user.profile_picture_url,
            }
        }), 200

    # Auto-create user since they used social login
    base_username = (first_name + last_name).lower().replace(' ', '')
    if len(base_username) < 5:
        base_username = base_username + 'user'
    username = f"{base_username}{secrets.randbelow(9999)}"

    while User.query.filter_by(username=username).first():
        username = f"{base_username}{secrets.randbelow(99999)}"

    random_password = secrets.token_urlsafe(16)

    new_user = User(
        first_name=first_name,
        last_name=last_name,
        username=username,
        email=email,
        status=status_override or 'PENDING',
        is_verified=True,
        profile_picture_url=picture_url
    )
    new_user.set_password(random_password)

    db.session.add(new_user)
    db.session.commit()

    return jsonify({
        'success': False,
        'message': f'Welcome {first_name}! Your account was created via {provider} but requires admin approval before you can log in.'
    }), 201

# --- MOBILE SOCIAL LOGIN POLLING ---
mobile_sessions = {}

@api_bp.route('/auth/social/complete', methods=['POST'])
def api_social_complete():
    import secrets
    data = request.json
    session_id = data.get('session_id')
    if not session_id:
        return jsonify({'success': False, 'message': 'No session ID'}), 400

    email = data.get('email')
    first_name = data.get('first_name', '')
    last_name = data.get('last_name', '')
    provider = data.get('provider', '')
    picture_url = data.get('picture_url')

    if not email:
        mobile_sessions[session_id] = {'success': False, 'status': 'failed', 'message': 'Email required.'}
        return jsonify({'success': False})

    user = User.query.filter_by(email=email).first()

    if user:
        if picture_url and not user.profile_picture_url:
            user.profile_picture_url = picture_url
            db.session.commit()

        if user.role in ['ADMIN', 'CASHIER', 'INVENTORY_STAFF']:
            mobile_sessions[session_id] = {'success': False, 'status': 'failed', 'message': 'Staff/Admin cannot login via mobile.'}
            return jsonify({'success': True})

        if user.status != 'ACTIVE':
            mobile_sessions[session_id] = {'success': False, 'status': 'failed', 'message': f'Your {provider} login was successful, but account is pending approval.'}
            return jsonify({'success': True})

        mobile_sessions[session_id] = {
            'success': True,
            'user': {
                'id': user.id,
                'first_name': user.first_name,
                'middle_name': user.middle_name,
                'last_name': user.last_name,
                'username': user.username,
                'email': user.email,
                'phone_number': user.phone_number,
                'profile_picture_url': user.profile_picture_url,
            }
        }
        return jsonify({'success': True})

    # Auto-create user
    base_username = (first_name + last_name).lower().replace(' ', '')
    if len(base_username) < 5:
        base_username += 'user'
    username = f"{base_username}{secrets.randbelow(9999)}"
    while User.query.filter_by(username=username).first():
        username = f"{base_username}{secrets.randbelow(99999)}"

    new_user = User(
        first_name=first_name,
        last_name=last_name,
        username=username,
        email=email,
        status=status_override or 'PENDING',
        is_verified=True,
        profile_picture_url=picture_url
    )
    new_user.set_password(secrets.token_urlsafe(16))
    db.session.add(new_user)
    db.session.commit()

    mobile_sessions[session_id] = {
        'success': False,
        'status': 'failed', 
        'message': f'Welcome {first_name}! Account created via {provider} but requires admin approval.'
    }
    return jsonify({'success': True})

@api_bp.route('/auth/social/poll', methods=['GET'])
def api_social_poll():
    session_id = request.args.get('session_id')
    if session_id in mobile_sessions:
        return jsonify(mobile_sessions.pop(session_id)), 200
    return jsonify({'success': False, 'status': 'pending'}), 200


# ═══ USER DASHBOARD API ═══
@api_bp.route('/user/<int:user_id>/dashboard', methods=['GET'])
def api_user_dashboard(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    today = date.today()
    upcoming = Reservation.query.filter(
        Reservation.user_id == user_id,
        Reservation.date >= today,
        Reservation.status.in_(['PENDING', 'CONFIRMED'])
    ).order_by(Reservation.date.asc(), Reservation.time.asc()).limit(3).all()
    
    total_visits = Reservation.query.filter(
        Reservation.user_id == user_id,
        Reservation.status == 'COMPLETED'
    ).count()
    
    recent_orders = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).limit(3).all()
    
    return jsonify({
        'upcoming_reservations': [{
            'id': r.id, 'date': r.date.strftime('%b %d, %Y'), 'time': r.time.strftime('%I:%M %p'),
            'guest_count': r.guest_count, 'occasion': r.occasion, 'booking_type': r.booking_type, 'status': r.status
        } for r in upcoming],
        'total_visits': total_visits,
        'loyalty_status': 'Gold' if total_visits >= 10 else 'Silver' if total_visits >= 5 else 'Bronze' if total_visits >= 1 else 'New',
        'recent_orders': [{
            'id': o.id, 'total_amount': float(o.total_amount), 'status': o.status,
            'created_at': o.created_at.strftime('%b %d, %Y'), 'item_count': len(o.items),
            'first_item': o.items[0].menu_item.name if o.items else ''
        } for o in recent_orders]
    }), 200

# ═══ ORDERS API ═══
@api_bp.route('/user/<int:user_id>/orders', methods=['GET'])
def api_user_orders(user_id):
    orders = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).all()
    
    user_reviews = Review.query.filter_by(user_id=user_id).all()
    reviews_by_order = {r.order_id: r.rating for r in user_reviews if r.order_id}
    
    result = []
    for o in orders:
        result.append({
            'id': o.id,
            'total_amount': float(o.total_amount),
            'status': o.status,
            'payment_status': o.payment_status,
            'dining_option': o.dining_option,
            'payment_method': o.payment_method,
            'delivery_address': o.delivery_address,
            'delivery_status': o.delivery_status,
            'notes': o.notes,
            'created_at': o.created_at.strftime('%b %d, %Y - %I:%M %p'),
            'items': [{'name': item.menu_item.name, 'quantity': item.quantity, 'price': float(item.price_at_time), 'image_url': item.menu_item.image_url, 'category': item.menu_item.category} for item in o.items],
            'review_rating': reviews_by_order.get(o.id)
        })
    
    pending_count = sum(1 for o in orders if o.status == 'PENDING')
    preparing_count = sum(1 for o in orders if o.status == 'PREPARING')
    completed_count = sum(1 for o in orders if o.status == 'COMPLETED')
    
    return jsonify({
        'orders': result,
        'pending_count': pending_count,
        'preparing_count': preparing_count,
        'completed_count': completed_count
    }), 200

@api_bp.route('/order/checkout', methods=['POST'])
def api_checkout():
    data = request.json
    user_id = data.get('user_id')
    cart_items = data.get('items', [])  # [{menu_item_id, quantity}]
    notes = data.get('notes', '')
    dining_option = data.get('dining_option', 'DINE_IN')
    payment_method = data.get('payment_method', 'COUNTER')
    
    if not user_id or not cart_items:
        return jsonify({'success': False, 'message': 'Cart is empty.'}), 400

    # --- ORDER VALIDATION LOGIC ---
    from utils import validate_order
    is_valid, msg, status_override = validate_order(cart_items, dining_option, payment_method, is_pos=False)

    if not is_valid:
        return jsonify({'success': False, 'message': msg}), 400
    # ------------------------------
    
    total = 0
    order_items = []
    for ci in cart_items:
        menu_item = MenuItem.query.get(ci['menu_item_id'])
        if menu_item and menu_item.is_available:
            price = float(menu_item.price)
            subtotal = price * ci['quantity']
            total += subtotal
            order_items.append(OrderItem(
                menu_item_id=menu_item.id,
                quantity=ci['quantity'],
                price_at_time=price
            ))
    
    if not order_items:
        return jsonify({'success': False, 'message': 'Items in cart are no longer available.'}), 400
    
    new_order = Order(
        user_id=user_id,
        total_amount=total,
        status=status_override or 'PENDING',
        dining_option=dining_option,
        payment_method=payment_method,
        notes=notes
    )
    if dining_option == 'DELIVERY':
        new_order.delivery_address = data.get('delivery_address', '')
        new_order.delivery_status = 'WAITING'

    db.session.add(new_order)
    db.session.flush()
    
    for oi in order_items:
        oi.order_id = new_order.id
        db.session.add(oi)
    
    db.session.commit()
    
    # ═══ HANDLE ONLINE PAYMENT (XENDIT) ═══
    invoice_url = None
    if payment_method == 'GCASH' and XENDIT_SECRET_KEY:
        try:
            # Build auth header
            auth_str = base64.b64encode(f'{XENDIT_SECRET_KEY}:'.encode()).decode()
            
            # Build invoice items
            inv_items = [
                {
                    'name': item.menu_item.name,
                    'quantity': int(item.quantity),
                    'price': float(item.price_at_time)
                } for item in order_items
            ]
            
            # Create Xendit Invoice via REST API
            xendit_resp = http_requests.post(
                XENDIT_API_URL,
                headers={
                    'Authorization': f'Basic {auth_str}',
                    'Content-Type': 'application/json'
                },
                json={
                    'external_id': f'order_{new_order.id}',
                    'amount': float(total),
                    'payer_email': User.query.get(user_id).email,
                    'description': f'Order #{new_order.id} - Le Maison Yelo Lane',
                    'invoice_duration': 86400,
                    'currency': 'PHP',
                    'items': inv_items
                },
                timeout=15
            )
            
            if xendit_resp.status_code == 200:
                inv_data = xendit_resp.json()
                new_order.xendit_invoice_id = inv_data.get('id')
                new_order.xendit_invoice_url = inv_data.get('invoice_url')
                new_order.payment_method = 'ONLINE'
                db.session.commit()
                invoice_url = inv_data.get('invoice_url')
            else:
                print(f'Xendit Error {xendit_resp.status_code}: {xendit_resp.text}')
                return jsonify({
                    'success': True,
                    'message': 'Order placed, but payment generation failed. Please pay at the counter.',
                    'order_id': new_order.id,
                    'payment_failed': True
                }), 201
            
        except Exception as e:
            print(f'Xendit Error: {e}')
            traceback.print_exc()
            return jsonify({
                'success': True, 
                'message': 'Order placed, but payment generation failed. Please pay at the counter.', 
                'order_id': new_order.id,
                'payment_failed': True
            }), 201

    # Send notification to user
    _create_notification(user_id, 'Order Placed', f'Your order #{new_order.id} has been placed successfully! Total: ₱{total:.2f}', 'ORDER')
    
    # Real-time update for Admin/Kitchen
    from extensions import socketio
    socketio.emit('new_order', {
        'id': new_order.id, 
        'customer': f"{User.query.get(user_id).first_name} {User.query.get(user_id).last_name}",
        'dining_option': dining_option,
        'total_amount': float(total)
    }, namespace='/')
    
    return jsonify({
        'success': True, 
        'message': 'Order placed successfully!', 
        'order_id': new_order.id,
        'invoice_url': invoice_url
    }), 201

# ═══ XENDIT WEBHOOK (payment callback) ═══
@api_bp.route('/xendit/callback', methods=['POST'])
def xendit_callback():
    """Handles Xendit invoice payment status updates."""
    data = request.json
    if not data:
        return jsonify({'success': False}), 400
    
    external_id = data.get('external_id', '')
    status = data.get('status', '')
    
    # Extract order ID from external_id (format: "order_123")
    if not external_id.startswith('order_'):
        return jsonify({'success': False, 'message': 'Invalid external_id'}), 400
    
    try:
        order_id = int(external_id.replace('order_', ''))
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid order ID'}), 400
    
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'success': False, 'message': 'Order not found'}), 404
    
    if status == 'PAID':
        order.payment_status = 'PAID'
        db.session.commit()
        _create_notification(order.user_id, 'Payment Received', f'Your GCash payment for order #{order.id} has been confirmed! ₱{float(order.total_amount):.2f}', 'ORDER')
    elif status == 'EXPIRED':
        order.payment_status = 'UNPAID'
        order.notes = (order.notes or '') + ' [Payment expired]'
        db.session.commit()
        _create_notification(order.user_id, 'Payment Expired', f'Your payment for order #{order.id} has expired. Please pay at the counter or place a new order.', 'ORDER')
    
    return jsonify({'success': True}), 200

@api_bp.route('/order/<int:order_id>/review', methods=['POST'])
def api_add_review(order_id):
    data = request.json
    user_id = data.get('user_id')
    rating = data.get('rating')
    comment = (data.get('comment') or '').strip()
    
    order = Order.query.get(order_id)
    if not order or order.user_id != user_id:
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
    if order.status != 'COMPLETED':
        return jsonify({'success': False, 'message': 'You can only review completed orders.'}), 400
    
    existing = Review.query.filter_by(order_id=order_id).first()
    if existing:
        return jsonify({'success': False, 'message': 'Already reviewed.'}), 400
    
    if not rating or rating < 1 or rating > 5:
        return jsonify({'success': False, 'message': 'Rating must be 1-5.'}), 400
    
    new_review = Review(user_id=user_id, order_id=order_id, rating=rating, comment=comment, status='PENDING')
    db.session.add(new_review)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Review submitted!'}), 201

# ═══ RESERVATIONS API ═══
@api_bp.route('/reserve', methods=['POST'])
def api_reserve():
    data = request.json
    user_id = data.get('user_id')
    res_date_str = data.get('date')
    res_time_str = data.get('time')
    guest_count_str = data.get('guest_count')
    occasion = data.get('occasion', '')
    booking_type = data.get('booking_type', 'REGULAR')
    duration_str = data.get('duration', '2')
    
    try:
        res_date = datetime.strptime(res_date_str, '%Y-%m-%d').date()
        hour, minute = map(int, res_time_str.split(':'))
        res_time = dtime(hour, minute)
        guest_count = int(guest_count_str)
        duration = int(duration_str)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid data format.'}), 400
    
    today = date.today()
    diff = (res_date - today).days
    
    if booking_type == 'EXCLUSIVE':
        if diff < 1:
            return jsonify({'success': False, 'message': 'Exclusive reservations must be made at least 1 day in advance.'}), 400
    else:
        if diff < 0:
            return jsonify({'success': False, 'message': 'Cannot book in the past.'}), 400
        if diff == 0:
            from datetime import datetime as dt
            curr_t = dt.now().time()
            if res_time <= curr_t:
                return jsonify({'success': False, 'message': 'You cannot book a time slot that has already passed today.'}), 400
    
    if diff > 60:
        return jsonify({'success': False, 'message': 'Reservation can be max 2 months (60 days) in advance.'}), 400
    
    if not check_reservation_time(res_time):
        return jsonify({'success': False, 'message': 'Time must be between 11:30 AM - 8:30 PM with 30-minute intervals.'}), 400
    
    if guest_count <= 0:
        return jsonify({'success': False, 'message': 'Guest count must be at least 1.'}), 400
    
    if booking_type == 'EXCLUSIVE':
        if guest_count > 50:
            return jsonify({'success': False, 'message': 'Exclusive Venue can hold up to 50 guests maximum.'}), 400
    else:
        if guest_count > 20:
            return jsonify({'success': False, 'message': 'Regular tables max at 20 guests.'}), 400
    
    active_res = Reservation.query.filter(
        Reservation.date == res_date,
        Reservation.status.in_(['PENDING', 'CONFIRMED'])
    ).all()
    
    from datetime import timedelta
    current_res_start = datetime.combine(res_date, res_time)
    current_res_end = current_res_start + timedelta(hours=duration)
    
    conflict = False
    conflict_msg = ""
    for r in active_res:
        r_start = datetime.combine(r.date, r.time)
        r_dur = r.duration if r.duration is not None else 2
        r_end = r_start + timedelta(hours=r_dur)
        if current_res_start < r_end and r_start < current_res_end:
            if booking_type == 'EXCLUSIVE' or r.booking_type == 'EXCLUSIVE':
                conflict = True
                conflict_msg = "Conflicting exclusive booking or overlapping reservation."
                break
                
    if conflict:
        return jsonify({'success': False, 'message': conflict_msg}), 400
        
    if booking_type != 'EXCLUSIVE':
        overlapping_guests = 0
        for r in active_res:
            if r.booking_type != 'EXCLUSIVE':
                r_start = datetime.combine(r.date, r.time)
                r_dur = r.duration if r.duration is not None else 2
                r_end = r_start + timedelta(hours=r_dur)
                if current_res_start < r_end and r_start < current_res_end:
                    overlapping_guests += r.guest_count
        
        if overlapping_guests + guest_count > 50:
            return jsonify({'success': False, 'message': 'Time slot is fully booked. Not enough seats.'}), 400
    
    new_res = Reservation(
        user_id=user_id,
        date=res_date,
        time=res_time,
        duration=duration,
        guest_count=guest_count,
        occasion=occasion,
        booking_type=booking_type
    )
    db.session.add(new_res)
    db.session.commit()
    
    # Send notification to user
    _create_notification(user_id, 'Reservation Submitted', f'Your reservation for {res_date.strftime("%b %d, %Y")} at {res_time.strftime("%I:%M %p")} has been submitted. Pending approval.', 'RESERVATION')
    
    return jsonify({'success': True, 'message': 'Reservation submitted! Pending admin approval.'}), 201

@api_bp.route('/user/<int:user_id>/reservations', methods=['GET'])
def api_user_reservations(user_id):
    today = date.today()
    upcoming = Reservation.query.filter(
        Reservation.user_id == user_id,
        Reservation.date >= today,
        Reservation.status.in_(['PENDING', 'CONFIRMED'])
    ).order_by(Reservation.date.asc(), Reservation.time.asc()).all()
    
    past = Reservation.query.filter(
        Reservation.user_id == user_id,
        Reservation.status.in_(['COMPLETED', 'REJECTED'])
    ).order_by(Reservation.created_at.desc()).limit(10).all()
    
    return jsonify({
        'upcoming': [{
            'id': r.id, 'date': r.date.strftime('%Y-%m-%d'), 'date_formatted': r.date.strftime('%b %d, %Y'),
            'time': r.time.strftime('%H:%M'), 'time_formatted': r.time.strftime('%I:%M %p'),
            'guest_count': r.guest_count, 'occasion': r.occasion, 'booking_type': r.booking_type, 'status': r.status
        } for r in upcoming],
        'past': [{
            'id': r.id, 'date_formatted': r.date.strftime('%b %d, %Y'),
            'time_formatted': r.time.strftime('%I:%M %p'),
            'guest_count': r.guest_count, 'occasion': r.occasion, 'status': r.status
        } for r in past]
    }), 200

# ═══ PROFILE API ═══
@api_bp.route('/user/<int:user_id>/profile', methods=['GET'])
def api_get_profile(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({
        'id': user.id,
        'first_name': user.first_name,
        'middle_name': user.middle_name,
        'last_name': user.last_name,
        'username': user.username,
        'email': user.email,
        'phone_number': user.phone_number,
        'profile_picture_url': user.profile_picture_url,
        'birthday': user.birthday.strftime('%Y-%m-%d') if user.birthday else None,
    }), 200

@api_bp.route('/user/<int:user_id>/profile', methods=['PUT'])
def api_update_profile(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.json
    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip()
    phone_number = (data.get('phone_number') or '').strip()
    
    if not all([first_name, last_name, username, email, phone_number]):
        return jsonify({'success': False, 'message': 'All fields are required.'}), 400
    
    if email != user.email and User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'message': 'Email already registered.'}), 400
    if username != user.username and User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'Username already taken.'}), 400
    
    user.first_name = first_name
    user.last_name = last_name
    user.username = username
    user.email = email
    user.phone_number = phone_number
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Profile updated!'}), 200

# ═══ FORGOT PASSWORD API ═══
@api_bp.route('/auth/forgot-password', methods=['POST'])
def api_forgot_password():
    """Step 1: Send OTP to user's email for password reset"""
    data = request.json
    email = (data.get('email') or '').strip()
    
    if not email:
        return jsonify({'success': False, 'message': 'Email is required.'}), 400
    
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'success': False, 'message': 'No account found with this email.'}), 404
    
    # Rate-limit OTP (wait 60 seconds between requests)
    if user.otp_created_at:
        elapsed = safe_elapsed(user.otp_created_at)
        if elapsed < 60:
            remaining = int(60 - elapsed)
            return jsonify({'success': False, 'message': f'Please wait {remaining}s before requesting a new code.'}), 429
    
    otp = f"{random.randint(100000, 999999)}"
    user.otp_code = otp
    user.otp_created_at = get_ph_time()
    db.session.commit()
    
    print(f"--- FORGOT PASSWORD OTP FOR {email} IS: {otp} ---")
    
    # Send OTP via Gmail
    try:
        mail = current_app.extensions['mail']
        msg = Message(
            subject='Le Maison Yelo Lane - Password Reset Code',
            sender=current_app.config.get('MAIL_DEFAULT_SENDER') or 'ryanbarilla16@gmail.com',
            recipients=[email]
        )
        msg.html = f"""
        <div style="font-family: 'Georgia', serif; max-width: 500px; margin: 0 auto; padding: 40px 30px; background: #ffffff; border-radius: 12px; border: 1px solid #e0d5c7;">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #8B4513; margin: 0; font-size: 1.5rem;">Le Maison Yelo Lane</h1>
                <p style="color: #999; font-size: 0.85rem; margin-top: 5px;">Password Reset</p>
            </div>
            <p style="color: #333;">Hello <strong>{user.first_name}</strong>,</p>
            <p style="color: #555;">You requested a password reset. Use the following OTP code to reset your password:</p>
            <div style="text-align: center; margin: 30px 0;">
                <span style="display: inline-block; background: linear-gradient(135deg, #8B4513, #A0522D); color: #fff; font-size: 2rem; font-weight: bold; letter-spacing: 8px; padding: 15px 35px; border-radius: 10px;">{otp}</span>
            </div>
            <p style="color: #999; font-size: 0.8rem; text-align: center;">This code will expire in 5 minutes. If you didn't request this, please ignore this email.</p>
        </div>
        """
        mail.send(msg)
    except Exception as e:
        print(f"Email sending failed: {e}")
        traceback.print_exc()
    
    return jsonify({'success': True, 'user_id': user.id, 'message': f'OTP sent to {email}.'}), 200

@api_bp.route('/auth/forgot-password/verify-otp', methods=['POST'])
def api_forgot_password_verify_otp():
    """Step 2: Verify the OTP entered by user"""
    data = request.json
    user_id = data.get('user_id')
    otp_input = (data.get('otp') or '').strip()
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404
    
    # Check OTP expiry (5 minutes)
    if user.otp_created_at:
        elapsed = safe_elapsed(user.otp_created_at)
        if elapsed > 300:
            return jsonify({'success': False, 'message': 'OTP has expired. Please request a new one.'}), 400
    
    if user.otp_code == otp_input:
        return jsonify({'success': True, 'message': 'OTP verified! You can now set a new password.'}), 200
    
    return jsonify({'success': False, 'message': 'Invalid OTP code.'}), 400

@api_bp.route('/auth/forgot-password/reset', methods=['POST'])
def api_forgot_password_reset():
    """Step 3: Set the new password (after OTP is verified)"""
    data = request.json
    user_id = data.get('user_id')
    otp_input = (data.get('otp') or '').strip()
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404
    
    # Re-verify OTP for security
    if user.otp_code != otp_input:
        return jsonify({'success': False, 'message': 'Invalid OTP. Please start over.'}), 400
        
    # Check OTP expiry (5 minutes)
    if user.otp_created_at:
        elapsed = safe_elapsed(user.otp_created_at)
        if elapsed > 300:
            return jsonify({'success': False, 'message': 'OTP has expired. Please start over.'}), 400
    
    # Validate new password
    err = validate_password(new_password, confirm_password)
    if err:
        return jsonify({'success': False, 'message': err}), 400
    
    user.set_password(new_password)
    user.otp_code = None
    user.otp_created_at = None
    db.session.commit()
    
    # Send notification
    _create_notification(user.id, 'Password Changed', 'Your password was successfully changed.', 'SYSTEM')
    
    return jsonify({'success': True, 'message': 'Password reset successfully! You can now log in with your new password.'}), 200

# ═══ NOTIFICATIONS API ═══
def _create_notification(user_id, title, message, notif_type='SYSTEM'):
    """Helper to create a notification (uses centralized helper)"""
    return create_notification(user_id, title, message, notif_type)

@api_bp.route('/user/<int:user_id>/notifications', methods=['GET'])
def api_get_notifications(user_id):
    """Get all notifications for a user"""
    from models import Notification
    notifications = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(50).all()
    return jsonify({
        'success': True,
        'notifications': [{
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'type': n.type,
            'is_read': n.is_read,
            'created_at': n.created_at.strftime('%b %d, %Y - %I:%M %p') if n.created_at else '',
        } for n in notifications]
    }), 200

@api_bp.route('/user/<int:user_id>/notifications/unread-count', methods=['GET'])
def api_unread_notification_count(user_id):
    """Get count of unread notifications"""
    from models import Notification
    count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    return jsonify({'success': True, 'count': count}), 200

@api_bp.route('/notification/<int:notif_id>/read', methods=['POST'])
def api_mark_notification_read(notif_id):
    """Mark a single notification as read"""
    from models import Notification
    notif = Notification.query.get(notif_id)
    if not notif:
        return jsonify({'success': False, 'message': 'Notification not found.'}), 404
    notif.is_read = True
    db.session.commit()
    return jsonify({'success': True}), 200

@api_bp.route('/user/<int:user_id>/notifications/read-all', methods=['POST'])
def api_mark_all_notifications_read(user_id):
    """Mark all notifications as read for a user"""
    from models import Notification
    Notification.query.filter_by(user_id=user_id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True, 'message': 'All notifications marked as read.'}), 200

@api_bp.route('/notifications/mark-read', methods=['POST'])
def api_mark_notifications_read():
    try:
        user_id = request.json.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': 'User ID required'}), 400
            
        Notification.query.filter_by(user_id=user_id, is_read=False).update({'is_read': True})
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# ═══ CHAT SUPPORT API ═══
@api_bp.route('/chat/<int:user_id>', methods=['GET'])
def api_get_chat_messages(user_id):
    """
    Get all chat messages for a specific user
    """
    try:
        messages = ChatMessage.query.filter_by(user_id=user_id).order_by(ChatMessage.created_at.asc()).all()
        return jsonify({
            'success': True,
            'messages': [{
                'id': msg.id,
                'sender': msg.sender,
                'message': msg.message,
                'is_read': msg.is_read,
                'created_at': msg.created_at.strftime("%Y-%m-%d %H:%M:%S") if msg.created_at else None
            } for msg in messages]
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/chat/<int:user_id>/send', methods=['POST'])
def api_send_chat_message(user_id):
    """
    Send a new chat message
    """
    try:
        data = request.json
        if not data or not data.get('message') or not data.get('sender'):
            return jsonify({'success': False, 'message': 'Message and sender are required'}), 400
            
        message = data.get('message').strip()
        sender = data.get('sender').upper()
        
        if sender not in ['USER', 'ADMIN']:
            return jsonify({'success': False, 'message': 'Invalid sender type'}), 400
            
        new_msg = ChatMessage(
            user_id=user_id,
            sender=sender,
            message=message,
            is_read=False
        )
        db.session.add(new_msg)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Message sent successfully',
            'data': {
                'id': new_msg.id,
                'sender': new_msg.sender,
                'message': new_msg.message,
                'created_at': new_msg.created_at.strftime("%Y-%m-%d %H:%M:%S") if new_msg.created_at else None
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# ═══ PROFILE PICTURE UPLOAD API ═══
@api_bp.route('/user/<int:user_id>/profile-picture', methods=['POST'])
def api_upload_profile_picture(user_id):
    """Upload profile picture as base64"""
    import base64
    import uuid
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404
    
    data = request.json
    image_data = data.get('image')  # base64 string
    
    if not image_data:
        return jsonify({'success': False, 'message': 'No image data provided.'}), 400
    
    try:
        # Remove data URI prefix if present
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        
        # Decode base64
        img_bytes = base64.b64decode(image_data)
        
        # Create uploads directory
        import os
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'profiles')
        os.makedirs(upload_dir, exist_ok=True)
        
        # Delete old profile picture file if exists
        if user.profile_picture_url and '/static/uploads/profiles/' in user.profile_picture_url:
            old_filename = user.profile_picture_url.split('/')[-1]
            old_path = os.path.join(upload_dir, old_filename)
            if os.path.exists(old_path):
                os.remove(old_path)
        
        # Save new file
        filename = f"profile_{user_id}_{uuid.uuid4().hex[:8]}.jpg"
        filepath = os.path.join(upload_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(img_bytes)
        
        # Update user record with relative URL
        user.profile_picture_url = f"/static/uploads/profiles/{filename}"
        db.session.commit()
        
        # Build full URL for the app
        base_url = request.host_url.rstrip('/')
        full_url = f"{base_url}/static/uploads/profiles/{filename}"
        
        return jsonify({
            'success': True,
            'message': 'Profile picture updated!',
            'profile_picture_url': full_url
        }), 200
    except Exception as e:
        print(f"Profile picture upload error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Failed to upload image.'}), 500

# ═══ RIDER API ENDPOINTS ═══
@api_bp.route('/rider/deliveries', methods=['GET'])
def rider_get_deliveries():
    """Get all DELIVERY orders for rider dashboard"""
    rider_id = request.args.get('rider_id', type=int)
    
    # Available = DELIVERY dining + no rider assigned yet (or WAITING)
    # Show PENDING, PREPARING, and COMPLETED orders so rider sees them immediately
    available = Order.query.filter(
        Order.dining_option == 'DELIVERY',
        Order.status.in_(['PENDING', 'PREPARING', 'COMPLETED']),
        (Order.rider_id == None) | (Order.delivery_status == 'WAITING')
    ).order_by(Order.created_at.desc()).all()
    
    # My active deliveries
    my_active = []
    if rider_id:
        my_active = Order.query.filter(
            Order.rider_id == rider_id,
            Order.delivery_status.in_(['PICKED_UP', 'ON_THE_WAY'])
        ).order_by(Order.created_at.desc()).all()
    
    # My completed deliveries (all history)
    my_completed = []
    if rider_id:
        my_completed = Order.query.filter(
            Order.rider_id == rider_id,
            Order.delivery_status == 'DELIVERED'
        ).order_by(Order.created_at.desc()).all()
    
    def order_to_dict(o):
        return {
            'id': o.id,
            'customer_name': f"{o.user.first_name} {o.user.last_name}" if o.user else (o.customer_name or 'Walk-in'),
            'customer_phone': o.user.phone_number if o.user else None,
            'delivery_address': o.delivery_address or 'No address provided',
            'total_amount': float(o.total_amount),
            'payment_method': o.payment_method,
            'payment_status': o.payment_status,
            'delivery_status': o.delivery_status or 'WAITING',
            'kitchen_status': o.status,  # PENDING, PREPARING, COMPLETED - for rider to know kitchen progress
            'status': o.status,
            'created_at': o.created_at.isoformat(),
            'items': [{
                'name': item.menu_item.name,
                'quantity': item.quantity,
                'price': float(item.price_at_time),
            } for item in o.items],
            'rider_id': o.rider_id,
        }
    
    return jsonify({
        'success': True,
        'available': [order_to_dict(o) for o in available],
        'active': [order_to_dict(o) for o in my_active],
        'completed': [order_to_dict(o) for o in my_completed],
    })

@api_bp.route('/rider/accept/<int:order_id>', methods=['POST'])
def rider_accept_delivery(order_id):
    """Rider accepts/reserves a delivery order - stays WAITING until kitchen completes"""
    data = request.json or {}
    rider_id = data.get('rider_id')
    if not rider_id:
        return jsonify({'success': False, 'message': 'Rider ID required.'}), 400
    
    order = Order.query.get_or_404(order_id)
    if order.status != 'COMPLETED':
        return jsonify({'success': False, 'message': 'Cannot accept yet! Kitchen is still preparing this order.'}), 400
        
    if order.rider_id and order.delivery_status not in [None, 'WAITING']:
        return jsonify({'success': False, 'message': 'Order already taken by another rider.'}), 400
    
    order.rider_id = rider_id
    # Stay as WAITING - rider reserves the order but cannot pick up until kitchen is done
    order.delivery_status = 'WAITING'
    db.session.commit()
    return jsonify({'success': True, 'message': f'Order #{order_id} reserved! Wait for kitchen to finish preparing.'})

@api_bp.route('/rider/update/<int:order_id>', methods=['POST'])
def rider_update_delivery(order_id):
    """Rider updates delivery status with strict workflow enforcement"""
    data = request.json or {}
    new_status = data.get('delivery_status')
    rider_id = data.get('rider_id')
    
    if new_status not in ['PICKED_UP', 'ON_THE_WAY', 'DELIVERED']:
        return jsonify({'success': False, 'message': 'Invalid delivery status.'}), 400
    
    order = Order.query.get_or_404(order_id)
    if order.rider_id != rider_id:
        return jsonify({'success': False, 'message': 'This order is not assigned to you.'}), 403
    
    # === STRICT WORKFLOW ENFORCEMENT ===
    # PICKED_UP: Only allowed if Kitchen has marked order as COMPLETED
    if new_status == 'PICKED_UP':
        if order.status != 'COMPLETED':
            return jsonify({
                'success': False, 
                'message': 'Cannot pick up yet! Kitchen is still preparing this order. Please wait for kitchen to finish.'
            }), 400
        if order.delivery_status not in [None, 'WAITING']:
            return jsonify({'success': False, 'message': 'Invalid status transition.'}), 400
    
    # ON_THE_WAY: Only allowed if currently PICKED_UP
    if new_status == 'ON_THE_WAY':
        if order.delivery_status != 'PICKED_UP':
            return jsonify({'success': False, 'message': 'You must pick up the order first before going on the way.'}), 400
    
    # DELIVERED: Only allowed if currently ON_THE_WAY
    if new_status == 'DELIVERED':
        if order.delivery_status != 'ON_THE_WAY':
            return jsonify({'success': False, 'message': 'You must be on the way before marking as delivered.'}), 400
    
    order.delivery_status = new_status
    
    # Handle Proof of Delivery (Photo)
    proof_url = data.get('proof_of_delivery_url')
    if proof_url:
        order.proof_of_delivery_url = proof_url

    # If DELIVERED, credit rider commission to wallet
    if new_status == 'DELIVERED':
        rider = User.query.get(rider_id)
        if rider:
            # Commission calculation: Flat 20 PHP + 50% of delivery fee
            delivery_fee_val = float(order.delivery_fee or 0)
            commission = 20.0 + (delivery_fee_val * 0.5)
            
            if not rider.wallet_balance:
                rider.wallet_balance = 0.0
            rider.wallet_balance = float(rider.wallet_balance) + commission
            
            # Log the commission earned.
            order.notes = (order.notes or '') + f" [Rider Commission: ₱{commission:.2f}]"

    # If COD and delivered, handle amount tendered
    if new_status == 'DELIVERED' and order.payment_method == 'COUNTER':
        amount_tendered = data.get('amount_tendered')
        if amount_tendered:
            order.amount_tendered = float(amount_tendered)
            order.change_amount = float(amount_tendered) - float(order.total_amount)
            order.payment_status = 'PAID'
    
    db.session.commit()
    return jsonify({'success': True, 'message': f'Delivery status updated to {new_status}!'})

@api_bp.route('/rider/summary/<int:rider_id>', methods=['GET'])
def rider_summary(rider_id):
    from datetime import date
    total_deliveries = Order.query.filter(
        Order.rider_id == rider_id,
        Order.delivery_status == 'DELIVERED'
    ).count()
    
    active_deliveries = Order.query.filter(
        Order.rider_id == rider_id,
        Order.delivery_status.in_(['PICKED_UP', 'ON_THE_WAY'])
    ).count()
    
    # Today's deliveries
    today = date.today()
    today_deliveries = Order.query.filter(
        Order.rider_id == rider_id,
        Order.delivery_status == 'DELIVERED',
        db.func.date(Order.created_at) == today
    ).count()
    
    # Wallet balance
    rider = User.query.get(rider_id)
    wallet_balance = float(rider.wallet_balance or 0) if rider else 0.0
    
    # Today's earnings estimate (commission: ₱20 + 50% delivery fee per delivery)
    today_orders = Order.query.filter(
        Order.rider_id == rider_id,
        Order.delivery_status == 'DELIVERED',
        db.func.date(Order.created_at) == today
    ).all()
    today_earnings = sum(20.0 + (float(o.delivery_fee or 0) * 0.5) for o in today_orders)
    
    return jsonify({
        'success': True,
        'total_deliveries_today': total_deliveries,
        'active_deliveries': active_deliveries,
        'today_deliveries': today_deliveries,
        'today_earnings': round(today_earnings, 2),
        'wallet_balance': round(wallet_balance, 2),
    })

# ═══ RIDER LOCATION TRACKING ═══
# In-memory store for rider locations (no DB migration needed)
_rider_locations = {}  # {rider_id: {lat, lng, timestamp, rider_name, order_ids}}

@api_bp.route('/rider/location', methods=['POST'])
def rider_update_location():
    """Rider sends their current GPS coordinates"""
    data = request.json or {}
    rider_id = data.get('rider_id')
    lat = data.get('latitude')
    lng = data.get('longitude')
    
    if not rider_id or lat is None or lng is None:
        return jsonify({'success': False, 'message': 'Missing rider_id, latitude, or longitude.'}), 400
    
    rider = User.query.get(rider_id)
    rider_name = f"{rider.first_name} {rider.last_name}" if rider else 'Unknown'
    
    # Get active order IDs for this rider
    active_orders = Order.query.filter(
        Order.rider_id == rider_id,
        Order.delivery_status.in_(['WAITING', 'PICKED_UP', 'ON_THE_WAY'])
    ).all()
    order_ids = [o.id for o in active_orders]
    
    _rider_locations[rider_id] = {
        'lat': float(lat),
        'lng': float(lng),
        'timestamp': get_ph_time().isoformat(),
        'rider_name': rider_name,
        'rider_id': rider_id,
        'order_ids': order_ids,
    }
    
    return jsonify({'success': True, 'message': 'Location updated.'})

@api_bp.route('/rider/locations', methods=['GET'])
def get_all_rider_locations():
    """Admin: Get all active rider locations for the map"""
    # Clean up stale locations (older than 2 minutes)
    now = get_ph_time()
    stale_ids = []
    for rid, loc in _rider_locations.items():
        try:
            ts = datetime.fromisoformat(loc['timestamp'])
            if (now - ts).total_seconds() > 120:
                stale_ids.append(rid)
        except Exception:
            stale_ids.append(rid)
    for rid in stale_ids:
        del _rider_locations[rid]
    
    return jsonify({
        'success': True,
        'riders': list(_rider_locations.values())
    })

@api_bp.route('/delivery/track/<int:order_id>', methods=['GET'])
def track_delivery(order_id):
    """Customer: Track a specific delivery order on the map"""
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'success': False, 'message': 'Order not found.'}), 404
    
    if order.dining_option != 'DELIVERY':
        return jsonify({'success': False, 'message': 'Not a delivery order.'}), 400
    
    rider_location = None
    if order.rider_id and order.rider_id in _rider_locations:
        loc = _rider_locations[order.rider_id]
        rider_location = {
            'lat': loc['lat'],
            'lng': loc['lng'],
            'rider_name': loc['rider_name'],
            'timestamp': loc['timestamp'],
        }
    
    rider_name = None
    if order.rider:
        rider_name = f"{order.rider.first_name} {order.rider.last_name}"
    
    return jsonify({
        'success': True,
        'order_id': order.id,
        'delivery_status': order.delivery_status or 'WAITING',
        'delivery_address': order.delivery_address,
        'rider_name': rider_name,
        'rider_location': rider_location,
    })

# ═══ ORDER CHAT API ═══
@api_bp.route('/order/<int:order_id>/chat', methods=['GET'])
def get_order_chat(order_id):
    """Fetch chat history for a specific order (between rider and customer)"""
    from models import OrderChat, Order
    
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'success': False, 'message': 'Order not found.'}), 404
    
    messages = OrderChat.query.filter_by(order_id=order_id).order_by(OrderChat.created_at.asc()).all()
    
    message_list = [{
        'id': msg.id,
        'sender_id': msg.sender_id,
        'sender_role': msg.sender.role,
        'message': msg.message,
        'is_read': msg.is_read,
        'created_at': msg.created_at.isoformat(),
        'sender_name': f"{msg.sender.first_name} {msg.sender.last_name}"
    } for msg in messages]
    
    return jsonify({
        'success': True,
        'messages': message_list
    })

@api_bp.route('/order/<int:order_id>/chat/send', methods=['POST'])
def send_order_chat(order_id):
    """Send a message in the order chat"""
    from models import OrderChat, Order, Notification
    
    data = request.json
    sender_id = data.get('sender_id')
    message_text = data.get('message', '').strip()
    
    if not sender_id or not message_text:
        return jsonify({'success': False, 'message': 'Missing data'}), 400
        
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'success': False, 'message': 'Order not found.'}), 404
        
    chat = OrderChat(
        order_id=order_id,
        sender_id=sender_id,
        message=message_text
    )
    db.session.add(chat)
    
    # Send a notification to the other party
    if sender_id == order.user_id:
        # Customer sent it -> notify rider
        if order.rider_id:
            notif = Notification(
                user_id=order.rider_id,
                title=f"New message from Customer (Order #{order.id})",
                message=message_text,
                type="DELIVERY"
            )
            db.session.add(notif)
    elif sender_id == order.rider_id:
        # Rider sent it -> notify customer
        notif = Notification(
            user_id=order.user_id,
            title=f"New message from Rider (Order #{order.id})",
            message=message_text,
            type="DELIVERY"
        )
        db.session.add(notif)
        
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Message sent successfully.'
    })

@api_bp.route('/user/<int:user_id>', methods=['DELETE'])
def api_delete_user(user_id):
    """Delete a user account permanently"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404
    
    try:
        # User deletion will cascade if relationships are set correctly in models.py
        # Otherwise, we might need to handle related records
        db.session.delete(user)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Account deleted successfully.'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error deleting account: {str(e)}'}), 500

# ═══ VOUCHER VALIDATION API ═══
@api_bp.route('/voucher/apply', methods=['POST'])
def api_apply_voucher():
    """Validate and apply a voucher code"""
    try:
        data = request.json
        code = data.get('code', '').strip().upper()
        order_total = data.get('order_total', 0)
        
        if not code:
            return jsonify({'success': False, 'message': 'Please enter a voucher code'}), 400
            
        voucher = Voucher.query.filter_by(code=code).first()
        if not voucher:
            return jsonify({'success': False, 'message': 'Invalid voucher code'}), 404
            
        if not voucher.is_active:
            return jsonify({'success': False, 'message': 'This voucher is no longer active'}), 400
            
        if voucher.times_used >= voucher.max_uses:
            return jsonify({'success': False, 'message': 'This voucher has reached its usage limit'}), 400
            
        now = get_ph_time()
        if voucher.valid_from and now < voucher.valid_from:
            return jsonify({'success': False, 'message': 'This voucher is not yet valid'}), 400
        if voucher.valid_until and now > voucher.valid_until:
            return jsonify({'success': False, 'message': 'This voucher has expired'}), 400
            
        if float(order_total) < float(voucher.min_order_amount):
            return jsonify({'success': False, 'message': f'Minimum order of ₱{voucher.min_order_amount} required'}), 400
        
        # Calculate discount
        if voucher.discount_type == 'PERCENT':
            discount = float(order_total) * float(voucher.discount_value) / 100
        else:
            discount = float(voucher.discount_value)
            
        discount = min(discount, float(order_total))  # Never exceed order total
        
        return jsonify({
            'success': True,
            'message': f'Voucher {code} applied!',
            'discount': round(discount, 2),
            'discount_type': voucher.discount_type,
            'discount_value': float(voucher.discount_value),
            'voucher_id': voucher.id
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
