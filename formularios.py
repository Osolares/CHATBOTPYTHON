from datetime import datetime, timedelta
from models import UserSession, ProductModel, db
from session_manager import load_or_create_session, get_session
from menus import generar_list_menu, generar_menu_principal
import time

lista_cancelar = ["exit", "cancel", "salir", "cancelar"]

def formulario_motor(number):
    """Inicia el flujo de cotización creando o actualizando sesión"""
    session = get_session()
    if not session:
        session = load_or_create_session(number)

    # Crear o reiniciar producto asociado
    producto = ProductModel.query.filter_by(session_id=session.idUser).first()
    if not producto:
        producto = ProductModel(session_id=session.idUser)
        db.session.add(producto)
    
    producto.current_step = 'awaiting_marca'
    session.last_interaction = datetime.utcnow()
    db.session.commit()

    return [

        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": number,
            "type": "interactive",
            "interactive":{
                "type":"button",
                "body": {
                    "text": "🔧 *Formulario para cotización de motores y repuestos* 🛻\n\n📝Escribe la *MARCA* de tu vehículo:\n_(Ej: Toyota, Mitsubishi, Kia, Hyundai)_ "
                },
                "footer": {
                    "text": ""
                },
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
        }
    ]

def manejar_paso_actual(number, user_message):
    """Maneja todos los pasos del formulario"""
    from app import db  # Importar db aquí para asegurar el contexto

    #session = get_session()
    # Usar una nueva sesión para esta operación
    session = db.session
    user_session = session.query(UserSession).filter_by(phone_number=number).first()

    if not user_session:
        #session = load_or_create_session(number)

        user_session = UserSession(phone_number=number)
        session.add(user_session)
        session.commit()
        return formulario_motor(number)


    #producto = ProductModel.query.filter_by(session_id=session.idUser).first()
    producto = session.query(ProductModel).filter_by(session_id=user_session.idUser).first()

    if not producto:
        return [

            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "interactive",
                "interactive":{
                    "type":"button",
                    "body": {
                        "text": "⚠️ Sesión no encontrada. Envía '1' para comenzar. "
                    },
                    "footer": {
                        "text": ""
                    },
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
            }
        ]
    
    elif user_session and (
        user_message in lista_cancelar or 
        (
            user_session.last_interaction and 
            datetime.utcnow() - user_session.last_interaction > timedelta(hours=1)
        )
    ):
        return cancelar_flujo(number)

    handlers = {
        'awaiting_marca': manejar_paso_marca,
        'awaiting_modelo': manejar_paso_modelo,
        'awaiting_combustible': manejar_paso_combustible,
        'awaiting_año': manejar_paso_anio,
        'awaiting_tipo_repuesto': manejar_paso_tipo_repuesto,
        'awaiting_comentario': manejar_paso_comentario,
        'completed': manejar_paso_finish

    }

    handler = handlers.get(producto.current_step)
    return handler(number, user_message, producto) if handler else [{
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": number,
        "type": "interactive",
        "interactive":{
            "type":"button",
            "body": {
                "text": "⚠️ Flujo no reconocido. Envía '1' para reiniciar. "
            },
            "footer": {
                "text": ""
            },
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

def manejar_paso_marca(number, user_message, producto):
    producto.marca = user_message
    producto.current_step = 'awaiting_modelo'
    actualizar_interaccion(number)
    
    return [
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": number,
            "type": "interactive",
            "interactive":{
                "type":"button",
                "body": {
                    "text": f"✅ Marca: {user_message}\n\n📝Ahora escribe la *LINEA*:\n_(Ej: L200, Hilux, Terracan, Sportage)_ "
                },
                "footer": {
                    "text": ""
                },
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
        }
    ]



def manejar_paso_combustible(number, user_message, producto):

    lista_combustible = ["gasolina", "diesel", "disel", "diésel", "gas", "gas propano"]
    if not user_message.lower() in lista_combustible:

        return [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "interactive",
                "interactive":{
                    "type":"button",
                    "body": {
                        "text": "⚠️ Combustible inválido. Ingresa el combustible.\nEjemplo: Gasolina, Diesel "
                    },
                    "footer": {
                        "text": ""
                    },
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
            }
        ]

    producto.combustible = user_message
    #producto.combustible = "Gasolina" if "gasolina" in user_message.lower() else "Diesel"
    producto.current_step = 'awaiting_año'
    actualizar_interaccion(number)

    return [
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": number,
            "type": "interactive",
            "interactive":{
                "type":"button",
                "body": {
                    "text": f"✅ Marca: {producto.marca}\n✅ Línea: {producto.linea}\n✅ Combustible: {producto.combustible}\n\n📝Escribe el *AÑO* del vehículo:\n_(Ej: 1995, 2000, 2005, 2010, 2018, 2020)_ "
                },
                "footer": {
                    "text": ""
                },
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
        }
    ]


def manejar_paso_anio(number, user_message, producto):
    if not user_message.isdigit() or not (1950 < int(user_message) <= datetime.now().year + 1):

        return [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "interactive",
                "interactive":{
                    "type":"button",
                    "body": {
                        "text": "⚠️ Año inválido. Ingresa un año entre 1950 y actual.\nEjemplo: 1995, 2000, 2005, 2008, 2015, 2020 "
                    },
                    "footer": {
                        "text": ""
                    },
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
            }
        ]

    producto.modelo_anio = user_message
    producto.current_step = 'awaiting_tipo_repuesto'
    actualizar_interaccion(number)

    return [
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": number,
            "type": "interactive",
            "interactive":{
                "type":"button",
                "body": {
                    "text": f"✅ Marca: {producto.marca}\n✅ Línea: {producto.linea}\n✅ Combustible: {producto.combustible}\n✅ Año/Modelo: {producto.modelo_anio}\n\n📝Escribe el *TIPO DE REPUESTO* que necesitas:\n_(Ej: Motor, Culata, Turbo, Cigüeñal)_ "
                },
                "footer": {
                    "text": ""
                },
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
        }
    ]

def manejar_paso_tipo_repuesto(number, user_message, producto):
    producto.tipo_repuesto = user_message
    producto.current_step = 'awaiting_comentario'
    actualizar_interaccion(number)

    return [

        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": number,
            "type": "interactive",
            "interactive":{
                "type":"button",
                "body": {
                    "text": f"✅ Marca: {producto.marca}\n✅ Línea: {producto.linea}\n✅ Combustible: {producto.combustible}\n✅ Año/Modelo: {producto.modelo_anio}\n✅ Tipo de repuesto: {producto.tipo_repuesto}\n\n📝Escribe una *DESCRIPCIÓN O COMENTARIO FINAL*:\n_Si no tienes comentarios escribe *No* o presiona el botón_ "
                },
                "footer": {
                    "text": ""
                },
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "no", "title": "No"}},
                        {"type": "reply", "reply": {"id":"exit", "title":"❌ Cancelar/Salir"}}
                    ]
                }
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
                    "text": f"✅ *Datos registrados:*\n\n• *Marca:* {producto.marca}\n• *Modelo:* {producto.linea}\n• *Combustible:* {producto.combustible}\n• *Año:* {producto.modelo_anio}\n• *Tipo de repuesto:* {producto.tipo_repuesto}\n• *Descripción:* {producto.estado}\n\n"
                },
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "cotizar_si", "title": "✅ Sí, cotizar"}},
                        {"type": "reply", "reply": {"id": "cancelar", "title": "❌ Salir/Cancelar"}}
                    ]
                }
            }
        }
    ]

def manejar_paso_finish(number, user_message, producto):
    producto.current_step = 'finished'
    actualizar_interaccion(number)

    if user_message in lista_cancelar:
        return cancelar_flujo(number)

    if user_message == "cotizar_si":
        session = get_session()
        if session:
            # Eliminar productos asociados
            ProductModel.query.filter_by(session_id=session.idUser).delete()
            #db.session.delete(session)
            db.session.commit()
            actualizar_interaccion(number)

        return [
            {
                "messaging_product": "whatsapp",
                "to": number,
                "type": "text",
                "text": {
                    "body": " Formulario recibido, en unos minutos nos pondremos en contacto"
                }
            },
            generar_list_menu(number)

        ]

def cancelar_flujo(number):
    """Limpia la sesión y productos asociados"""
    session = UserSession.query.filter_by(phone_number=number).first()
    #session = get_session()
    if session:
        # Eliminar productos asociados
        #ProductModel.query.filter_by(session_id=session.idUser).delete()
        ProductModel.query.filter_by(session_id=session.idUser).delete(synchronize_session=False)
        #db.session.delete(session)
        db.session.commit()
        actualizar_interaccion(number)

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

def actualizar_interaccion(number):
    """Actualiza la marca de tiempo de la sesión"""
    session = UserSession.query.filter_by(phone_number=number).first()
    if session:
        session.last_interaction = datetime.utcnow()
        db.session.commit()