from flask import Flask
from flask_socketio import SocketIO
try:
    app = Flask(__name__)
    socketio = SocketIO(app, async_mode='eventlet')
    print("SocketIO initialized with eventlet successfully.")
except Exception as e:
    print(f"SocketIO initialization failed: {e}")
