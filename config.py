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
    
    # Verify if PostgreSQL host is resolvable; if host DNS fails, fallback to local SQLite
    if _db_url and ("postgresql" in _db_url or "postgres" in _db_url):
        try:
            from urllib.parse import urlparse
            import socket
            parsed_host = urlparse(_db_url).hostname
            if parsed_host:
                socket.gethostbyname(parsed_host)
        except Exception as e:
            import sys
            if 'pytest' not in sys.modules:
                print(f"[WARNING] Database host '{parsed_host if 'parsed_host' in locals() else _db_url}' is unreachable ({e}). Falling back to local SQLite.")
            _db_url = None

    if not _db_url:
        # Fallback to SQLite for local development
        import sys
        if 'pytest' not in sys.modules:
            print("[WARNING] Using local SQLite database for development.")
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
        "pool_recycle": 120,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30,
        "connect_args": {
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        } if "postgresql" in _db_url else {}
    }

    # Archive database (separate file for SQLite, or `archive` schema on same Postgres DB)
    @staticmethod
    def _build_archive_uri(main_uri):
        explicit = os.environ.get("ARCHIVE_DATABASE_URL")
        if explicit:
            url = explicit
        elif main_uri.startswith("sqlite"):
            url = "sqlite:///lemaison_archive.db"
        elif "postgresql" in main_uri or "postgres" in main_uri:
            # Same Neon/Postgres database — tables stored in `archive` schema
            url = main_uri
        else:
            url = "sqlite:///lemaison_archive.db"

        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        if "postgresql" in url and "sslmode" not in url:
            url += ("&" if "?" in url else "?") + "sslmode=require"
        return url

    ARCHIVE_DATABASE_URI = _build_archive_uri.__func__(_db_url)
    SQLALCHEMY_BINDS = {"archive": ARCHIVE_DATABASE_URI}
    ARCHIVE_CONFIG_PATH = os.environ.get("ARCHIVE_CONFIG_PATH", "archive/config.json")
    # When True, archive tables use PostgreSQL schema `archive` (no second database needed)
    ARCHIVE_USE_SCHEMA = (
        ("postgresql" in _db_url or "postgres" in _db_url)
        and not os.environ.get("ARCHIVE_DATABASE_URL")
    )
    
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
