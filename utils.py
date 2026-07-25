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

def create_notification(user_id, title, message, notif_type='SYSTEM', link=None):
    """Helper to create a notification for any user"""
    from models import db, Notification
    notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=notif_type,
        link=link
    )
    db.session.add(notif)
    db.session.commit()
    return notif

def generate_menu_item_code(category):
    """
    Generate unique menu item code based on category.
    Format: CATEGORY-NUMBER (e.g., PASTA-001, PIZZA-001)
    
    Args:
        category: Menu item category (e.g., "Pasta & Salads", "Hand-Tossed Pizza")
    
    Returns:
        str: Unique code like "PASTA-001"
    """
    from models import MenuItem, db
    
    # Clean and shorten category name for code
    # Remove special characters, take first word or abbreviation
    category_clean = category.upper().replace('&', '').replace('-', '').strip()
    
    # Extract meaningful part (first significant word)
    words = category_clean.split()
    if len(words) > 0:
        # Take first word, limit to 8 characters
        category_code = words[0][:8]
    else:
        category_code = "ITEM"
    
    # Get the last item code in this category
    last_item = MenuItem.query.filter(
        MenuItem.item_code.like(f'{category_code}-%')
    ).order_by(MenuItem.item_code.desc()).first()
    
    # Generate next number
    if last_item and last_item.item_code:
        try:
            # Extract number from code (e.g., PASTA-001 → 001)
            last_num = int(last_item.item_code.split('-')[-1])
            next_num = last_num + 1
        except (ValueError, IndexError):
            next_num = 1
    else:
        next_num = 1
    
    # Format: PASTA-001
    return f"{category_code}-{next_num:03d}"

# Ingredient category → short code prefix mapping
_INGREDIENT_CATEGORY_MAP = {
    'meat':    'MEAT',
    'protein': 'MEAT',
    'poultry': 'MEAT',
    'produce': 'VEG',
    'vegetable': 'VEG',
    'vegetables': 'VEG',
    'fruit': 'VEG',
    'dairy': 'DAIRY',
    'milk': 'DAIRY',
    'cheese': 'DAIRY',
    'spice': 'SPICE',
    'spices': 'SPICE',
    'herb': 'SPICE',
    'herbs': 'SPICE',
    'seasoning': 'SPICE',
    'bakery': 'BAKE',
    'baked': 'BAKE',
    'bread': 'BAKE',
    'pastry': 'BAKE',
    'beverage': 'BEV',
    'beverages': 'BEV',
    'drink': 'BEV',
    'drinks': 'BEV',
    'grains': 'GRAIN',
    'grain': 'GRAIN',
    'rice': 'GRAIN',
    'noodles': 'GRAIN',
    'pantry': 'PANTRY',
    'condiment': 'PANTRY',
    'sauce': 'SAUCE',
    'sauces': 'SAUCE',
    'seafood': 'SEAF',
    'fish': 'SEAF',
}

def generate_ingredient_code(category):
    """
    Generate a unique ingredient code based on its category.
    Format: PREFIX-NUMBER (e.g., MEAT-001, VEG-001, DAIRY-001)

    Category to Prefix mapping:
        Meat / Protein  → MEAT
        Produce / Veg   → VEG
        Dairy           → DAIRY
        Spice / Herbs   → SPICE
        Bakery          → BAKE
        Beverage        → BEV
        Grains          → GRAIN
        Pantry          → PANTRY
        Sauces          → SAUCE
        Seafood         → SEAF
        Everything else → GEN (up to 6 chars from category name)

    Args:
        category: Ingredient category name (e.g., "Meat", "Dairy", "Pantry")

    Returns:
        str: Unique code like "MEAT-001"
    """
    from models import Ingredient, db

    if category:
        cat_lower = category.lower().strip()
        prefix = _INGREDIENT_CATEGORY_MAP.get(cat_lower)
        if not prefix:
            # Take first 6 chars of cleaned category name
            cat_clean = ''.join(c for c in category.upper() if c.isalpha())
            prefix = cat_clean[:6] if cat_clean else 'GEN'
    else:
        prefix = 'GEN'

    # Get the last ingredient code with this prefix
    last_ing = Ingredient.query.filter(
        Ingredient.ingredient_code.like(f'{prefix}-%')
    ).order_by(Ingredient.ingredient_code.desc()).first()

    if last_ing and last_ing.ingredient_code:
        try:
            last_num = int(last_ing.ingredient_code.split('-')[-1])
            next_num = last_num + 1
        except (ValueError, IndexError):
            next_num = 1
    else:
        next_num = 1

    return f"{prefix}-{next_num:03d}"

def generate_order_code():
    """
    Generate unique order code based on date and sequence.
    Format: ORD-YYYYMMDD-SEQUENCE (e.g., ORD-20240526-001)
    
    Returns:
        str: Unique code like "ORD-20240526-001"
    """
    from models import Order, db
    from datetime import date
    
    # Get today's date in YYYYMMDD format
    today = date.today()
    date_str = today.strftime('%Y%m%d')
    
    # Get the last order code for today
    prefix = f'ORD-{date_str}-'
    last_order = Order.query.filter(
        Order.order_code.like(f'{prefix}%')
    ).order_by(Order.order_code.desc()).first()
    
    # Generate next sequence number
    if last_order and last_order.order_code:
        try:
            # Extract sequence number (e.g., ORD-20240526-001 → 001)
            last_seq = int(last_order.order_code.split('-')[-1])
            next_seq = last_seq + 1
        except (ValueError, IndexError):
            next_seq = 1
    else:
        next_seq = 1
    
    # Format: ORD-20240526-001
    return f"ORD-{date_str}-{next_seq:03d}"

def generate_reservation_code():
    """
    Generate unique reservation code based on date and sequence.
    Format: YYYYMMDD-SEQUENCE (e.g., 20240526-001)
    
    Returns:
        str: Unique code like "20240526-001"
    """
    from models import Reservation, db
    from datetime import date
    
    # Get today's date in YYYYMMDD format
    today = date.today()
    date_str = today.strftime('%Y%m%d')
    
    # Get the last reservation code for today
    prefix = f'{date_str}-'
    last_reservation = Reservation.query.filter(
        Reservation.reservation_code.like(f'{prefix}%')
    ).order_by(Reservation.reservation_code.desc()).first()
    
    # Generate next sequence number
    if last_reservation and last_reservation.reservation_code:
        try:
            # Extract sequence number (e.g., 20240526-001 → 001)
            last_seq = int(last_reservation.reservation_code.split('-')[-1])
            next_seq = last_seq + 1
        except (ValueError, IndexError):
            next_seq = 1
    else:
        next_seq = 1
    
    # Format: 20240526-001
    return f"{date_str}-{next_seq:03d}"

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__dirname__)) if '__dirname__' in locals() else os.path.dirname(__file__), 'site_settings.json')

DEFAULT_SETTINGS = {
    "hero1": {
        "title1": "Experience Premium",
        "title2": "French Dining",
        "description": "Indulge in our beautifully presented, gourmet French-inspired dishes crafted with culinary passion.",
        "image_url": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?q=70&w=1500&auto=format&fit=crop"
    },
    "hero2": {
        "title1": "Bold Sizzling",
        "title2": "Rustic Steaks",
        "description": "Savor the rich flavors of premium, flame-grilled cuts served hot on our signature wooden carving boards.",
        "image_url": "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?q=70&w=1500&auto=format&fit=crop"
    },
    "hero3": {
        "title1": "Crispy & Loaded",
        "title2": "Comfort Bites",
        "description": "Share the joy with our golden hand-cut fries, stacked nachos, and savory snack spreads made for great company.",
        "image_url": "https://i.postimg.cc/cCRnWV9j/htdhtht.webp"
    },
    "welcome": {
        "title": "Le Maison de Yelo Lane",
        "subtitle": "Welcome to",
        "description1": "From humble beginnings on Yelo Lane to becoming Pagsanjan's beloved dining destination, every dish we serve carries a story of passion, tradition, and French-inspired artistry.",
        "description2": "Whether it's a romantic dinner, a family celebration, or a casual coffee date — we've prepared the perfect ambiance just for you.",
        "image_url": "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?q=75&w=900&auto=format&fit=crop"
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

def validate_order(items_data, dining_option, payment_method, is_pos=False, apply_lock=False):
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
                
            # --- SCOUT #1 FIX: Race Condition Lock & Real-time Pending Calculation ---
            # 1. Lock the ingredient row to prevent simultaneous identical checks (The "Safety Lock")
            if apply_lock:
                from sqlalchemy.orm import object_session
                session = object_session(ingredient)
                if session:
                    session.refresh(ingredient, with_for_update=True)
            
            # 2. Calculate how much of this ingredient is already "reserved" by PENDING orders
            from models import Order, OrderItem, MenuItemIngredient, db
            pending_usage = db.session.query(db.func.sum(OrderItem.quantity * MenuItemIngredient.quantity_needed))\
                .join(Order, Order.id == OrderItem.order_id)\
                .join(MenuItemIngredient, MenuItemIngredient.menu_item_id == OrderItem.menu_item_id)\
                .filter(Order.status.in_(['PENDING', 'HOLD']))\
                .filter(MenuItemIngredient.ingredient_id == ingredient.id)\
                .scalar()
            
            pending_usage = float(pending_usage or 0)
            real_available = float(ingredient.kitchen_qty or 0) - pending_usage
            needed = float(r.quantity_needed) * quantity
            
            # 3. Check if the "Real Available" stock is enough
            if real_available < needed:
                return False, f"Insufficient Stock: We cannot fulfill '{menu_item.name}'. Another customer is currently reserving the last available stock.", None

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

        mail_user = os.environ.get('MAIL_USERNAME')
        mail_pass = os.environ.get('MAIL_PASSWORD')
        sendgrid_api_key = os.environ.get('SENDGRID_API_KEY')
        resend_api_key = os.environ.get('RESEND_API_KEY')
        sender = current_app.config.get('MAIL_DEFAULT_SENDER') or 'ryanbarilla16@gmail.com'
        # Get plain sender email string for APIs that need it
        sender_email = sender[1] if isinstance(sender, tuple) else sender
        sender_name = sender[0] if isinstance(sender, tuple) else 'Le Maison Yelo Lane'

        # 1. Try Resend API FIRST (uses HTTPS - works on Render free tier, not blocked like SMTP)
        if resend_api_key:
            try:
                import urllib.request
                import json as _json
                payload_data = {
                    "from": "Le Maison Yelo Lane <onboarding@resend.dev>",
                    "to": [to_email],
                    "subject": subject,
                    "html": html_content
                }
                payload = _json.dumps(payload_data).encode('utf-8')
                req = urllib.request.Request(
                    "https://api.resend.com/emails",
                    data=payload,
                    headers={
                        "Authorization": f"Bearer {resend_api_key.strip()}",
                        "Content-Type": "application/json",
                        "User-Agent": "LeMaisonApp/1.0"
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    body = resp.read().decode()
                    print(f"[SUCCESS] Email sent via Resend to {to_email} | status={resp.status} | body={body}")
                    return True
            except urllib.error.HTTPError as http_err:
                err_body = http_err.read().decode() if hasattr(http_err, 'read') else ''
                print(f"[ERROR] Resend API HTTP Error {http_err.code}: {http_err.reason} | details: {err_body}")
            except Exception as e:
                print(f"[ERROR] Resend API exception: {str(e)}")

        # 2. Try Flask-Mail (Gmail SMTP) if credentials exist
        if mail_user and mail_pass:
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
                    print(f"[SUCCESS] Email sent via Gmail SMTP to {to_email}")
                    return True
                else:
                    print("[ERROR] Flask-Mail extension not initialized.")
            except Exception as e:
                print(f"[ERROR] Gmail SMTP exception: {str(e)}")

        # 2. Try SendGrid as fallback if API key exists
        if sendgrid_api_key:
            try:
                from sendgrid import SendGridAPIClient
                from sendgrid.helpers.mail import Mail as SGMail

                if isinstance(sender, tuple) and len(sender) == 2:
                    sg_sender = (sender[1], sender[0])
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
                    print(f"[SUCCESS] Email sent via SendGrid to {to_email}")
                    return True
                else:
                    print(f"[ERROR] SendGrid error {response.status_code}: {response.body}")
            except Exception as e:
                print(f"[ERROR] SendGrid exception: {str(e)}")
                if hasattr(e, 'body'):
                    print(f"[ERROR] SendGrid error body: {e.body}")

    except Exception as e:
        print(f"[ERROR] Critical error in send_email: {str(e)}")

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
        mail_user = os.environ.get('MAIL_USERNAME')
        mail_pass = os.environ.get('MAIL_PASSWORD')
        sendgrid_api_key = os.environ.get('SENDGRID_API_KEY')
        sender = os.environ.get('MAIL_DEFAULT_SENDER') or os.environ.get('MAIL_USERNAME') or 'ryanbarilla16@gmail.com'

        if mail_user and mail_pass:
            from flask import current_app
            from flask_mail import Message
            mail = current_app.extensions.get('mail') if current_app else None
            if mail:
                msg = Message(subject=subject, sender=sender, recipients=[to_email])
                msg.html = html_content
                mail.send(msg)
                return True

        if sendgrid_api_key:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail as SGMail
            sg = SendGridAPIClient(sendgrid_api_key)
            msg = SGMail(from_email=sender, to_emails=to_email, subject=subject, html_content=html_content)
            sg.send(msg)
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

def save_optimized_image(file_source, target_filepath, max_dim=(800, 800), quality=80):
    """
    Optimizes and saves an uploaded image file.
    Resizes image to fit within max_dim while preserving aspect ratio,
    handles EXIF rotation, and saves with JPEG/WebP/PNG compression.

    Args:
        file_source: FileStorage object (from request.files), file path, or bytes
        target_filepath: Absolute file path where the optimized image should be saved
        max_dim: tuple of (max_width, max_height)
        quality: int (1-100) compression quality
    """
    try:
        from PIL import Image, ImageOps
        import io

        if hasattr(file_source, 'read'):
            data = file_source.read()
            if not data:
                return False
            img = Image.open(io.BytesIO(data))
        elif isinstance(file_source, str):
            img = Image.open(file_source)
        elif isinstance(file_source, bytes):
            img = Image.open(io.BytesIO(file_source))
        else:
            img = Image.open(file_source)

        # Correct orientation from EXIF tags
        img = ImageOps.exif_transpose(img)

        target_ext = os.path.splitext(target_filepath)[1].lower()

        # Resize keeping aspect ratio
        img.thumbnail(max_dim, Image.Resampling.LANCZOS)

        os.makedirs(os.path.dirname(target_filepath), exist_ok=True)

        if target_ext in ['.jpg', '.jpeg']:
            if img.mode in ('RGBA', 'P', 'LA'):
                img = img.convert('RGB')
            img.save(target_filepath, 'JPEG', quality=quality, optimize=True)
        elif target_ext == '.webp':
            if img.mode == 'P':
                img = img.convert('RGBA')
            img.save(target_filepath, 'WEBP', quality=quality, optimize=True)
        elif target_ext == '.png':
            img.save(target_filepath, 'PNG', optimize=True)
        else:
            if img.mode in ('RGBA', 'P', 'LA'):
                img = img.convert('RGB')
            img.save(target_filepath, quality=quality, optimize=True)

        return True
    except Exception as e:
        print(f"Error optimizing image: {e}")
        try:
            if hasattr(file_source, 'seek'):
                file_source.seek(0)
            if hasattr(file_source, 'save'):
                file_source.save(target_filepath)
                return True
        except Exception as fallback_err:
            print(f"Fallback save failed: {fallback_err}")
        return False

