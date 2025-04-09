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

class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha_y_hora = db.Column(db.DateTime, default=datetime.utcnow)
    texto = db.Column(db.TEXT)

# Crear tablas si no existen
def init_db():
    db.create_all()
