from datetime import datetime
from config import db

class UserSession(db.Model):
    __tablename__ = 'user_sessions'
    
    phone_number = db.Column(db.String(20), primary_key=True)
    current_step = db.Column(db.String(50), default='awaiting_marca')
    marca = db.Column(db.String(50))
    modelo = db.Column(db.String(50))
    combustible = db.Column(db.String(20))
    año = db.Column(db.String(10))
    last_interaction = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Session {self.phone_number}>'