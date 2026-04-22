import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Security Key for Flask Session tracking
    SECRET_KEY = os.environ.get('SECRET_KEY')
    FACEBOOK_APP_ID = os.environ.get('FACEBOOK_APP_ID')
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    XENDIT_SECRET_KEY = os.environ.get('XENDIT_SECRET_KEY')
    
    
    # PostgreSQL Database (supports Neon, Supabase, or any provider)
    # Priority: NEON_DATABASE_URL -> DATABASE_URL -> SQLite fallback
    _db_url = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL")
    
    if not _db_url:
        # Fallback to SQLite for local development
        import sys
        if 'pytest' not in sys.modules:
            print("[WARNING] No DATABASE_URL set. Using SQLite for development.")
        _db_url = "sqlite:///lemaisondb.db"
    
    # Neon strings often use `postgres://`, but SQLAlchemy requires `postgresql://`
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    
    # Force sslmode=require for production postgres connections if not present
    if "postgresql" in _db_url and "sslmode" not in _db_url:
        _db_url += ("&" if "?" in _db_url else "?") + "sslmode=require"
        
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
    
    # Mail Config (for OTP)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    _mail_port = os.environ.get('MAIL_PORT', '587')
    MAIL_PORT = int(_mail_port) if _mail_port and _mail_port.isdigit() else 587
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = ('Le Maison - Yelo Lane', os.environ.get('MAIL_USERNAME'))
