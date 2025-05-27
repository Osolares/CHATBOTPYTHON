# init_data.py

from models import db, Configuration, UserSession
from config import now
import json

# 1. Días festivos (fijos y por año específico)
DIAS_FESTIVOS_DEFECTO = [
    "01-01",         # Año Nuevo (cada año)
    "05-01",         # Día del Trabajo (cada año)
    "12-25",         # Navidad (cada año)
    "2025-04-17",    # Jueves Santo (sólo 2025)
    "2025-12-31"     # Fin de año (sólo 2025)
]

def inicializar_configuracion():
    configuraciones_defecto = {
        "HORARIO_LUNES": "08:00-17:30",
        "HORARIO_MARTES": "08:00-17:30",
        "HORARIO_MIERCOLES": "08:00-17:30",
        "HORARIO_JUEVES": "08:00-17:30",
        "HORARIO_VIERNES": "08:00-17:30",
        "HORARIO_SABADO": "08:00-12:30",
        "HORARIO_DOMINGO": None,
        "DIAS_FESTIVOS": json.dumps(DIAS_FESTIVOS_DEFECTO, ensure_ascii=False),
        # otros config...
    }

    for clave, valor in configuraciones_defecto.items():
        existente = Configuration.query.filter_by(key=clave).first()
        if not existente:
            nueva = Configuration(key=clave, value=valor if valor is not None else "")
            db.session.add(nueva)
    db.session.commit()
    print("✅ Configuración inicial creada")


import json
from models import db, Configuration

# Estructura de intenciones por defecto
INTENCIONES_BOT_DEFECTO = {
    "formas_pago": [
        "formas de pago", "medios de pago", "pagar con tarjeta", "aceptan tarjeta", "aceptan visa",
        "visa cuotas", "puedo pagar con", "puedo pagar", "metodos de pago", "pago contra entrega"
    ],
    "envios": [
        "envio", "hacen envíos", "métodos de env", "metodos de env", "entregan", "delivery", "a domicilio", "puerta de mi casa", "mandan a casa",
        "hacen envios", "enviar producto", "pueden enviar", "envian el "
    ],
    "ubicacion": [
        "donde estan", "ubicacion", "ubicación", "direccion", "dirección", "donde queda", "donde están",
        "ubicados", "mapa", "ubicacion tienda", "como llegar", "tienda fisica"
    ],
    "cuentas": [
        "numero de cuenta", "donde deposito ", "bancarias", "banrural", "industrial", "banco", "para depositar"
    ],
    "horario": [
        "horario", "atienden ", "abierto", "cierran", "abren", "a que hora", "a qué hora", "cuando abren", "horario de atencion"
    ],
    "contacto": [
        "contacto", "telefono", "celular", "comunicarme", "llamar", "numero de telefono", "donde puedo llamar"
    ],
    "mensaje_despedida": [
        "gracias por la informacion", "muy amable", "le agradezco", "feliz tarde", "adios", "saludos", "los visito", "feliz dia" , "feliz noche"
    ]
}

def inicializar_intenciones_bot():
    clave = "INTENCIONES_BOT"
    existente = Configuration.query.filter_by(key=clave).first()
    if not existente:
        config = Configuration(
            key=clave,
            value=json.dumps(INTENCIONES_BOT_DEFECTO, ensure_ascii=False)
        )
        db.session.add(config)
        db.session.commit()
        print("✅ Intenciones Bot inicializadas")
    else:
        print("🔹 Ya existen las intenciones bot")


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
        {"tipo": "bienvenida", "mensaje": "😃 ¡Bienvenido(a) a Intermotores Guatemala, qué gusto tenerte aquí! Dinos qué necesitas. 🚗\n\n🗒️ Consulta nuestro menú.", "canal": "whatsapp"},
        {"tipo": "bienvenida", "mensaje": "👋 ¡Bienvenido(a) a Intermotores Guatemala! Estamos aquí para ayudarte a encontrar el repuesto ideal para tu vehículo. 🚗\n\n🗒️ Consulta nuestro menú.", "canal": "whatsapp"},

        # Alerta fuera de horario (WhatsApp)
        {"tipo": "alerta_fuera_horario", "mensaje": "⌚ Gracias por comunicarte. Ahora mismo estamos fuera de horario, pero tu consulta es importante para nosotros. ¡Te responderemos pronto!", "canal": "all"},
        {"tipo": "alerta_fuera_horario", "mensaje": "🕒 Gracias por comunicarte con nosotros. En este momento estamos fuera de nuestro horario de atención.\n\n💬 Puedes continuar usando nuestro asistente y nuestro equipo te atenderá lo más pronto posible.", "canal": "all"},
        {"tipo": "alerta_fuera_horario", "mensaje": "⌛ Nuestro equipo está fuera de horario. Puedes dejar tu mensaje aquí y te reponderemos lo mas pronto posible.", "canal": "all"},

        # Re-bienvenida (WhatsApp)
        {"tipo": "re_bienvenida", "mensaje": "👋 ¡Hola de nuevo! ¿Te ayudamos con otra cotización? 🚗\n\n🗒️ Consulta nuestro menú.", "canal": "whatsapp"},
        {"tipo": "re_bienvenida", "mensaje": "🚗 ¿Necesitas otro repuesto? Estamos para servirte 🚗\n\n🗒️ Consulta nuestro menú..", "canal": "whatsapp"},
        {"tipo": "re_bienvenida", "mensaje": "👋 ¡Hola de nuevo! Gracias por contactar a Intermotores Guatemala. ¿En qué podemos ayudarte hoy? 🚗\n\n🗒️ Consulta nuestro menú.", "canal": "whatsapp"},
        {"tipo": "re_bienvenida", "mensaje": "👋 ¡Bienvenido(a) de nuevo! ¿En qué podemos ayudarte hoy?", "canal": "whatsapp"},
        {"tipo": "re_bienvenida", "mensaje": "🚗 ¡Hola Bienvenido(a) de nuevo a Intermotores Guatemala ¿Buscas un motor o repuesto? Pregúntanos sin compromiso.", "canal": "whatsapp"},
        # Mensaje global, para todos los canales (canal='all')

        #DIAS FESTIVOS
        {"tipo": "alerta_dia_festivo_01-01", "mensaje": "🎉 Hoy es 1 de enero (Año Nuevo). ¡Estamos cerrados! Disfruta tu día y escríbenos mañana.", "canal": "all"},
        {"tipo": "alerta_dia_festivo_05-01", "mensaje": "🎉 Hoy es 1 de mayo (Día del Trabajo). ¡Estamos cerrados! Gracias por tu preferencia.", "canal": "all"},
        {"tipo": "alerta_dia_festivo_12-25", "mensaje": "🎄 ¡Feliz Navidad! Hoy no laboramos. Puedes dejar tu mensaje y te atenderemos el siguiente día hábil.", "canal": "all"},
        {"tipo": "alerta_dia_festivo_2025-04-17", "mensaje": "⛪ Hoy es Jueves Santo y estamos de descanso. Te responderemos el próximo día hábil.", "canal": "all"},
        {"tipo": "alerta_dia_festivo", "mensaje": "🎉 Hoy es día festivo y estamos cerrados. Puedes dejar tu mensaje y te responderemos en el próximo día hábil.", "canal": "all"},

        # Formas de pago (varios, para rotar)
        #{"tipo": "formas_pago", "mensaje": "💳 Aceptamos efectivo, depósitos, transferencias, Visa Cuotas y pago contra entrega.", "canal": "whatsapp"},
        {"tipo": "formas_pago", "mensaje": "*💲Medios de pago:* \n\n 💵 Efectivo. \n\n 🏦 Depósitos o transferencias bancarias. \n\n 📦 Pago contra Entrega. \nPagas al recibir tu producto, aplica para envíos por medio de Guatex, el monto máximo es de Q5,000. \n\n💳 Visa Cuotas. \nHasta 12 cuotas con tu tarjeta visa \n\n💳 Cuotas Credomatic. \nHasta 12 cuotas con tu tarjeta BAC Credomatic \n\n🔗 Neo Link. \nTe enviamos un link para que pagues con tu tarjeta sin salir de casa", "canal": "whatsapp"},
        # Envíos
        {"tipo": "envios", "mensaje": "🏠*Enviamos nuestros productos hasta la puerta de su casa* \n\n 🛵 *Envíos dentro de la capital.* \n Hacemos envíos directos dentro de la ciudad capital, aldea Puerta Parada, Santa Catarina Pinula y sus alrededores \n\n 🚚 *Envío a Departamentos.* \nHacemos envíos a los diferentes departamentos del país por medio de terceros o empresas de transporte como Guatex, Cargo Express, Forza o el de su preferencia. \n\n ⏳📦 *Tiempo de envío.* \nLos pedidos deben hacerse con 24 horas de anticipación y el tiempo de entrega para los envíos directos es de 24 a 48 horas y para los envíos a departamentos depende directamente de la empresa encargarda.", "canal": "whatsapp"},
        # Ubicación
        {"tipo": "ubicacion", "mensaje": "📍  Estamos ubicados en km 13.5 carretera a El Salvador frente a Plaza Express a un costado de farmacia Galeno, en Intermotores", "canal": "whatsapp"},
        # Horario
        {"tipo": "horario", "mensaje": "📅 Horario de Atención:\n\n Lunes a Viernes\n🕜 8:00 am a 5:00 pm\n\nSábado\n🕜 8:00 am a 12:00 pm\n\nDomingo Cerrado 🤓", "canal": "whatsapp"},

        {"tipo": "contacto", "mensaje": "☎*Comunícate con nosotros será un placer atenderte* \n\n 📞 6637-9834 \n\n 📞 6646-6137 \n\n 📱 5510-5350 \n\n 🌐 www.intermotores.com  \n\n 📧 intermotores.ventas@gmail.com \n\n *Facebook* \n Intermotores GT\n\n *Instagram* \n Intermotores GT ", "canal": "whatsapp"},

        {"tipo": "mensaje_despedida", "mensaje": "De nada, ¡qué tengas buen día! 🚗💨", "canal": "whatsapp"},
        {"tipo": "mensaje_despedida", "mensaje": "De nada, ¡qué tengas un gran día! 😊🚗💨", "canal": "whatsapp"},
        {"tipo": "mensaje_despedida", "mensaje": "Fue un gusto ayudarte. ¡Hasta la próxima! 😊🔧", "canal": "whatsapp"},

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
    inicializar_intenciones_bot()