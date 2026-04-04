import json
import os
from datetime import datetime, timedelta

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

def load_site_settings():
    if not os.path.exists(SETTINGS_FILE):
        return DEFAULT_SETTINGS
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Merge with default to ensure all keys exist
            merged = DEFAULT_SETTINGS.copy()
            for key in merged:
                if key in data:
                    merged[key].update(data[key])
            return merged
    except Exception:
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
    from models import MenuItem, MenuItemIngredient, Ingredient
    from decimal import Decimal

    total_amount = Decimal('0.0')
    total_items = 0
    order_status_override = 'PENDING'

    # 1. GLOBAL RULES: Max Quantity per Item
    for item in items_data:
        menu_item_id = item.get('menu_item_id')
        quantity = int(item.get('quantity', 0))
        
        if quantity > 20:
            return False, f"Spam Detection: You can only order a maximum of 20 servings of '{MenuItem.query.get(menu_item_id).name}' per transaction.", None
        
        menu_item = MenuItem.query.get(menu_item_id)
        if not menu_item:
            continue
            
        # 1. GLOBAL RULES: Inventory Check
        recipe = MenuItemIngredient.query.filter_by(menu_item_id=menu_item.id).all()
        for r in recipe:
            ingredient = Ingredient.query.get(r.ingredient_id)
            if ingredient:
                needed = float(r.quantity_needed) * quantity
                if float(ingredient.stock_qty) < needed:
                    return False, f"Insufficient Stock: '{menu_item.name}' is temporarily unavailable due to lack of ingredients ({ingredient.name}).", None

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
            from models import User
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
    sendgrid_api_key = os.environ.get('SENDGRID_API_KEY')
    sender = current_app.config.get('MAIL_DEFAULT_SENDER') or 'ryanbarilla16@gmail.com'
    
    # Try SendGrid first
    if sendgrid_api_key:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail as SGMail
        try:
            sg = SendGridAPIClient(sendgrid_api_key)
            msg = SGMail(
                from_email=sender,
                to_emails=to_email,
                subject=subject,
                html_content=html_content
            )
            sg.send(msg)
            print(f"✅ Email sent via SendGrid to {to_email}")
            return True
        except Exception as e:
            print(f"❌ SendGrid error: {e}")
            # Do NOT return False here, allow fallback to Flask-Mail below
    
    # Fallback to Flask-Mail (e.g. for local dev or if SendGrid fails)
    from flask_mail import Message
    try:
        # Check if mail extension exists before trying to send
        if 'mail' in current_app.extensions:
            mail = current_app.extensions['mail']
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
            print("❌ Flask-Mail extension not found in current_app.extensions.")
    except Exception as e:
        print(f"❌ Flask-Mail error: {e}")
        import traceback
        traceback.print_exc()
        
    return False
