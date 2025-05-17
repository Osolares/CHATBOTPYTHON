from datetime import datetime
from config import db, now
from utils.timezone import now

class UserSession(db.Model):
    __tablename__ = 'user_sessions'

    idUser = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20))
    email = db.Column(db.String(120), unique=True)
    telegram_id = db.Column(db.String(50), unique=True)
    messenger_id = db.Column(db.String(50), unique=True)
    nombre = db.Column(db.String(25))
    apellido = db.Column(db.String(25))
    tipo_usuario = db.Column(db.String(50), default='cliente')  # opciones: admin, colaborador, cliente

    #last_interaction = db.Column(db.DateTime, default=now)
    last_interaction = db.Column(db.DateTime, default=now)  # Usa la función centralizada

    mostro_bienvenida = db.Column(db.Boolean, default=False)
    ultima_alerta_horario = db.Column(db.DateTime)

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
    serie_motor = db.Column(db.String(50))

    session_id = db.Column(db.Integer, db.ForeignKey('user_sessions.idUser'), nullable=False)  # FIX: Integer

class Log(db.Model):
    __tablename__ = 'logs'

    id = db.Column(db.Integer, primary_key=True)
    #fecha_y_hora = db.Column(db.DateTime, default=now)
    fecha_y_hora = db.Column(db.DateTime, default=now)  # Usa la función centralizada
    texto = db.Column(db.Text)
    
    session_id = db.Column(db.Integer, db.ForeignKey('user_sessions.idUser'), index=True)

# models.py
class Configuration(db.Model):
    __tablename__ = 'configurations'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='activo') # 'activo', 'bloqueado', 'inactivo'
    descripcion = db.Column(db.String(255))  # Opcional: para mostrar en el admin
    created_at = db.Column(db.DateTime, default=now)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)

class Memory(db.Model):
    __tablename__ = 'memories'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('user_sessions.idUser'), nullable=False)
    key = db.Column(db.String(100))
    value = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)
