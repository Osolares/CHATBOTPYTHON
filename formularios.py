from datetime import datetime
from models import UserSession, ModelProduct, db
import time

def formulario_motor(number):
    """Inicia el flujo de cotización creando o actualizando sesión"""
    session = UserSession.query.get(number)
    if not session:
        session = UserSession(phone_number=number)
        db.session.add(session)
    
    # Crear o reiniciar producto asociado
    producto = ModelProduct.query.filter_by(session_id=number).first()
    if not producto:
        producto = ModelProduct(session_id=number)
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
    producto = ModelProduct.query.filter_by(session_id=number).first()
    if not producto:
        return [{
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {"body": "⚠️ Sesión no encontrada. Envía '1' para comenzar."}
        }]

    handlers = {
        'awaiting_marca': manejar_paso_marca,
        'awaiting_modelo': manejar_paso_modelo,
        'awaiting_combustible': manejar_paso_combustible,
        'awaiting_año': manejar_paso_año,
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

def manejar_paso_año(number, user_message, producto):
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
        ModelProduct.query.filter_by(session_id=number).delete()
        db.session.delete(session)
        db.session.commit()
    
    return [
        {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {
                "body": "🔁 Formulario cancelado correctamente. Escribe '0' si deseas ver el menú."
            }
        }
    ]

def actualizar_interaccion(number):
    """Actualiza la marca de tiempo de la sesión"""
    session = UserSession.query.get(number)
    if session:
        session.last_interaction = datetime.utcnow()
        db.session.commit()