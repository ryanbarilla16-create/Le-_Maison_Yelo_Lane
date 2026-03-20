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

app = Flask(__name__)
# Tell Flask it is behind a proxy (like LocalTunnel) so redirects use the correct url
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config.from_object(Config)

# Enable CORS for cross-origin requests from Flutter Web or mobile API
CORS(app, supports_credentials=True, resources={r"/api/*": {"origins": "*"}})

# Equivalent to PHP Session Properties configured
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# Database and Login Manager initialization
db.init_app(app)
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

@app.before_request
def init_session():
    """Initialize session - equivalent to PHP session_start()"""
    if session:
        pass
    session.permanent = True

@app.context_processor
def inject_config():
    return dict(
        FACEBOOK_APP_ID=app.config.get('FACEBOOK_APP_ID'),
        GOOGLE_CLIENT_ID=app.config.get('GOOGLE_CLIENT_ID'),
        get_ph_time=get_ph_time
    )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0')
