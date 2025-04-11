from datetime import datetime
from config import db

class UserSession(db.Model):
    __tablename__ = 'user_sessions'

    idUser = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), unique=True)
    nombre = db.Column(db.String(25))
    apellido = db.Column(db.String(25))
    last_interaction = db.Column(db.DateTime, default=datetime.utcnow)

    logs = db.relationship('Log', backref='session', lazy=True)
    model_products = db.relationship('ProductModel', backref='session', lazy=True)

class ProductModel(db.Model):
    __tablename__ = 'model_products'

    idProduct = db.Column(db.Integer, primary_key=True)
    current_step = db.Column(db.String(50), default='awaiting_marca')
    marca = db.Column(db.String(50))
    linea = db.Column(db.String(50))
    combustible = db.Column(db.String(20))
    modelo_anio = db.Column(db.String(10))
    tipo_repuesto = db.Column(db.String(50))
    estado = db.Column(db.String(100))

    session_id = db.Column(db.Integer, db.ForeignKey('user_sessions.idUser'), nullable=False)

class Log(db.Model):
    __tablename__ = 'logs'

    id = db.Column(db.Integer, primary_key=True)
    fecha_y_hora = db.Column(db.DateTime, default=datetime.utcnow)
    texto = db.Column(db.Text)

    session_id = db.Column(db.Integer, db.ForeignKey('user_sessions.idUser'))
