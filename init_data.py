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

from models import MensajeBot, db
from config import now

def inicializar_mensajes_bot():
    mensajes = [
        # Bienvenidas (WhatsApp)
        {"tipo": "bienvenida", "mensaje": "👋 ¡Bienvenido! ¿En qué podemos ayudarte hoy?", "canal": "whatsapp"},
        {"tipo": "bienvenida", "mensaje": "🚗 ¡Hola! ¿Buscas un motor o repuesto? Pregúntanos sin compromiso.", "canal": "whatsapp"},
        {"tipo": "bienvenida", "mensaje": "😃 ¡Qué gusto tenerte aquí! Dinos qué necesitas.", "canal": "whatsapp"},
        # Alerta fuera de horario (WhatsApp)
        {"tipo": "alerta_fuera_horario", "mensaje": "🕒 Gracias por comunicarte. Ahora mismo estamos fuera de horario, pero tu consulta es importante. ¡Te responderemos pronto!", "canal": "all"},
        {"tipo": "alerta_fuera_horario", "mensaje": "🕒 Gracias por comunicarte con nosotros. En este momento estamos fuera de nuestro horario de atención.\n\n💬 Puedes continuar usando nuestro asistente y nuestro equipo te atenderá lo más pronto posible.", "canal": "all"},
        # Re-bienvenida (WhatsApp)
        {"tipo": "re_bienvenida", "mensaje": "👋 ¡Hola de nuevo! ¿Te ayudamos con otra cotización?", "canal": "whatsapp"},
        {"tipo": "re_bienvenida", "mensaje": "🚗 ¿Necesitas otro repuesto? Estamos para servirte.", "canal": "whatsapp"},
        # Mensaje global, para todos los canales (canal='all')
        {"tipo": "alerta_fuera_horario", "mensaje": "🕒 Nuestro equipo está fuera de horario. Puedes dejar tu mensaje aquí y te reponderemos lo mas pronto posible.", "canal": "all"},
    ]
    for datos in mensajes:
        existe = MensajeBot.query.filter_by(
            tipo=datos["tipo"], mensaje=datos["mensaje"], canal=datos["canal"]
        ).first()
        if not existe:
            nuevo = MensajeBot(
                tipo=datos["tipo"],
                mensaje=datos["mensaje"],
                canal=datos.get("canal", "all"),
                idioma=datos.get("idioma", "es"),
                activo=True,
                created_at=now(),
                updated_at=now()
            )
            db.session.add(nuevo)
    db.session.commit()
    print("✅ Mensajes dinámicos iniciales creados")




def inicializar_todo():
    inicializar_configuracion()
    inicializar_usuarios()
    inicializar_mensajes_bot()    # <--- Agrega esta línea
