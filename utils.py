import json
import os
import re
from datetime import datetime, timedelta
import time
import threading

def get_ph_time():
    return datetime.utcnow() + timedelta(hours=8)

def safe_elapsed(dt_value):
    """Safely calculate seconds elapsed since dt_value, handling timezone-aware vs naive datetimes."""
    if dt_value is None:
        return 999999  # Treat as very old
    now = get_ph_time()
    # Strip timezone info if present (PostgreSQL may return timezone-aware datetimes)
    if hasattr(dt_value, 'tzinfo') and dt_value.tzinfo is not None:
        dt_value = dt_value.replace(tzinfo=None)
    return (now - dt_value).total_seconds()

def create_notification(user_id, title, message, notif_type='SYSTEM'):
    """Helper to create a notification for any user"""
    from models import db, Notification
    notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=notif_type
    )
    db.session.add(notif)
    db.session.commit()
    return notif

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__dirname__)) if '__dirname__' in locals() else os.path.dirname(__file__), 'site_settings.json')

DEFAULT_SETTINGS = {
    "hero2": {
        "title1": "Premium French Dining",
        "title2": "Drift into Joy",
        "description": "Order your favorite organic blends and freshly baked pastries right to your table, or reserve a spot for your next coffee run.",
        "image_url": "https://images.unsplash.com/photo-1554118811-1e0d58224f24?q=80&w=2047&auto=format&fit=crop"
    },
    "card1": {
        "title": "Signature Yelo Latte",
        "description": "Double espresso with strictly steamed oat milk, real vanilla bean and a rich artisanal caramel drizzle. 🌸",
        "image_url": "https://images.unsplash.com/photo-1497935586351-b67a49e012bf?q=80&w=800&auto=format&fit=crop"
    },
    "card2": {
        "title": "Fresh Bites in Bloom",
        "description": "Enjoy light, vibrant artisan pastries inspired by the sweetness of spring — made to brighten every moment. 🌷",
        "image_url": "https://images.unsplash.com/photo-1509042239860-f550ce710b93?q=80&w=800&auto=format&fit=crop"
    },
    "footer": {
        "facebook_link": "https://facebook.com",
        "instagram_link": "https://instagram.com",
        "twitter_link": "https://twitter.com",
        "youtube_link": "https://youtube.com",
        "address_text": "Le maison yelo Lane",
        "copyright_text": "© 2026 Le maison yelo Lane. All rights reserved."
    }
}

_SITE_SETTINGS_CACHE = {
    "value": None,
    "mtime": None,
    "loaded_at_monotonic": 0.0,
}

def load_site_settings():
    """
    Cached settings loader.
    Avoids re-reading/parsing `site_settings.json` on every request.
    Cache invalidates when the file mtime changes or after a short TTL.
    """
    ttl_seconds = 5
    now_mono = time.monotonic()
    try:
        current_mtime = os.path.getmtime(SETTINGS_FILE) if os.path.exists(SETTINGS_FILE) else None
    except Exception:
        current_mtime = None

    cached = _SITE_SETTINGS_CACHE["value"]
    if (
        cached is not None
        and _SITE_SETTINGS_CACHE["mtime"] == current_mtime
        and (now_mono - _SITE_SETTINGS_CACHE["loaded_at_monotonic"]) < ttl_seconds
    ):
        return cached

    if not os.path.exists(SETTINGS_FILE):
        _SITE_SETTINGS_CACHE["value"] = DEFAULT_SETTINGS
        _SITE_SETTINGS_CACHE["mtime"] = current_mtime
        _SITE_SETTINGS_CACHE["loaded_at_monotonic"] = now_mono
        return DEFAULT_SETTINGS
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Merge with default to ensure all keys exist
            merged = DEFAULT_SETTINGS.copy()
            for key in merged:
                if key in data:
                    merged[key].update(data[key])
            _SITE_SETTINGS_CACHE["value"] = merged
            _SITE_SETTINGS_CACHE["mtime"] = current_mtime
            _SITE_SETTINGS_CACHE["loaded_at_monotonic"] = now_mono
            return merged
    except Exception:
        _SITE_SETTINGS_CACHE["value"] = DEFAULT_SETTINGS
        _SITE_SETTINGS_CACHE["mtime"] = current_mtime
        _SITE_SETTINGS_CACHE["loaded_at_monotonic"] = now_mono
        return DEFAULT_SETTINGS

def save_site_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4)
        return True
    except Exception:
        return False

# --- RBAC Security Decorator ---
from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user

def requires_roles(*allowed_roles):
    """
    Higpitan ang access bitbit ang listahan ng roles.
    Halimbawa: @requires_roles('SUPER_ADMIN', 'CASHIER')
    """
    def wrapper(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("You need to login first.", "warning")
                return redirect(url_for('main.login'))
            
            if current_user.role not in allowed_roles:
                abort(403, description="You do not have permission to view this page.")
                
            return f(*args, **kwargs)
        return wrapped
    return wrapper

def validate_order(items_data, dining_option, payment_method, is_pos=False):
    """
    Business Logic Validation for Orders.
    Returns (is_valid, message, order_status_override)
    """
    from models import MenuItem, MenuItemIngredient, Ingredient, User
    from decimal import Decimal
    from collections import defaultdict

    total_amount = Decimal('0.0')
    total_items = 0
    order_status_override = 'PENDING'

    # ---- Batch-load to avoid N+1 queries (performance hot path) ----
    # items_data: [{menu_item_id, quantity}, ...]
    normalized_items = []
    menu_item_ids = set()
    for item in items_data or []:
        try:
            mid = int(item.get('menu_item_id'))
            qty = int(item.get('quantity', 0))
        except Exception:
            continue
        if mid:
            menu_item_ids.add(mid)
            normalized_items.append({'menu_item_id': mid, 'quantity': qty})

    menu_items_by_id = {}
    if menu_item_ids:
        menu_items = MenuItem.query.filter(MenuItem.id.in_(menu_item_ids)).all()
        menu_items_by_id = {m.id: m for m in menu_items}

    # Recipes (MenuItemIngredient) grouped by menu_item_id
    recipes_by_menu_item_id = defaultdict(list)
    ingredient_ids = set()
    if menu_item_ids:
        recipe_rows = MenuItemIngredient.query.filter(
            MenuItemIngredient.menu_item_id.in_(menu_item_ids)
        ).all()
        for r in recipe_rows:
            recipes_by_menu_item_id[r.menu_item_id].append(r)
            ingredient_ids.add(r.ingredient_id)

    # Ingredients grouped by id
    ingredients_by_id = {}
    if ingredient_ids:
        ingredients = Ingredient.query.filter(Ingredient.id.in_(ingredient_ids)).all()
        ingredients_by_id = {i.id: i for i in ingredients}

    # 1. GLOBAL RULES: Max Quantity per Item
    for item in normalized_items:
        menu_item_id = item.get('menu_item_id')
        quantity = item.get('quantity', 0)
        
        if quantity > 20:
            name = menu_items_by_id.get(menu_item_id).name if menu_items_by_id.get(menu_item_id) else f"Item #{menu_item_id}"
            return False, f"Spam Detection: You can only order a maximum of 20 servings of '{name}' per transaction.", None
        
        # Use batched menu items for speed
        menu_item = menu_items_by_id.get(menu_item_id)
        if not menu_item:
            continue
            
        # 1. GLOBAL RULES: Inventory Check
        for r in recipes_by_menu_item_id.get(menu_item.id, []):
            ingredient = ingredients_by_id.get(r.ingredient_id)
            if ingredient is None:
                continue
            needed = float(r.quantity_needed) * quantity
            if float(ingredient.kitchen_qty or 0) < needed:
                return False, f"Insufficient Stock: '{menu_item.name}' is temporarily unavailable due to lack of ingredients in kitchen ({ingredient.name}).", None

        total_amount += Decimal(str(menu_item.price)) * quantity
        total_items += quantity

    # If it's a Walk-in (Cashier/POS), bypass the remaining limits
    if is_pos:
        return True, "Valid POS order.", 'PENDING'

    # 2. DELIVERY & PICK-UP Rules
    if dining_option in ['DELIVERY', 'TAKE_OUT']:
        if total_amount > 3000 or total_items > 25:
            if payment_method in ['COUNTER', 'COD', 'UNPAID']: # Assuming COUNTER is the offline option for web
                return False, "Bulk Order Protection: Orders exceeding ₱3,000 or 25 items require Online Payment (GCash/Maya) to prevent bogus buyers.", None

    # 3. DINE-IN Rules (QR/Self-Ordering)
    if dining_option == 'DINE_IN':
        if total_amount > 3000 or total_items > 25:
            # Trigger alert to Admin/Cashier
            staff_users = User.query.filter(User.role.in_(['ADMIN', 'CASHIER', 'STAFF'])).all()
            for staff in staff_users:
                create_notification(
                    staff.id, 
                    '⚠️ Large Dine-in Order Detected', 
                    f'Order total: ₱{total_amount:,.2f} ({total_items} items). Requires Staff Verification before kitchen processing.', 
                    'SYSTEM'
                )
            
            # Place on HOLD for staff verification
            order_status_override = 'HOLD'
            return True, "Large order detected. Please wait for staff verification at your table.", 'HOLD'

    return True, "Valid order.", 'PENDING'

def send_email(to_email, subject, html_content):
    import os
    from flask import current_app
    
    try:
        # Prefer RQ queue only when explicitly enabled.
        # This avoids silently queueing emails when no worker is running.
        queue_enabled = (os.environ.get("EMAIL_QUEUE_ENABLED", "").strip().lower() in ("1", "true", "yes", "on"))
        redis_url = (os.environ.get("REDIS_URL") or "").strip()
        if queue_enabled and redis_url:
            try:
                from redis import Redis
                from rq import Queue
                q = Queue(connection=Redis.from_url(redis_url))
                # enqueue a lightweight task; worker will execute
                q.enqueue("utils._send_email_job", to_email, subject, html_content, job_timeout=60)
                return True
            except Exception as e:
                # Fall back to sync send below
                print(f"⚠️ RQ enqueue failed, falling back to direct send: {e}")

        sendgrid_api_key = os.environ.get('SENDGRID_API_KEY')
        sender = current_app.config.get('MAIL_DEFAULT_SENDER') or 'ryanbarilla16@gmail.com'
        
        # Try SendGrid first if API key exists
        if sendgrid_api_key:
            try:
                from sendgrid import SendGridAPIClient
                from sendgrid.helpers.mail import Mail as SGMail
                
                # Handle Flask-Mail tuple format (name, email)
                if isinstance(sender, tuple) and len(sender) == 2:
                    sg_sender = (sender[1], sender[0]) # SendGrid expects (email, name)
                else:
                    sg_sender = sender

                sg = SendGridAPIClient(sendgrid_api_key)
                msg = SGMail(
                    from_email=sg_sender,
                    to_emails=to_email,
                    subject=subject,
                    html_content=html_content
                )
                response = sg.send(msg)
                if response.status_code in (200, 201, 202):
                    print(f"✅ Email sent via SendGrid to {to_email}")
                    return True
                else:
                    print(f"❌ SendGrid error {response.status_code}: {response.body}")
            except Exception as e:
                print(f"❌ SendGrid exception: {str(e)}")
                if hasattr(e, 'body'):
                    print(f"❌ SendGrid error body: {e.body}")
        
        # Fallback to Flask-Mail (e.g. Gmail SMTP)
        try:
            from flask_mail import Message
            mail = current_app.extensions.get('mail')
            if mail:
                msg = Message(
                    subject=subject,
                    sender=sender,
                    recipients=[to_email]
                )
                msg.html = html_content
                mail.send(msg)
                print(f"✅ Email sent via Flask-Mail fallback to {to_email}")
                return True
            else:
                print("❌ Flask-Mail extension not found.")
        except Exception as e:
            print(f"❌ Flask-Mail error: {str(e)}")
            
    except Exception as e:
        print(f"❌ Critical error in send_email: {str(e)}")
        
    return False

def _send_email_job(to_email, subject, html_content):
    """
    RQ worker job: run inside a worker process.
    Uses Flask app context if available, else sends via SendGrid only.
    """
    # Attempt to import Flask app for context.
    try:
        from app import app as flask_app
        with flask_app.app_context():
            return send_email_direct(to_email, subject, html_content)
    except Exception:
        return send_email_direct(to_email, subject, html_content)

def send_email_direct(to_email, subject, html_content):
    """Direct send used by queue worker (no re-enqueue)."""
    import os
    try:
        sendgrid_api_key = os.environ.get('SENDGRID_API_KEY')
        sender = os.environ.get('MAIL_DEFAULT_SENDER') or os.environ.get('MAIL_USERNAME') or 'ryanbarilla16@gmail.com'

        if sendgrid_api_key:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail as SGMail
            sg = SendGridAPIClient(sendgrid_api_key)
            msg = SGMail(from_email=sender, to_emails=to_email, subject=subject, html_content=html_content)
            sg.send(msg)
            return True

        # Fallback to Flask-Mail if available (requires app context configured externally)
        from flask import current_app
        from flask_mail import Message
        mail = current_app.extensions.get('mail') if current_app else None
        if mail:
            msg = Message(subject=subject, sender=sender, recipients=[to_email])
            msg.html = html_content
            mail.send(msg)
            return True
    except Exception:
        pass
    return False

# --- SHARED VALIDATION HELPERS ---
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

def validate_password(password, confirm):
    if len(password) < 6: return "Password must be at least 6 characters."
    if password.startswith(' ') or password.endswith(' '): return "Password cannot start or end with spaces."
    if '   ' in password: return "Password cannot contain too many consecutive spaces."
    if not re.search(r'[A-Z]', password): return "Password must contain an uppercase letter."
    if not re.search(r'[0-9]', password): return "Password must contain a number."
    if not re.search(r'[^A-Za-z0-9\s]', password): return "Password must contain a special character."
    if password != confirm: return "Passwords do not match."
    return None
