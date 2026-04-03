"""
Flask extensions initialization module.
Extensions are created here to avoid circular imports.
"""
from flask_socketio import SocketIO

socketio = SocketIO(cors_allowed_origins="*")
