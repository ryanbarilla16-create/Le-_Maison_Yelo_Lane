from flask import Flask, session, render_template, request, jsonify
from datetime import timedelta
from config import Config
from models import db, User
from flask_login import LoginManager
from routes import main_bp
import os
from flask_cors import CORS
# from sync import setup_supabase_sync
from flask_mail import Mail
from utils import get_ph_time

from werkzeug.middleware.proxy_fix import ProxyFix
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from extensions import socketio
from flasgger import Swagger
from flask_compress import Compress
import threading
from sqlalchemy import text as sql_text

app = Flask(__name__)
# Initialize extensions
Compress(app)
# Application Optimizations
app.config['COMPRESS_REGISTER'] = True
app.config['COMPRESS_ALGORITHM'] = ['gzip', 'br', 'deflate']
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000 # Cache static resources for 1 year

socketio.init_app(app, async_mode='eventlet')
# Tell Flask it is behind a proxy (like LocalTunnel) so redirects use the correct url
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config.from_object(Config)

# Initialize Security & Documentation
# Talisman(app, content_security_policy=None, force_https=False) # Uncomment in actual production
Swagger(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["5000 per day", "1000 per hour"],
    storage_uri="memory://"
)

# Enable CORS for cross-origin requests from Flutter Web or mobile API
CORS(app, supports_credentials=True, resources={r"/api/*": {"origins": "*"}})

# Equivalent to PHP Session Properties configured
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# Database and Login Manager initialization
db.init_app(app)
migrate = Migrate(app, db) # Handles seamless database upgrades

login_manager = LoginManager()
login_manager.login_view = 'main.login'
login_manager.init_app(app)

# Initialize Flask-Mail
mail = Mail(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Initialize realtime mirroring to Supabase via Event Hooks
# setup_supabase_sync()

# Register blueprints
app.register_blueprint(main_bp)

from routes.admin import admin_bp
app.register_blueprint(admin_bp)

from routes.api import api_bp
app.register_blueprint(api_bp)

from routes.portals import cashier_bp, kitchen_bp, inventory_bp, rider_bp
app.register_blueprint(cashier_bp)
app.register_blueprint(kitchen_bp)
app.register_blueprint(inventory_bp)
app.register_blueprint(rider_bp)

from routes.debug import debug_bp
app.register_blueprint(debug_bp)

# Ensure database tables exist (Crucial for Render production)
with app.app_context():
    try:
        db.create_all()
        print("--- DB INIT: Tables verified/created successfully ---")
    except Exception as e:
        print(f"--- DB INIT ERROR: {e} ---")

def _maybe_create_indexes_background():
    """
    Create DB indexes to speed up frequent filters/joins.
    Runs in a background thread so it won't block app startup.
    """
    # Avoid running on SQLite (indexes unnecessary; and SQL differs).
    try:
        dialect = db.engine.dialect.name
    except Exception:
        return
    if dialect not in ("postgresql", "postgres"):
        return

    # You can disable by setting AUTO_CREATE_INDEXES=0
    enabled = os.environ.get("AUTO_CREATE_INDEXES", "").strip()
    if enabled == "0":
        return

    def worker():
        with app.app_context():
            try:
                stmts = [
                    # Reservations overlap checks / listings
                    "CREATE INDEX IF NOT EXISTS idx_reservation_date_status_booking_time ON reservation (date, status, booking_type, time)",
                    "CREATE INDEX IF NOT EXISTS idx_reservation_user_date_status ON reservation (user_id, date, status)",
                    # Orders (rider tracking + user dashboards)
                    "CREATE INDEX IF NOT EXISTS idx_order_rider_delivery_status_id ON \"order\" (rider_id, delivery_status, id)",
                    "CREATE INDEX IF NOT EXISTS idx_order_user_created_at ON \"order\" (user_id, created_at DESC)",
                    # Reviews admin page
                    "CREATE INDEX IF NOT EXISTS idx_review_status_created_at ON review (status, created_at DESC)",
                    # Menu page category browsing
                    "CREATE INDEX IF NOT EXISTS idx_menu_item_category_name ON menu_item (category, name)",
                    # Order chat
                    "CREATE INDEX IF NOT EXISTS idx_order_chat_order_id_created_at ON order_chat (order_id, created_at DESC)",
                    # Order items / recipes joins
                    "CREATE INDEX IF NOT EXISTS idx_order_item_order_menuitem ON order_item (order_id, menu_item_id)",
                    "CREATE INDEX IF NOT EXISTS idx_menu_item_ingredient_menuitem_ingredient ON menu_item_ingredient (menu_item_id, ingredient_id)",
                ]
                conn = db.engine.connect()
                try:
                    for s in stmts:
                        conn.execute(sql_text(s))
                    conn.commit()
                finally:
                    conn.close()
            except Exception as e:
                # Do not crash app; just log.
                print(f"Index creation skipped/failed: {e}")

    threading.Thread(target=worker, daemon=True).start()

_maybe_create_indexes_background()


@app.before_request
def init_session():
    """Initialize session - equivalent to PHP session_start()"""
    if session:
        pass
    session.permanent = True

@app.after_request
def add_static_cache_headers(resp):
    """
    Strong caching for static assets to reduce repeat loading.
    """
    try:
        path = request.path or ""
        if path.startswith("/static/"):
            resp.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    except Exception:
        pass
    return resp

@app.context_processor
def inject_config():
    from utils import load_site_settings
    return dict(
        FACEBOOK_APP_ID=app.config.get('FACEBOOK_APP_ID'),
        GOOGLE_CLIENT_ID=app.config.get('GOOGLE_CLIENT_ID'),
        get_ph_time=get_ph_time,
        site=load_site_settings()
    )

import traceback
import sys

@app.errorhandler(Exception)
def handle_exception(e):
    # Pass through HTTP errors
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    
    # Log the full traceback to the Render logs
    print("🚨 TRACEBACK ERROR LOGGED BY ANTIGRAVITY:", file=sys.stderr)
    traceback.print_exc()
    
    # Try to render the 500 error page if it exists, else return text
    return f"Internal Server Error:\n\n{traceback.format_exc()}", 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    # Get local IP address
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    # Print accessible URLs
    print("\n" + "="*60)
    print("Le Maison Flask App is Running!")
    print("="*60)
    print(f"Local Access:        http://localhost:5000")
    print(f"Local IP Access:     http://127.0.0.1:5000")
    print(f"Network Access:      http://{local_ip}:5000")
    print("="*60 + "\n")
    
    # Run with debug=True for development only
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    socketio.run(app, debug=debug_mode, host='0.0.0.0', port=5000)
