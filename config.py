from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()

class Config:
    SQLALCHEMY_DATABASE_URI = 'sqlite:///autoparts_chatbot.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TOKEN_WHATSAPP = "TOKEN_OIOT"  # Mueve el token aquí