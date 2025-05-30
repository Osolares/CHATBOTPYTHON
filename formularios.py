from datetime import datetime, timedelta
from models import UserSession, ProductModel, db
from menus import generar_list_menu

lista_cancelar = ["exit", "cancel", "salir", "cancelar"]

def formulario_motor(number):
    """Inicia el flujo de cotización creando o actualizando sesión"""
    session = UserSession.query.filter_by(phone_number=number).first()
    if not session:
        session = UserSession(phone_number=number, last_interaction=datetime.utcnow())
        db.session.add(session)
        db.session.commit()
    else:
        # Refresca last_interaction por si la sesión existe
        session.last_interaction = datetime.utcnow()
        db.session.commit()

    # Siempre borra el producto anterior para evitar residuos de formularios previos
    ProductModel.query.filter_by(session_id=session.idUser).delete()
    db.session.commit()

    # Crea nuevo producto
    producto = ProductModel(session_id=session.idUser, current_step='awaiting_marca')
    db.session.add(producto)
    db.session.commit()

    return [{
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "interactive",
        "interactive":{
            "type":"button",
            "body": {
                "text": "🔧 *Formulario para cotización de motores y repuestos* 🛻\n\n📝Escribe la *MARCA* de tu vehículo:\n_(Ej: Toyota, Mitsubishi, Kia, Hyundai)_ "
            },
            "footer": {"text": ""},
            "action": {
                "buttons":[
                    {
                        "type": "reply",
                        "reply":{
                            "id":"exit",
                            "title":"❌ Cancelar/Salir"
                        }
                    }
                ]
            }
        }
    }]

def manejar_paso_actual(number, user_message):
    """Maneja todos los pasos del formulario"""

    # Siempre obtiene la última versión actualizada de session y producto
    session = UserSession.query.filter_by(phone_number=number).first()
    if not session:
        return error_inicio(number, "⚠️ Sesión no encontrada. Envía '1' para comenzar. ")

    producto = ProductModel.query.filter_by(session_id=session.idUser).first()
    if not producto:
        return error_inicio(number, "⚠️ Producto no encontrado. Envía '1' para comenzar. ")

    # Si cancela o timeout
    if user_message.lower() in lista_cancelar or (
        session.last_interaction and datetime.utcnow() - session.last_interaction > timedelta(hours=1)
    ):
        return cancelar_flujo(number)

    # Decide el paso según current_step
    paso = producto.current_step
    if paso == 'awaiting_marca':
        return manejar_paso_marca(number, user_message)
    elif paso == 'awaiting_modelo':
        return manejar_paso_modelo(number, user_message)
    elif paso == 'awaiting_combustible':
        return manejar_paso_combustible(number, user_message)
    elif paso == 'awaiting_año':
        return manejar_paso_anio(number, user_message)
    elif paso == 'awaiting_tipo_repuesto':
        return manejar_paso_tipo_repuesto(number, user_message)
    elif paso == 'awaiting_comentario':
        return manejar_paso_comentario(number, user_message)
    elif paso == 'completed':
        return manejar_paso_finish(number, user_message)
    else:
        return error_inicio(number, "⚠️ Flujo no reconocido. Envía '1' para reiniciar. ")

def error_inicio(number, mensaje):
    return [{
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "interactive",
        "interactive":{
            "type":"button",
            "body": {"text": mensaje},
            "footer": {"text": ""},
            "action": {
                "buttons":[
                    {
                        "type": "reply",
                        "reply":{
                            "id":"exit",
                            "title":"❌ Cancelar/Salir"
                        }
                    }
                ]
            }
        }
    }]

def manejar_paso_marca(number, user_message):
    session = UserSession.query.filter_by(phone_number=number).first()
    producto = ProductModel.query.filter_by(session_id=session.idUser).first()
    producto.marca = user_message
    producto.current_step = 'awaiting_modelo'
    session.last_interaction = datetime.utcnow()
    db.session.commit()
    return [{
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "interactive",
        "interactive":{
            "type":"button",
            "body": {
                "text": f"✅ Marca: {user_message}\n\n📝Ahora escribe la *LINEA*:\n_(Ej: L200, Hilux, Terracan, Sportage)_ "
            },
            "footer": {"text": ""},
            "action": {
                "buttons":[
                    {
                        "type": "reply",
                        "reply":{
                            "id":"exit",
                            "title":"❌ Cancelar/Salir"
                        }
                    }
                ]
            }
        }
    }]

def manejar_paso_modelo(number, user_message):
    session = UserSession.query.filter_by(phone_number=number).first()
    producto = ProductModel.query.filter_by(session_id=session.idUser).first()
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
            "body": {
                "text": f"✅ Marca: {producto.marca}\n✅ Línea: {user_message}\n\n🫳Selecciona el *COMBUSTIBLE:* "
            },
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "gasolina", "title": "Gasolina"}},
                    {"type": "reply", "reply": {"id": "diesel", "title": "Diésel"}},
                    {"type": "reply", "reply": {"id":"exit", "title":"❌ Cancelar/Salir"}}
                ]
            }
        }
    }]

def manejar_paso_combustible(number, user_message):
    session = UserSession.query.filter_by(phone_number=number).first()
    producto = ProductModel.query.filter_by(session_id=session.idUser).first()
    lista_combustible = ["gasolina", "diesel", "disel", "diésel", "gas", "gas propano"]
    if not user_message.lower() in lista_combustible:
        return error_inicio(number, "⚠️ Combustible inválido. Ingresa el combustible.\nEjemplo: Gasolina, Diesel ")

    producto.combustible = user_message
    producto.current_step = 'awaiting_año'
    session.last_interaction = datetime.utcnow()
    db.session.commit()
    return [{
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "interactive",
        "interactive":{
            "type":"button",
            "body": {
                "text": f"✅ Marca: {producto.marca}\n✅ Línea: {producto.linea}\n✅ Combustible: {producto.combustible}\n\n📝Escribe el *AÑO* del vehículo:\n_(Ej: 1995, 2000, 2005, 2010, 2018, 2020)_ "
            },
            "footer": {"text": ""},
            "action": {
                "buttons":[
                    {
                        "type": "reply",
                        "reply":{
                            "id":"exit",
                            "title":"❌ Cancelar/Salir"
                        }
                    }
                ]
            }
        }
    }]

def manejar_paso_anio(number, user_message):
    session = UserSession.query.filter_by(phone_number=number).first()
    producto = ProductModel.query.filter_by(session_id=session.idUser).first()
    if not user_message.isdigit() or not (1950 < int(user_message) <= datetime.now().year + 1):
        return error_inicio(number, "⚠️ Año inválido. Ingresa un año entre 1950 y actual.\nEjemplo: 1995, 2000, 2005, 2008, 2015, 2020 ")
    producto.modelo_anio = user_message
    producto.current_step = 'awaiting_tipo_repuesto'
    session.last_interaction = datetime.utcnow()
    db.session.commit()
    return [{
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "interactive",
        "interactive":{
            "type":"button",
            "body": {
                "text": f"✅ Marca: {producto.marca}\n✅ Línea: {producto.linea}\n✅ Combustible: {producto.combustible}\n✅ Año/Modelo: {producto.modelo_anio}\n\n📝Escribe el *TIPO DE REPUESTO* que necesitas:\n_(Ej: Motor, Culata, Turbo, Cigüeñal)_ "
            },
            "footer": {"text": ""},
            "action": {
                "buttons":[
                    {
                        "type": "reply",
                        "reply":{
                            "id":"exit",
                            "title":"❌ Cancelar/Salir"
                        }
                    }
                ]
            }
        }
    }]

def manejar_paso_tipo_repuesto(number, user_message):
    session = UserSession.query.filter_by(phone_number=number).first()
    producto = ProductModel.query.filter_by(session_id=session.idUser).first()
    producto.tipo_repuesto = user_message
    producto.current_step = 'awaiting_comentario'
    session.last_interaction = datetime.utcnow()
    db.session.commit()
    return [{
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "interactive",
        "interactive":{
            "type":"button",
            "body": {
                "text": f"✅ Marca: {producto.marca}\n✅ Línea: {producto.linea}\n✅ Combustible: {producto.combustible}\n✅ Año/Modelo: {producto.modelo_anio}\n✅ Tipo de repuesto: {producto.tipo_repuesto}\n\n📝Escribe una *DESCRIPCIÓN O COMENTARIO FINAL*:\n_Si no tienes comentarios escribe *No* o presiona el botón_ "
            },
            "footer": {"text": ""},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "no", "title": "No"}},
                    {"type": "reply", "reply": {"id":"exit", "title":"❌ Cancelar/Salir"}}
                ]
            }
        }
    }]

def manejar_paso_comentario(number, user_message):
    session = UserSession.query.filter_by(phone_number=number).first()
    producto = ProductModel.query.filter_by(session_id=session.idUser).first()
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
    # Llamada directa para integración con el handler de slots (no hagas import arriba, hazlo aquí)
    from app import handle_cotizacion_slots
    session = UserSession.query.filter_by(phone_number=number).first()
    producto = ProductModel.query.filter_by(session_id=session.idUser).first()
    producto.current_step = 'finished'
    session.last_interaction = datetime.utcnow()
    db.session.commit()

    if user_message.lower() in lista_cancelar:
        return cancelar_flujo(number)

    if user_message == "cotizar_si":
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
        resultado = handle_cotizacion_slots(state)
        ProductModel.query.filter_by(session_id=session.idUser).delete()
        db.session.commit()
        return resultado["response_data"]

    # Si no es cotizar, termina y muestra menú
    return [
        {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {
                "body": "🚪 Has salido del formulario de cotización."
            }
        },
        generar_list_menu(number)
    ]

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
            "text": {
                "body": "🚪 Formulario cancelado. Has salido del formulario actual. ¿Qué deseas hacer ahora?"
            }
        },
        generar_list_menu(number)
    ]
