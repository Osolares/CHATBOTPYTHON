from datetime import datetime
from config import db

class UserSession(db.Model):
    __tablename__ = 'user_sessions'
    
    idUser = db.Column(db.Integer, primary_key=True)
    
    # Identificadores por canal
    phone_number = db.Column(db.String(20), index=True)  # WhatsApp/Telegram
    email = db.Column(db.String(120), index=True)       # Web
    messenger_id = db.Column(db.String(50), index=True) # Facebook Messenger
    
    # Datos de perfil
    nombre = db.Column(db.String(25))
    apellido = db.Column(db.String(25))
    
    # Metadatos de interacción
    last_interaction = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    last_channel = db.Column(db.String(20))  # 'whatsapp', 'telegram', 'messenger', 'web'
    unified_id = db.Column(db.String(64), unique=True, index=True)  # Hash para identificación cruzada
    
    # Relaciones
    logs = db.relationship('Log', backref='session', lazy=True, cascade='all, delete-orphan')
    model_products = db.relationship('ProductModel', backref='session', lazy=True)
    sources = db.relationship('MessageSource', backref='session', lazy=True)

class MessageSource(db.Model):
    __tablename__ = 'message_sources'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('user_sessions.idUser'), nullable=False)
    channel = db.Column(db.String(20), nullable=False)   # Ej: 'whatsapp'
    channel_id = db.Column(db.String(120), nullable=False)  # ID único en ese canal
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Índice compuesto para búsquedas rápidas
    __table_args__ = (
        db.Index('idx_channel_unique', 'channel', 'channel_id', unique=True),
    )

class ProductModel(db.Model):
    __tablename__ = 'model_products'
    
    idProduct = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('user_sessions.idUser'), nullable=False)
    
    # Datos del flujo de producto
    current_step = db.Column(db.String(50), default='awaiting_marca')
    marca = db.Column(db.String(50))
    linea = db.Column(db.String(50))
    combustible = db.Column(db.String(20))
    modelo_anio = db.Column(db.String(10))
    tipo_repuesto = db.Column(db.String(50))
    estado = db.Column(db.String(100))
    
    # Índices para búsquedas frecuentes
    __table_args__ = (
        db.Index('idx_product_session', 'session_id', 'current_step'),
    )

class Log(db.Model):
    __tablename__ = 'logs'
    
    id = db.Column(db.Integer, primary_key=True)
    fecha_y_hora = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    texto = db.Column(db.Text, nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('user_sessions.idUser'))
    
    # Índices optimizados para búsquedas
    __table_args__ = (
        db.Index('idx_log_timestamp', 'fecha_y_hora'),
        db.Index('idx_log_content', db.func.substr('texto', 1, 50)),  # Para búsqueda de message_id
    )