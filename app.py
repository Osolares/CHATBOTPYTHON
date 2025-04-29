from typing import TypedDict, Optional, List, Dict, Any, Union
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from config import db, Config
from models import UserSession, Log, ProductModel
from woocommerce_service import WooCommerceService
from datetime import datetime
import json
import time
import http.client
import os
from flask import Flask, request, jsonify, render_template, Blueprint

from flask_sqlalchemy import SQLAlchemy
from formularios import formulario_motor, manejar_paso_actual
from menus import generar_list_menu, generar_menu_principal
from datetime import datetime, timedelta
import logging

# Instancia global del servicio
woo_service = WooCommerceService()

# Configuración de DeepSeek
deepseek_key = os.environ["DEEPSEEK_API_KEY"]
model = ChatOpenAI(
    model="deepseek-chat",
    api_key=deepseek_key,
    base_url="https://api.deepseek.com/v1",
    temperature=0,
    max_tokens=200,
)

# ------------------------------------------
# Definición del Estado y Modelos
# ------------------------------------------

class BotState(TypedDict):
    phone_number: str
    user_msg: str
    session: Optional[UserSession]
    flujo_producto: Optional[ProductModel]
    response_data: List[Dict[str, Any]]
    message_data: Optional[Dict[str, Any]]
    logs: List[str]
    source: str  # NUEVO: whatsapp, telegram, messenger, web, etc

# ------------------------------------------
# Nodos del Grafo para Manejo de Usuarios
# ------------------------------------------

def load_or_create_session(state: BotState) -> BotState:
    """Carga o crea una sesión de usuario, compatible con múltiples fuentes: WhatsApp, Telegram, Messenger, Web"""
    phone_number = state.get("phone_number")
    source = state.get("source")
    message_data = state.get("message_data", {})

    session = None

    with db.session.begin():
        if source == "whatsapp":
            session = db.session.query(UserSession).filter_by(phone_number=phone_number).first()
            if not session:
                session = UserSession(phone_number=phone_number)
                db.session.add(session)
                db.session.flush()

        elif source == "telegram":
            chat_id = message_data.get("chat_id")
            session = db.session.query(UserSession).filter_by(telegram_id=chat_id).first()
            if not session:
                session = UserSession(telegram_id=chat_id)
                db.session.add(session)
                db.session.flush()

        elif source == "messenger":
            messenger_id = message_data.get("recipient", {}).get("id")
            session = db.session.query(UserSession).filter_by(messenger_id=messenger_id).first()
            if not session:
                session = UserSession(messenger_id=messenger_id)
                db.session.add(session)
                db.session.flush()

        elif source == "web":
            email = message_data.get("email")
            session = db.session.query(UserSession).filter_by(email=email).first()
            if not session and email:
                session = UserSession(email=email)
                db.session.add(session)
                db.session.flush()

        if session:
            session.last_interaction = datetime.utcnow()
        
        state["session"] = session

    return state

def load_product_flow(state: BotState) -> BotState:
    """Carga el estado del flujo de producto para el usuario actual"""
    if state["session"]:
        flujo_producto = db.session.query(ProductModel).filter_by(
            session_id=state["session"].idUser
        ).first()
        state["flujo_producto"] = flujo_producto
    return state

def handle_product_flow(state: BotState) -> BotState:
    """Maneja el flujo de producto si existe para el usuario"""
    if state["flujo_producto"]:
        response = manejar_paso_actual(
            state["phone_number"],
            state["user_msg"]
        )
        # FUTURO: Aquí podríamos modificar 'response' si quisiéramos respuestas distintas por source.
        state["response_data"] = response
    return state


def handle_special_commands(state: BotState) -> BotState:
    """Maneja comandos especiales (1-8, 0, hola) para cada usuario, considerando la fuente"""
    texto = state["user_msg"].lower().strip()
    number = state.get("phone_number")
    source = state.get("source")

    # Dependiendo del source, podrías en el futuro mandar menús diferentes.
    if "hola" in texto:
        if source in ["whatsapp", "telegram", "messenger", "web"]:
            state["response_data"] = [
                {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": number,
                    "type": "image",
                    "image": {
                        "link": "https://intermotores.com/wp-content/uploads/2025/04/LOGO_INTERMOTORES.png"
                    }
                },
                {
                    "messaging_product": "whatsapp" if source == "whatsapp" else "other",
                    "recipient_type": "individual",
                    "to": number,
                    "type": "text",
                    "text": {
                        "preview_url": False,
                        "body": "👋 Gracias por comunicarse con nosotros, es un placer atenderle 👨‍💻"
                    }
                }
            ]
    elif texto == "1":
        state["response_data"] = formulario_motor(number)

    elif texto == "2":
        state["response_data"] = manejar_comando_ofertas(number)

    elif texto == "3":
        state["response_data"] = [
            {
                "messaging_product": "whatsapp" if source == "whatsapp" else "other",
                "recipient_type": "individual",
                "to": number,
                "type": "location",
                "location": {
                    "latitude": "14.564777",
                    "longitude": "-90.466011",
                    "name": "Intermotores",
                    "address": "Importadora Internacional de Motores Japoneses, s.a."
                }
            },
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "📍  Estamos ubicados en km 13.5 carretera a El Salvador frente a Plaza Express a un costado de farmacia Galeno, en Intermotores"
                }
            },
            generar_list_menu(number)

        ]

    elif texto == "4":
        state["response_data"] = [
            {
                "messaging_product": "whatsapp" if source == "whatsapp" else "other",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "📅 Horario de Atención:\n\n Lunes a Viernes\n🕜 8:00 am a 5:00 pm\n\nSábado\n🕜 8:00 am a 12:00 pm\n\nDomingo Cerrado 🤓"
                }
            }
        ]

    elif texto == "5":
        state["response_data"] = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "☎*Comunícate con nosotros será un placer atenderte* \n\n 📞 6637-9834 \n\n 📞 6646-6137 \n\n 📱 5510-5350 \n\n 🌐 www.intermotores.com  \n\n 📧 intermotores.ventas@gmail.com \n\n *Facebook* \n Intermotores GT\n\n *Instagram* \n Intermotores GT "}
            },
            generar_list_menu(number)
        ]

    elif texto == "6":
        state["response_data"] = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "image",
                "image": {
                    "link": "https://intermotores.com/wp-content/uploads/2025/04/numeros_de_cuenta_intermotores.jpg"
                }
            }, 
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "*💲Medios de pago:* \n\n 💵 Efectivo. \n\n 🏦 Depósitos o transferencias bancarias. \n\n 📦 Pago contra Entrega. \nPagas al recibir tu producto, aplica para envíos por medio de Guatex, el monto máximo es de Q5,000. \n\n💳 Visa Cuotas. \nHasta 12 cuotas con tu tarjeta visa \n\n💳 Cuotas Credomatic. \nHasta 12 cuotas con tu tarjeta BAC Credomatic \n\n🔗 Neo Link. \nTe enviamos un link para que pagues con tu tarjeta sin salir de casa"}
            },
            generar_list_menu(number)
        ]

    elif texto == "7":
        state["response_data"] = [
            {
                "messaging_product": "whatsapp" if source == "whatsapp" else "other",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "🤝 Gracias por esperar, indique *¿cómo podemos apoyarle?*"
                }
            }
        ]

    elif texto == "8":
        state["response_data"] = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "🏠*Enviamos nuestros productos hasta la puerta de su casa* \n\n 🛵 *Envíos dentro de la capital.* \n Hacemos envíos directos dentro de la ciudad capital, aldea Puerta Parada, Santa Catarina Pinula y sus alrededores \n\n 🚚 *Envío a Departamentos.* \nHacemos envíos a los diferentes departamentos del país por medio de terceros o empresas de transporte como Guatex, Cargo Express, Forza o el de su preferencia. \n\n ⏳📦 *Tiempo de envío.* \nLos pedidos deben hacerse con 24 horas de anticipación y el tiempo de entrega para los envíos directos es de 24 a 48 horas y para los envíos a departamentos depende directamente de la empresa encargarda."}
            },
            generar_list_menu(number)
        ]

    elif texto == "0":
        state["response_data"] = [generar_menu_principal(number)]

    return state


def asistente(state: BotState) -> BotState:
    """Maneja mensajes no reconocidos usando DeepSeek"""
    if not state.get("response_data"):
        user_msg = state["user_msg"]
        response = model.invoke([HumanMessage(content=user_msg)])
        
        body = response.content

        if state["source"] in ["whatsapp", "telegram", "messenger", "web"]:
            state["response_data"] = [{
                "messaging_product": "whatsapp" if state["source"] == "whatsapp" else "other",
                "to": state.get("phone_number") or state.get("email"),
                "type": "text",
                "text": {"body": body}
            }]
    
    return state

def send_messages(state, messages_to_send=None):
    """
    Envía mensajes al usuario según la plataforma y canal.
    Si no se proporcionan mensajes específicos, usa los mensajes en 'response_data'.
    """
    phone_number = state.get("phone_number")
    source = state.get("source", "whatsapp")  # Fuente: whatsapp, telegram, etc.

    # 🔥 Mensajes a enviar
    messages = messages_to_send if messages_to_send else state.get("response_data", [])

    for msg in messages:
        try:
            if source == "whatsapp":
                bot_enviar_mensaje_whatsapp(phone_number, msg)
            elif source == "telegram":
                bot_enviar_mensaje_telegram(phone_number, msg)
            elif source == "messenger":
                bot_enviar_mensaje_messenger(phone_number, msg)
            else:
                agregar_mensajes_log(f"Plataforma desconocida: {source}")
        except Exception as e:
            agregar_mensajes_log(f"Error enviando mensaje a {source}: {str(e)}")


# ------------------------------------------
# Funciones Auxiliares (Mantenidas de tu código original)
# ------------------------------------------

def agregar_mensajes_log(texto: Union[str, dict, list], session_id: Optional[int] = None) -> None:
    """Guarda un mensaje en memoria y en la base de datos."""
    try:
        texto_str = json.dumps(texto, ensure_ascii=False) if isinstance(texto, (dict, list)) else str(texto)
        
        with db.session.begin():
            nuevo_registro = Log(texto=texto_str, session_id=session_id)
            db.session.add(nuevo_registro)
    except Exception as e:
        fallback = f"[ERROR LOG] No se pudo guardar: {str(texto)[:200]}... | Error: {str(e)}"
        try:
            with db.session.begin():
                fallback_registro = Log(texto=fallback, session_id=session_id)
                db.session.add(fallback_registro)
        except Exception as e2:
            pass

def verificar_middleware_usuario(state):
    phone_number = state.get("phone_number")

    usuarios_bloqueados = [
        "50212345678",  # Ejemplo
        "50287654321",
    ]

    if phone_number in usuarios_bloqueados:
        agregar_mensajes_log(f"Usuario bloqueado: {phone_number}")
        return False

    # Horarios
    horarios = {
        "lunes": ("08:00", "17:30"),
        "martes": ("08:00", "17:30"),
        "miércoles": ("08:00", "17:30"),
        "jueves": ("08:00", "17:30"),
        "viernes": ("08:00", "17:30"),
        "sábado": ("08:00", "12:30"),
        "domingo": None,
    }

    ahora = datetime.now()
    dia_actual = ahora.strftime('%A').lower()
    hora_actual = ahora.strftime('%H:%M')

    horario = horarios.get(dia_actual)
    session = UserSession.query.filter_by(phone_number=phone_number).first()

    if not session:
        session = UserSession(phone_number=phone_number)
        db.session.add(session)
        db.session.commit()

    if horario:
        inicio, fin = horario
        if not (inicio <= hora_actual <= fin):
            if not getattr(session, 'fuera_horario_notificado', False):
                bot_enviar_mensaje_whatsapp(phone_number, f"🕔 Hola, estamos fuera de nuestro horario de atención, *Envíanos tu consulta o revisa nuestro menú* ({inicio}-{fin}). Te responderemos lo mas pronto posible.")
                session.fuera_horario_notificado = True
                db.session.commit()
    else:
        if not getattr(session, 'fuera_horario_notificado', False):
            bot_enviar_mensaje_whatsapp(phone_number,f"🕔 Hola, estamos fuera de nuestro horario de atención, *Envíanos tu consulta o revisa nuestro menú* ({inicio}-{fin}). Te responderemos lo mas pronto posible.")
            session.fuera_horario_notificado = True
            db.session.commit()

    return True

def enviar_mensaje_bienvenida(state):
    phone_number = state.get("phone_number")
    ahora = datetime.utcnow()
    tiempo_limite = timedelta(hours=4)

    session = UserSession.query.filter_by(phone_number=phone_number).first()

    if not session:
        session = UserSession(phone_number=phone_number)
        db.session.add(session)
        db.session.commit()
        bot_enviar_mensaje_whatsapp(phone_number, "👋 ¡Bienvenidoa Intermotores! ¿En qué podemos ayudarte hoy?")
        return

    ultima_interaccion = session.last_interaction or ahora
    if ahora - ultima_interaccion > tiempo_limite:
        bot_enviar_mensaje_whatsapp(phone_number, "👋 ¡Hola de nuevo! ¿En qué podemos ayudarte hoy?")

    # Actualizar última interacción
    session.last_interaction = ahora
    session.fuera_horario_notificado = False  # Reiniciar advertencia
    db.session.commit()


def bot_enviar_mensaje_whatsapp(data: Dict[str, Any]) -> Optional[bytes]:
    """Envía un mensaje a WhatsApp"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"{Config.WHATSAPP_TOKEN}"
    }
    
    try:
        connection = http.client.HTTPSConnection("graph.facebook.com")
        json_data = json.dumps(data)
        connection.request("POST", f"/v22.0/{Config.PHONE_NUMBER_ID}/messages", json_data, headers)
        response = connection.getresponse()
        return response.read()
    except Exception as e:
        agregar_mensajes_log(f"Error enviando a WhatsApp: {str(e)}")
        return None
    finally:
        connection.close()

def bot_enviar_mensaje_telegram(data: Dict[str, Any]) -> Optional[bytes]:
    """Envía un mensaje a Telegram"""
    try:
        telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = data.get("chat_id")
        text = data.get("text")
        payload = {
            "chat_id": chat_id,
            "text": text
        }
        headers = {
            "Content-Type": "application/json"
        }
        connection = http.client.HTTPSConnection("api.telegram.org")
        connection.request("POST", f"/bot{telegram_token}/sendMessage", json.dumps(payload), headers)
        response = connection.getresponse()
        return response.read()
    except Exception as e:
        agregar_mensajes_log(f"Error enviando a Telegram: {str(e)}")
        return None
    finally:
        connection.close()

def bot_enviar_mensaje_messenger(data: Dict[str, Any]) -> Optional[bytes]:
    """Envía un mensaje a Messenger"""
    try:
        page_access_token = os.getenv('FACEBOOK_PAGE_ACCESS_TOKEN')
        headers = {
            "Content-Type": "application/json"
        }
        connection = http.client.HTTPSConnection("graph.facebook.com")
        connection.request("POST", f"/v16.0/me/messages?access_token={page_access_token}", json.dumps(data), headers)
        response = connection.getresponse()
        return response.read()
    except Exception as e:
        agregar_mensajes_log(f"Error enviando a Messenger: {str(e)}")
        return None
    finally:
        connection.close()

def bot_enviar_mensaje_web(data: Dict[str, Any]) -> Optional[bytes]:
    """Envía un mensaje a la Web (puedes implementarlo como un correo o notificación interna)"""
    try:
        # Por ahora simulamos que enviamos un correo o notificación
        agregar_mensajes_log(f"Mensaje Web enviado: {json.dumps(data)}")
        return b"ok"
    except Exception as e:
        agregar_mensajes_log(f"Error enviando a Web: {str(e)}")
        return None

def manejar_comando_ofertas(number: str) -> List[Dict[str, Any]]:
    """Procesa el comando de ofertas (versión mejorada para múltiples usuarios)"""
    try:
        productos = woo_service.obtener_ofertas_recientes()
        
        if not isinstance(productos, list):
            productos = []
            agregar_mensajes_log("Error: La respuesta de productos no es una lista")
        
        mensajes = woo_service.formatear_ofertas_whatsapp(productos)
        
        respuesta = [{
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {"body": "📢 *OFERTAS ESPECIALES* 🎁\n\nEstas son nuestras mejores ofertas:"}
        }]
        
        for msg in mensajes:
            if msg and isinstance(msg, str):
                respuesta.append({
                    "messaging_product": "whatsapp",
                    "to": number,
                    "type": "text",
                    "text": {"preview_url": True, "body": msg}
                })

        if len(respuesta) > 1:
            respuesta.append({
                "messaging_product": "whatsapp",
                "to": number,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": "¿Qué deseas hacer ahora?"},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": "1", "title": "🔧 Cotizar repuesto"}},
                            {"type": "reply", "reply": {"id": "0", "title": "🏠 Menú principal"}}
                        ]
                    }
                }
            })
        else:
            respuesta.append({
                "messaging_product": "whatsapp",
                "to": number,
                "type": "text",
                "text": {"body": "⚠️ No hay ofertas disponibles en este momento."}
            })
        
        return respuesta
        
    except Exception as e:
        agregar_mensajes_log(f"Error en manejar_comando_ofertas: {str(e)}")
        return [{
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {"body": "⚠️ Ocurrió un error al cargar las ofertas. Por favor intenta más tarde."}
        }]

# ------------------------------------------
# Construcción del Grafo de Flujo
# ------------------------------------------

workflow = StateGraph(BotState)

# Añadir nodos
workflow.add_node("load_session", load_or_create_session)
workflow.add_node("load_product_flow", load_product_flow)
workflow.add_node("handle_product_flow", handle_product_flow)
workflow.add_node("handle_special_commands", handle_special_commands)
workflow.add_node("asistente", asistente)
workflow.add_node("send_messages", send_messages)

# Definir flujo
workflow.add_edge("load_session", "load_product_flow")
workflow.add_edge("load_product_flow", "handle_product_flow")
workflow.add_edge("handle_product_flow", "handle_special_commands")
workflow.add_edge("handle_special_commands", "asistente")
workflow.add_edge("asistente", "send_messages")
workflow.add_edge("send_messages", END)

workflow.set_entry_point("load_session")

# Compilar el grafo
app_flow = workflow.compile()

# ------------------------------------------
# Configuración de Flask y Rutas
# ------------------------------------------

flask_app = Flask(__name__)
flask_app.config.from_object(Config)
db.init_app(flask_app)

@flask_app.route('/')
def index():
    try:
        registros = Log.query.order_by(Log.fecha_y_hora.desc()).limit(100).all()
    except Exception as e:
        registros = []
        agregar_mensajes_log(f"Error cargando registros: {str(e)}")

    try:
        users = UserSession.query.order_by(UserSession.last_interaction.desc()).all()
    except Exception as e:
        users = []
        agregar_mensajes_log(f"Error cargando usuarios: {str(e)}")

    try:
        products = ProductModel.query.order_by(ProductModel.session_id.desc()).all()
    except Exception as e:
        products = []
        agregar_mensajes_log(f"Error cargando productos: {str(e)}")

    return render_template('index.html', registros=registros, users=users, products=products)


# webhook dentro de app.py o donde antes lo tenías

from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from config import Config, db, migrate
from app_flow import app_flow  # Tu flujo normal
from send_messages import send_messages  # Función corregida
from utils import (
    is_human_message,
    verificar_middleware_usuario,
    enviar_mensaje_bienvenida,
    verificar_fuera_horario,
    handle_special_commands,
)
import logging

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
migrate.init_app(app, db)

# --- AQUÍ EL WEBHOOK SIN BLUEPRINT ---

@app.route('/webhook', methods=['GET', 'POST'])
def webhook_whatsapp():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode == 'subscribe' and token == 'TOKEN_WEBHOOK_WHATSAPP':  # Asegúrate que el token sea correcto
            return challenge, 200
        else:
            return 'Error de verificación', 403

    if request.method == 'POST':
        try:
            data = request.get_json()
            logging.info(data)  # Opcional para debug

            # ✅ Procesar mensajes
            entry = data.get('entry', [])[0]
            changes = entry.get('changes', [])[0]
            value = changes.get('value', {})
            messages = value.get('messages')

            if not messages:
                return jsonify({'message': 'EVENT_RECEIVED'})  # Si no hay mensajes, terminar

            message = messages[0]
            phone_number = message['from']
            text = message['text']['body'] if message['type'] == 'text' else ''
            current_time = datetime.utcnow()

            initial_state = {
                'source': 'whatsapp',
                'user_id': phone_number,
                'phone_number': phone_number,
                'message': text,
                'current_time': current_time,
                'metadata': value.get('metadata', {}),
            }

            # ✅ Verificar si el mensaje es de humano
            if not is_human_message(message):
                return jsonify({'message': 'EVENT_RECEIVED'})

            # ✅ Middleware usuarios bloqueados
            if not verificar_middleware_usuario(initial_state):
                return jsonify({'message': 'EVENT_RECEIVED'})

            # ✅ Mensaje de bienvenida (si aplica)
            enviar_mensaje_bienvenida(initial_state)

            # ✅ Mensaje fuera de horario (solo una vez)
            verificar_fuera_horario(initial_state)

            # ✅ Comandos especiales
            special_response = handle_special_commands(initial_state)
            if special_response:
                send_messages(initial_state, special_response)
                return jsonify({'message': 'EVENT_RECEIVED'})

            # ✅ Flujo normal
            app_flow.invoke(initial_state)

            return jsonify({'message': 'EVENT_RECEIVED'})

        except Exception as e:
            logging.error(f"Error en webhook_whatsapp: {e}")
            return jsonify({'error': str(e)}), 500

# --- FIN DEL WEBHOOK NORMAL ---

@flask_app.route('/webhook/telegram', methods=['POST'])
def webhook_telegram():
    try:
        data = request.get_json()
        agregar_mensajes_log(data)

        message = data.get("message", {})
        chat = message.get("chat", {})
        phone_number = None  # En Telegram puro no se obtiene el número directamente
        chat_id = chat.get("id")
        text = message.get("text", "")

        initial_state = {
            "phone_number": "",  # En Telegram puro no tienes el número
            "user_msg": text,
            "response_data": [],
            "message_data": {"chat_id": chat_id},
            "logs": [],
            "source": "telegram"
        }
        
        app_flow.invoke(initial_state)
        
        return jsonify({'message': 'EVENT_RECEIVED'})
    
    except Exception as e:
        agregar_mensajes_log(f"Error en webhook_telegram: {str(e)}")
        return jsonify({'message': 'EVENT_RECEIVED'}), 500

@flask_app.route('/webhook/messenger', methods=['POST'])
def webhook_messenger():
    try:
        data = request.get_json()
        agregar_mensajes_log(data)

        entry = data['entry'][0]
        messaging = entry.get('messaging', [])[0]
        sender_id = messaging['sender']['id']
        text = messaging['message']['text']

        initial_state = {
            "phone_number": "",  # No hay teléfono en Messenger
            "user_msg": text,
            "response_data": [],
            "message_data": {"recipient": {"id": sender_id}},
            "logs": [],
            "source": "messenger"
        }
        
        app_flow.invoke(initial_state)
        
        return jsonify({'message': 'EVENT_RECEIVED'})
    
    except Exception as e:
        agregar_mensajes_log(f"Error en webhook_messenger: {str(e)}")
        return jsonify({'message': 'EVENT_RECEIVED'}), 500

@flask_app.route('/webhook/web', methods=['POST'])
def webhook_web():
    try:
        data = request.get_json()
        agregar_mensajes_log(data)

        email = data.get("email")
        text = data.get("message", "")

        initial_state = {
            "phone_number": "", 
            "user_msg": text,
            "response_data": [],
            "message_data": {"email": email},
            "logs": [],
            "source": "web"
        }
        
        app_flow.invoke(initial_state)
        
        return jsonify({'message': 'EVENT_RECEIVED'})
    
    except Exception as e:
        agregar_mensajes_log(f"Error en webhook_web: {str(e)}")
        return jsonify({'message': 'EVENT_RECEIVED'}), 500

def is_human_message(message):
    """
    Detecta si el mensaje recibido es de un humano real.
    Solo procesa mensajes de tipo "text" o "interactive".
    """
    valid_types = ["text", "interactive"]
    message_type = message.get("type")
    return message_type in valid_types


def verificar_token_whatsapp(req):
    """Verificación del token de WhatsApp"""
    token = req.args.get('hub.verify_token')
    challenge = req.args.get('hub.challenge')

    if challenge and token == Config.TOKEN_WEBHOOK_WHATSAPP:
        return challenge
    else:
        return jsonify({'error': 'Token Invalido'}), 401

# ------------------------------------------
# Inicialización
# ------------------------------------------

with flask_app.app_context():
    db.create_all()

if __name__ == '__main__':
    flask_app.run(host='0.0.0.0', port=80, debug=True)