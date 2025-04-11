from datetime import datetime, timedelta
from models import UserSession, ProductModel, db
import time

def formulario_motor(number):
    """Inicia el flujo de cotización creando o actualizando sesión"""
    session = UserSession.query.get(number)
    if not session:
        session = UserSession(phone_number=number)
        db.session.add(session)

    # Crear o reiniciar producto asociado
    producto = ProductModel.query.filter_by(session_id=number).first()
    if not producto:
        producto = ProductModel(session_id=number)
        db.session.add(producto)
    
    producto.current_step = 'awaiting_marca'
    session.last_interaction = datetime.utcnow()
    db.session.commit()

    return [
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": number,
            "type": "text",
            "text": {
                "body": "🔧 *Cotización de repuestos*\n\n📝Escribe la *MARCA* de tu vehículo:\n_(Ej: Toyota, Mitsubishi, Kia, Hyundai)_"
            }
        }
    ]

def manejar_paso_actual(number, user_message):
    """Maneja todos los pasos del formulario"""
    session = UserSession.query.get(number)
    producto = ProductModel.query.filter_by(session_id=number).first()
    if not producto:
        return [{
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {"body": "⚠️ Sesión no encontrada. Envía '1' para comenzar."}
        }]
    
    elif session and (
        user_message in ["exit", "cancel"] or 
        (
            session.last_interaction and 
            datetime.utcnow() - session.last_interaction > timedelta(hours=1)
        )
    ):
        cancelar_flujo(number)

    handlers = {
        'awaiting_marca': manejar_paso_marca,
        'awaiting_modelo': manejar_paso_modelo,
        'awaiting_combustible': manejar_paso_combustible,
        'awaiting_año': manejar_paso_anio,
        'awaiting_tipo_repuesto': manejar_paso_tipo_repuesto,
        'awaiting_comentario': manejar_paso_comentario
    }

    handler = handlers.get(producto.current_step)
    return handler(number, user_message, producto) if handler else [{
        "messaging_product": "whatsapp",
        "to": number,
        "type": "text",
        "text": {"body": "⚠️ Flujo no reconocido. Envía '1' para reiniciar."}
    }]

def manejar_paso_marca(number, user_message, producto):
    producto.marca = user_message
    producto.current_step = 'awaiting_modelo'
    actualizar_interaccion(number)
    
    return [
        {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {
                "body": f"✅ Marca: {user_message}\n\n📝Ahora escribe la *LINEA*:\n_(Ej: L200, Hilux, Terracan, Sportage)_"
            }
        }
    ]

def manejar_paso_modelo(number, user_message, producto):
    producto.linea = user_message
    producto.current_step = 'awaiting_combustible'
    actualizar_interaccion(number)
    
    return [
        {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": f"✅ Marca: {producto.marca}\n✅ Línea: {user_message}\n\n🫳Selecciona el *COMBUSTIBLE:*"
                },
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "comb_gasolina", "title": "Gasolina"}},
                        {"type": "reply", "reply": {"id": "comb_diesel", "title": "Diésel"}}
                    ]
                }
            }
        }
    ]

def manejar_paso_combustible(number, user_message, producto):
    producto.combustible = "Gasolina" if "gasolina" in user_message.lower() else "Diesel"
    producto.current_step = 'awaiting_año'
    actualizar_interaccion(number)
    
    return [
        {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {
                "body": f"✅ Marca: {producto.marca}\n✅ Línea: {user_message}\n✅ Combustible: {producto.combustible}\n\n📝Escribe el *AÑO* del vehículo:\n_(Ej: 2000, 2005, 2010, 2018, 2020)_"
            }
        }
    ]

def manejar_paso_anio(number, user_message, producto):
    if not user_message.isdigit() or not (1900 < int(user_message) <= datetime.now().year + 1):
        return [{
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {
                "body": "⚠️ Año inválido. Ingresa un año entre 1900 y actual.\nEjemplo: 2015"
            }
        }]
    
    producto.modelo_anio = user_message
    producto.current_step = 'awaiting_tipo_repuesto'
    actualizar_interaccion(number)

    return [
        {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {
                "body": f"✅ Marca: {producto.marca}\n✅ Línea: {user_message}\n✅ Combustible: {producto.combustible}\n✅ Año/Modelo: {producto.modelo_anio}\n\n📝Escribe el *TIPO DE REPUESTO* que necesitas:\n_(Ej: Motor, Culata, Turbo, Cigüeñal)_"
            }
        }
    ]

def manejar_paso_tipo_repuesto(number, user_message, producto):
    producto.tipo_repuesto = user_message
    producto.current_step = 'awaiting_comentario'
    actualizar_interaccion(number)

    return [
        {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {
                "body": f"✅ Marca: {producto.marca}\n✅ Línea: {user_message}\n✅ Combustible: {producto.combustible}\n✅ Año/Modelo: {producto.modelo_anio}\n✅ Tipo de repuesto: {producto.tipo_repuesto}\n\n📝Escribe una *DESCRIPCIÓN O COMENTARIO FINAL*:\n_Si no tienes comentarios escribe *No*_"
            }
        }
    ]

def manejar_paso_comentario(number, user_message, producto):
    producto.estado = user_message
    producto.current_step = 'completed'
    actualizar_interaccion(number)

    return [
        {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": f"✅ *Datos registrados:*\n\n• *Marca:* {producto.marca}\n• *Modelo:* {producto.linea}\n• *Combustible:* {producto.combustible}\n• *Año:* {producto.modelo_anio}\n• Tipo de repuesto: {producto.tipo_repuesto}\n• Descripción: {producto.estado}\n\n"
                },
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "cotizar_si", "title": "✅ Sí, cotizar"}},
                        {"type": "reply", "reply": {"id": "salir_flujo", "title": "❌ Salir/Cancelar"}}
                    ]
                }
            }
        }
    ]

def cancelar_flujo(number):
    """Limpia la sesión y productos asociados"""
    session = UserSession.query.get(number)
    if session:
        # Eliminar productos asociados
        ProductModel.query.filter_by(session_id=number).delete()
        db.session.delete(session)
        db.session.commit()
    
    return [
        {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {
                "body": "🚪 Formulario cancelado. Has salido del formulario actual. ¿Qué deseas hacer ahora?"
            }
        },
        {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {
                    "text": "🌐 Visita nuestro sitio web www.intermotores.com para más información.\n\n1️⃣ ⚙ Motores\n2️⃣ 🛞 Repuestos\n3️⃣ 📍 Ubicación\n4️⃣ 🕜 Horario de Atención\n5️⃣ ☎ Contacto\n6️⃣  💳 Formas de pago y números de cuenta\n7️⃣ ⏳ Esperar para ser atendido por nuestro personal\n8️⃣ 🚛 Opciones de envío\n0️⃣ 🔙 Regresar al Menú \n\n📌 *Escribe el número #️⃣ de tu elección.*"
                },
                "footer": {
                    "text": ""
                },
                "action": {
                    "button": "Ver Menú",
                    "sections": [
                        {
                            "title": "Opciones Principales",
                            "rows": [
                                {"id": "1", "title": "1️⃣ ⚙Motores", "description": "Cotizar Motores"},
                                {"id": "2", "title": "2️⃣ 🛞Repuestos", "description": "Cotizar Repuestos"},
                                {"id": "3", "title": "3️⃣ 📍Ubicación", "description": "Dónde estamos ubicados"},
                                {"id": "4", "title": "4️⃣ 🕜Horario", "description": "Horario de atención"},
                                {"id": "5", "title": "5️⃣ ☎Contacto", "description": "Contáctanos"},
                                {"id": "6", "title": "6️⃣ 💳Cuentas y Pagos", "description": "Cuentas de banco y formas de pago"},
                                {"id": "7", "title": "7️⃣ ⏳Hablar con personal", "description": "Esperar para ser atendido por nuestro personal"},
                                {"id": "8", "title": "8️⃣ 🚛Envíos", "description": "Opciones de envío"}
                                ]
                        }
                    ]
                }
            }
        }
    ]

def actualizar_interaccion(number):
    """Actualiza la marca de tiempo de la sesión"""
    session = UserSession.query.get(number)
    if session:
        session.last_interaction = datetime.utcnow()
        db.session.commit()