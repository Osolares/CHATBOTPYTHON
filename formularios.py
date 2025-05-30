from datetime import datetime, timedelta
from models import UserSession, ProductModel, db
from menus import generar_list_menu
from app import handle_cotizacion_slots  # Importación directa, sin circularidad si solo usas aquí
# from catalog_service import get_marcas_permitidas, get_series_disponibles, get_categorias_disponibles

lista_cancelar = ["exit", "cancel", "salir", "cancelar"]

def formulario_motor(number):
    """Inicia el flujo de cotización creando o actualizando sesión y producto"""
    session = UserSession.query.filter_by(phone_number=number).first()
    if not session:
        session = UserSession(phone_number=number, last_interaction=datetime.utcnow())
        db.session.add(session)
        db.session.commit()
    else:
        session.last_interaction = datetime.utcnow()
        db.session.commit()
    
    # Borra productos previos para que sea limpio
    ProductModel.query.filter_by(session_id=session.idUser).delete(synchronize_session=False)
    db.session.commit()
    
    producto = ProductModel(session_id=session.idUser, current_step='awaiting_marca')
    db.session.add(producto)
    db.session.commit()
    
    return [{
        "messaging_product": "whatsapp",
        "to": number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": "🔧 *Formulario para cotización de motores y repuestos* 🛻\n\n📝Escribe la *MARCA* de tu vehículo:\n_(Ej: Toyota, Mitsubishi, Kia, Hyundai)_"
            },
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "exit", "title": "❌ Cancelar/Salir"}}
                ]
            }
        }
    }]

def manejar_paso_actual(number, user_message):
    session = UserSession.query.filter_by(phone_number=number).first()
    producto = ProductModel.query.filter_by(session_id=session.idUser).first() if session else None

    # CANCELA si no hay sesión o producto
    if not session or not producto:
        return cancelar_flujo(number)
    if user_message.lower() in lista_cancelar:
        return cancelar_flujo(number)
    if session.last_interaction and (datetime.utcnow() - session.last_interaction > timedelta(hours=1)):
        return cancelar_flujo(number)
    
    paso = producto.current_step
    handlers = {
        'awaiting_marca': manejar_paso_marca,
        'awaiting_modelo': manejar_paso_modelo,
        'awaiting_combustible': manejar_paso_combustible,
        'awaiting_año': manejar_paso_anio,
        'awaiting_tipo_repuesto': manejar_paso_tipo_repuesto,
        'awaiting_comentario': manejar_paso_comentario,
        'completed': manejar_paso_finish
    }
    handler = handlers.get(paso)
    return handler(number, user_message) if handler else cancelar_flujo(number)

def manejar_paso_marca(number, user_message):
    session = UserSession.query.filter_by(phone_number=number).first()
    producto = ProductModel.query.filter_by(session_id=session.idUser).first()
    if not producto:
        return cancelar_flujo(number)
    producto.marca = user_message
    producto.current_step = 'awaiting_modelo'
    session.last_interaction = datetime.utcnow()
    db.session.commit()
    return [{
        "messaging_product": "whatsapp",
        "to": number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": f"✅ Marca: {user_message}\n\n📝Ahora escribe la *LINEA*:\n_(Ej: L200, Hilux, Terracan, Sportage)_"},
            "action": {"buttons": [{"type": "reply", "reply": {"id": "exit", "title": "❌ Cancelar/Salir"}}]}
        }
    }]

def manejar_paso_modelo(number, user_message):
    session = UserSession.query.filter_by(phone_number=number).first()
    producto = ProductModel.query.filter_by(session_id=session.idUser).first()
    if not producto:
        return cancelar_flujo(number)
    producto.linea = user_message
    producto.current_step = 'awaiting_combustible'
    session.last_interaction = datetime.utcnow()
    db.session.commit()
    return [{
        "messaging_product": "whatsapp",
        "to": number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": f"✅ Marca: {producto.marca}\n✅ Línea: {user_message}\n\n🫳Selecciona el *COMBUSTIBLE:*"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "gasolina", "title": "Gasolina"}},
                    {"type": "reply", "reply": {"id": "diesel", "title": "Diésel"}},
                    {"type": "reply", "reply": {"id": "exit", "title": "❌ Cancelar/Salir"}}
                ]
            }
        }
    }]

def manejar_paso_combustible(number, user_message):
    session = UserSession.query.filter_by(phone_number=number).first()
    producto = ProductModel.query.filter_by(session_id=session.idUser).first()
    if not producto:
        return cancelar_flujo(number)

    lista_combustible = ["gasolina", "diesel", "disel", "diésel", "gas", "gas propano"]
    if not user_message.lower() in lista_combustible:
        return [{
            "messaging_product": "whatsapp",
            "to": number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": "⚠️ Combustible inválido. Ingresa el combustible.\nEjemplo: Gasolina, Diesel "},
                "action": {"buttons": [{"type": "reply", "reply": {"id": "exit", "title": "❌ Cancelar/Salir"}}]}
            }
        }]

    producto.combustible = user_message
    producto.current_step = 'awaiting_año'
    session.last_interaction = datetime.utcnow()
    db.session.commit()
    return [{
        "messaging_product": "whatsapp",
        "to": number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": f"✅ Marca: {producto.marca}\n✅ Línea: {producto.linea}\n✅ Combustible: {producto.combustible}\n\n📝Escribe el *AÑO* del vehículo:\n_(Ej: 1995, 2000, 2005, 2010, 2018, 2020)_"
            },
            "action": {"buttons": [{"type": "reply", "reply": {"id": "exit", "title": "❌ Cancelar/Salir"}}]}
        }
    }]

def manejar_paso_anio(number, user_message):
    session = UserSession.query.filter_by(phone_number=number).first()
    producto = ProductModel.query.filter_by(session_id=session.idUser).first()
    if not producto:
        return cancelar_flujo(number)

    if not user_message.isdigit() or not (1950 < int(user_message) <= datetime.now().year + 1):
        return [{
            "messaging_product": "whatsapp",
            "to": number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": "⚠️ Año inválido. Ingresa un año entre 1950 y actual.\nEjemplo: 1995, 2000, 2005, 2008, 2015, 2020 "},
                "action": {"buttons": [{"type": "reply", "reply": {"id": "exit", "title": "❌ Cancelar/Salir"}}]}
            }
        }]

    producto.modelo_anio = user_message
    producto.current_step = 'awaiting_tipo_repuesto'
    session.last_interaction = datetime.utcnow()
    db.session.commit()
    return [{
        "messaging_product": "whatsapp",
        "to": number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": f"✅ Marca: {producto.marca}\n✅ Línea: {producto.linea}\n✅ Combustible: {producto.combustible}\n✅ Año/Modelo: {producto.modelo_anio}\n\n📝Escribe el *TIPO DE REPUESTO* que necesitas:\n_(Ej: Motor, Culata, Turbo, Cigüeñal)_"
            },
            "action": {"buttons": [{"type": "reply", "reply": {"id": "exit", "title": "❌ Cancelar/Salir"}}]}
        }
    }]

def manejar_paso_tipo_repuesto(number, user_message):
    session = UserSession.query.filter_by(phone_number=number).first()
    producto = ProductModel.query.filter_by(session_id=session.idUser).first()
    if not producto:
        return cancelar_flujo(number)
    producto.tipo_repuesto = user_message
    producto.current_step = 'awaiting_comentario'
    session.last_interaction = datetime.utcnow()
    db.session.commit()
    return [{
        "messaging_product": "whatsapp",
        "to": number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": f"✅ Marca: {producto.marca}\n✅ Línea: {producto.linea}\n✅ Combustible: {producto.combustible}\n✅ Año/Modelo: {producto.modelo_anio}\n✅ Tipo de repuesto: {producto.tipo_repuesto}\n\n📝Escribe una *DESCRIPCIÓN O COMENTARIO FINAL*:\n_Si no tienes comentarios escribe *No* o presiona el botón_"
            },
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "no", "title": "No"}},
                    {"type": "reply", "reply": {"id": "exit", "title": "❌ Cancelar/Salir"}}
                ]
            }
        }
    }]

def manejar_paso_comentario(number, user_message):
    session = UserSession.query.filter_by(phone_number=number).first()
    producto = ProductModel.query.filter_by(session_id=session.idUser).first()
    if not producto:
        return cancelar_flujo(number)
    producto.estado = user_message
    producto.current_step = 'completed'
    session.last_interaction = datetime.utcnow()
    db.session.commit()
    return [{
        "messaging_product": "whatsapp",
        "to": number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": f"✅ *Datos registrados:*\n\n• *Marca:* {producto.marca}\n• *Modelo:* {producto.linea}\n• *Combustible:* {producto.combustible}\n• *Año:* {producto.modelo_anio}\n• *Tipo de repuesto:* {producto.tipo_repuesto}\n• *Descripción:* {producto.estado}\n\n"
            },
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "cotizar_si", "title": "✅ Sí, cotizar"}},
                    {"type": "reply", "reply": {"id": "cancelar", "title": "❌ Salir/Cancelar"}}
                ]
            }
        }
    }]

def manejar_paso_finish(number, user_message):
    session = UserSession.query.filter_by(phone_number=number).first()
    producto = ProductModel.query.filter_by(session_id=session.idUser).first()
    if not producto:
        return cancelar_flujo(number)
    producto.current_step = 'finished'
    session.last_interaction = datetime.utcnow()
    db.session.commit()

    if user_message.lower() in lista_cancelar:
        return cancelar_flujo(number)

    if user_message == "cotizar_si":
        # Prepara los slots para handle_cotizacion_slots
        slots = {
            "tipo_repuesto": producto.tipo_repuesto,
            "marca": producto.marca,
            "linea": producto.linea,
            "año": producto.modelo_anio,
            "serie_motor": None,
            "cc": None,
            "combustible": producto.combustible,
        }
        state = {
            "session": session,
            "phone_number": number,
            "source": "whatsapp",
            "user_msg": "Cotizar",
            "slots": slots,
            "response_data": [],
            "message_data": {},
        }
        # Elimina los productos de la sesión (ya terminado)
        ProductModel.query.filter_by(session_id=session.idUser).delete(synchronize_session=False)
        db.session.commit()
        return handle_cotizacion_slots(state)["response_data"]

    # Si llega aquí por error, cancela
    return cancelar_flujo(number)

def cancelar_flujo(number):
    session = UserSession.query.filter_by(phone_number=number).first()
    if session:
        ProductModel.query.filter_by(session_id=session.idUser).delete(synchronize_session=False)
        session.last_interaction = datetime.utcnow()
        db.session.commit()
    return [
        {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {"body": "🚪 Formulario cancelado. Has salido del formulario actual. ¿Qué deseas hacer ahora?"}
        },
        generar_list_menu(number)
    ]
