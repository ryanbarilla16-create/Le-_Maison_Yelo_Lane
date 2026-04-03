import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Security Key for Flask Session tracking
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'super_secret_key_123'
    FACEBOOK_APP_ID = os.environ.get('FACEBOOK_APP_ID') or 'YOUR_FACEBOOK_APP_ID_HERE'
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID') or 'YOUR_GOOGLE_CLIENT_ID_HERE'
    
    
    # Neon PostgreSQL (Primary Database)
    _db_url = os.environ.get("NEON_DATABASE_URL")
    
    if not _db_url:
        # Fallback to SQLite for local development
        import sys
        if 'pytest' not in sys.modules:
            print("⚠️  Warning: NEON_DATABASE_URL not set. Using SQLite for development.")
        _db_url = "sqlite:///lemaisondb.db"
    
    # Neon strings often use `postgres://`, but SQLAlchemy requires `postgresql://`
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
        
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
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', 'ryanbarilla254@gmail.com')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', 'smqnvgtyfgwzipqr')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_USERNAME', 'ryanbarilla254@gmail.com')
