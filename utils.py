import json
import os
from datetime import datetime, timedelta

def get_ph_time():
    return datetime.utcnow() + timedelta(hours=8)

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
