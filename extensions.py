# extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO

# Create the singleton but don't bind it to the app yet.
socketio = SocketIO(cors_allowed_origins="*")

db = SQLAlchemy()
