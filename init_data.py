# init_data.py

from models import db, Configuration, UserSession
from config import now

def inicializar_configuracion():
    configuraciones_defecto = {
        "HORARIO_LUNES_VIERNES": "08:00-17:30",
        "HORARIO_SABADO": "08:00-12:30",
        "HORARIO_DOMINGO": "cerrado",
        "MENSAJE_BIENVENIDA": "👋 Bienvenido a Intermotores, ¿en qué podemos ayudarte hoy?",
        "TOKEN_SERVICIO_X": "REEMPLAZAR_ESTE_VALOR"
    }

    for clave, valor in configuraciones_defecto.items():
        existente = Configuration.query.filter_by(key=clave).first()
        if not existente:
            nueva = Configuration(key=clave, value=valor)
            db.session.add(nueva)
    db.session.commit()
    print("✅ Configuración inicial creada")

def inicializar_usuarios():
    usuarios_defecto = [
        {"phone_number": "50255105350", "nombre": "Oscar", "apellido": "Solares", "tipo_usuario": "admin"},
        {"phone_number": "50255101111", "nombre": "Soporte", "apellido": "Técnico", "tipo_usuario": "colaborador"},
        {"phone_number": "50255102222", "nombre": "Carlos", "apellido": "Cliente", "tipo_usuario": "cliente"}
    ]

    for usr in usuarios_defecto:
        existente = UserSession.query.filter_by(phone_number=usr["phone_number"]).first()
        if not existente:
            nuevo_usuario = UserSession(
                phone_number=usr["phone_number"],
                nombre=usr["nombre"],
                apellido=usr["apellido"],
                tipo_usuario=usr["tipo_usuario"],
                last_interaction=now()
            )
            db.session.add(nuevo_usuario)
    db.session.commit()
    print("✅ Usuarios de prueba creados")

def inicializar_todo():
    inicializar_configuracion()
    inicializar_usuarios()
