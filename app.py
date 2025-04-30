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
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from formularios import formulario_motor, manejar_paso_actual
from menus import generar_list_menu, generar_menu_principal
from datetime import datetime, timedelta
from pytz import timezone
from config import GUATEMALA_TZ
from utils.timezone import now


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
#from datetime import datetime, time, timedelta
#from typing import Optional
#from config import db
#from models import UserSession
#
#GUATEMALA_TZ = timezone('America/Guatemala')
#
#def now():
#    return datetime.now(GUATEMALA_TZ)
def block(source, to_compare):
    # --- BLOQUEO DE USUARIOS ---
    BLOQUEADOS = {
        "whatsapp": ["502123456", "50233334444"],
        "telegram": ["123456789"],
        "web": ["correo@ejemplo.com"]
    }


    if to_compare in BLOQUEADOS.get(source, []):
        # Para usuarios bloqueados SI interrumpimos el flujo
        error_msg = f"❌ Error Usuario bloqueado"
        agregar_mensajes_log(error_msg)
        return {"status": "blocked", "message": error_msg}
    
    return {"status": "success"}

def pre_validaciones(state: BotState) -> BotState:
    """
    Middleware que valida:
    - Usuarios bloqueados
    - Horario de atención (zona horaria de Guatemala)
    - Bienvenida con control de frecuencia
    
    Ahora solo agrega mensajes adicionales sin interrumpir el flujo
    """
    ahora = now()
    session = state.get("session")
    phone_or_id = state.get("phone_number") or state["message_data"].get("email")
    source = state.get("source")

    # --- BLOQUEO DE USUARIOS ---
    #BLOQUEADOS = {
    #    "whatsapp": ["502123456", "50233334444"],
    #    "telegram": ["123456789"],
    #    "web": ["correo@ejemplo.com"]
    #}
#
    #if phone_or_id in BLOQUEADOS.get(source, []):
    #    # Para usuarios bloqueados SI interrumpimos el flujo
    #    state["response_data"] = [{
    #        "messaging_product": "whatsapp" if source == "whatsapp" else "other",
    #        "to": phone_or_id,
    #        "type": "text",
    #        "text": {
    #            "body": "⚠️ Este canal no está habilitado para usted. Gracias por su comprensión."
    #        }
    #    }]
    #    state["skip_processing"] = True  # Nueva bandera para saltar procesamiento
    #    return state

    # --- HORARIO DE ATENCIÓN ---
    HORARIO = {
        0: ("08:00", "17:00"),  # Lunes
        1: ("08:00", "17:00"),
        2: ("08:00", "17:00"),
        3: ("08:00", "17:00"),
        4: ("08:00", "17:00"),
        5: ("08:00", "12:00"),
        6: (None, None)         # Domingo cerrado
    }

    dia = ahora.weekday()
    h_ini_str, h_fin_str = HORARIO.get(dia, (None, None))
    dentro_horario = False

    if h_ini_str and h_fin_str:
        h_ini = datetime.strptime(h_ini_str, "%H:%M").time()
        h_fin = datetime.strptime(h_fin_str, "%H:%M").time()
        dentro_horario = h_ini <= ahora.time() <= h_fin

    if not dentro_horario:
        mostrar_alerta = False
        
        # Solo mostrar alerta si pasó más de 1 hora desde la última
        if session:
            ultima_alerta = session.ultima_alerta_horario or datetime.min.replace(tzinfo=GUATEMALA_TZ)
            if ahora - ultima_alerta > timedelta(hours=1):
                mostrar_alerta = True
                session.ultima_alerta_horario = ahora
                db.session.commit()
        else:
            mostrar_alerta = True

        if mostrar_alerta:
            state.setdefault("additional_messages", []).append({
                "messaging_product": "whatsapp" if source == "whatsapp" else "other",
                "to": phone_or_id,
                "type": "text",
                "text": {
                    "body": "🕒 En este momento estamos fuera de nuestro horario de atención.\n"
                            "Nuestro equipo le responderá en el siguiente horario disponible.\n\n"
                            "Puede continuar usando el asistente automático mientras tanto."
                }
            })

    # --- BIENVENIDA CONTROLADA ---
    if session:
        # Solo mostrar bienvenida si es la primera vez o si pasó más de 24h desde la última interacción
        if not session.mostro_bienvenida or (ahora - session.last_interaction > timedelta(hours=24)):
            state.setdefault("additional_messages", []).append({
                "messaging_product": "whatsapp" if source == "whatsapp" else "other",
                "to": phone_or_id,
                "type": "text",
                "text": {
                    "body": "👋 ¡Bienvenido(a) a Intermotores! Estamos aquí para ayudarte a encontrar el repuesto ideal. 🚗"
                }
            })
            session.mostro_bienvenida = True
            db.session.commit()
    else:
        # Si no hay sesión, mostrar bienvenida mínima
        state.setdefault("additional_messages", []).append({
            "messaging_product": "whatsapp" if source == "whatsapp" else "other",
            "to": phone_or_id,
            "type": "text",
            "text": {
                "body": "👋 ¡Gracias por contactar a Intermotores!"
            }
        })

    return state

#def load_or_create_session(state: BotState) -> BotState:
#    """Carga o crea una sesión de usuario, compatible con múltiples fuentes: WhatsApp, Telegram, Messenger, Web"""
#    phone_number = state.get("phone_number")
#    source = state.get("source")
#    message_data = state.get("message_data", {})
#
#    session = None
#
#    with db.session.begin():
#        if source == "whatsapp":
#            session = db.session.query(UserSession).filter_by(phone_number=phone_number).first()
#            if not session:
#                session = UserSession(phone_number=phone_number)
#                db.session.add(session)
#                db.session.flush()
#
#        elif source == "telegram":
#            chat_id = message_data.get("chat_id")
#            session = db.session.query(UserSession).filter_by(telegram_id=chat_id).first()
#            if not session:
#                session = UserSession(telegram_id=chat_id)
#                db.session.add(session)
#                db.session.flush()
#
#        elif source == "messenger":
#            messenger_id = message_data.get("recipient", {}).get("id")
#            session = db.session.query(UserSession).filter_by(messenger_id=messenger_id).first()
#            if not session:
#                session = UserSession(messenger_id=messenger_id)
#                db.session.add(session)
#                db.session.flush()
#
#        elif source == "web":
#            email = message_data.get("email")
#            session = db.session.query(UserSession).filter_by(email=email).first()
#            if not session and email:
#                session = UserSession(email=email)
#                db.session.add(session)
#                db.session.flush()
#
#        if session:
#            session.last_interaction =now()
#        
#        state["session"] = session
#
#    return state

def load_or_create_session(state: BotState) -> BotState:
    """Carga o crea una sesión de usuario"""
    try:
        phone_number = state.get("phone_number")
        source = state.get("source")
        message_data = state.get("message_data", {})

        with db.session.begin():
            if source == "whatsapp":
                session = db.session.query(UserSession).filter_by(phone_number=phone_number).first()
                if not session:
                    session = UserSession(
                        phone_number=phone_number,
                        #created_at=now(),
                        last_interaction=now(),
                        source=source
                    )
                    db.session.add(session)
                
                # Actualizar siempre la última interacción
                session.last_interaction = now()
                session.source = source
                db.session.commit()

            state["session"] = session
            return state
            
    except Exception as e:
        agregar_mensajes_log(f"Error en load_or_create_session: {str(e)}")
        # Crear estado mínimo si falla
        state["session"] = None
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
                    "messaging_product": "whatsapp",
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
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "location",
                "location": {
                    "latitude": "14.564777",
                    "longitude": "-90.466011",
                    "name": "Intermotores",  # Nombre sin formato (texto plano)
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
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "*💲Medios de pago:* \n\n 💵 Efectivo. \n\n 🏦 Depósitos o transferencias bancarias. \n\n 📦 Pago contra Entrega. \nPagas al recibir tu producto, aplica para envíos por medio de Guatex, el monto máximo es de Q5,000. \n\n💳 Visa Cuotas. \nHasta 12 cuotas con tu tarjeta visa \n\n💳 Cuotas Credomatic. \nHasta 12 cuotas con tu tarjeta BAC Credomatic \n\n🔗 Neo Link. \nTe enviamos un link para que pagues con tu tarjeta sin salir de casa"}
            },
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "image",
                "image": {
                    "link": "https://intermotores.com/wp-content/uploads/2025/04/numeros_de_cuenta_intermotores.jpg"
                }
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
        last_log = db.session.query(Log).filter(
            Log.session_id == (state["session"].idUser if state["session"] else None)
        ).order_by(Log.fecha_y_hora.desc()).first()

        if last_log and user_msg in (last_log.texto or ""):
            agregar_mensajes_log("🔁 Mensaje duplicado detectado, ignorando respuesta asistente", state["session"].idUser if state["session"] else None)
            return state

        # Llama DeepSeek solo si no es duplicado

        response = model.invoke([HumanMessage(content=f"Responde en maximo 15 palabras de forma muy directa, concisa y resumida: {user_msg}")])
        body = response.content

        if state["source"] in ["whatsapp", "telegram", "messenger", "web"]:
            state["response_data"] = [{
                "messaging_product": "whatsapp" if state["source"] == "whatsapp" else "other",
                "to": state.get("phone_number") or state.get("email"),
                "type": "text",
                "text": {"body": body}
            }]

    return state

def send_messages(state: BotState) -> BotState:
    """Envía mensajes al canal correcto según la fuente."""
    messages = state.get("response_data", [])
    
    if not messages:
        return state
    
    for mensaje in messages:
        try:
            #agregar_mensajes_log(json.dumps(mensaje), state["session"].idUser if state["session"] else None)
            if state["source"] == "whatsapp":
                bot_enviar_mensaje_whatsapp(mensaje)
            elif state["source"] == "telegram":
                bot_enviar_mensaje_telegram(mensaje)
            elif state["source"] == "messenger":
                bot_enviar_mensaje_messenger(mensaje)
            elif state["source"] == "web":
                bot_enviar_mensaje_web(mensaje)

            agregar_mensajes_log(json.dumps(mensaje), state["session"].idUser if state["session"] else None)
            time.sleep(1)
        except Exception as e:
            agregar_mensajes_log(f"Error enviando mensaje ({state['source']}): {str(e)}",
                               state["session"].idUser if state["session"] else None)
    return state
# ------------------------------------------
# Funciones Auxiliares (Mantenidas de tu código original)
# ------------------------------------------

def merge_responses(state: BotState) -> BotState:
    """
    Combina los mensajes adicionales del middleware con las respuestas normales.
    Los mensajes adicionales van primero.
    """
    additional = state.pop("additional_messages", [])
    main_responses = state.get("response_data", [])
    
    state["response_data"] = additional + main_responses
    return state

def is_human_message(platform: str, message_data: dict) -> bool:
    """
    Verifica si un mensaje es válido para procesar en cualquier plataforma.
    
    Args:
        platform: "whatsapp", "telegram", "messenger", "web"
        message_data: Datos crudos del mensaje recibido
        
    Returns:
        bool: True si es un mensaje válido de humano, False si es un evento del sistema
    """
    try:
        if platform == "whatsapp":
            # WhatsApp Business API structure
            message = message_data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("messages", [{}])[0]
            if not message.get("from"):
                return False
                
            message_type = message.get("type")
            valid_types = ["text", "interactive"]
            return message_type in valid_types
            
        elif platform == "telegram":
            # Telegram webhook structure
            if "message" not in message_data:
                return False
                
            message = message_data["message"]
            return "text" in message or "data" in message  # Mensajes o callback queries
            
        elif platform == "messenger":
            # Messenger webhook structure
            entry = message_data.get("entry", [{}])[0]
            messaging = entry.get("messaging", [{}])[0]
            return "message" in messaging and "text" in messaging["message"]
            
        elif platform == "web":
            # Estructura para web (formularios, chat web)
            return bool(message_data.get("message")) and bool(message_data.get("email"))
            
        return False
        
    except Exception as e:
        agregar_mensajes_log(f"Error en is_human_message: {str(e)}")
        return False


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

# --- 1. Nodos ---
workflow.add_node("load_session", load_or_create_session)
workflow.add_node("pre_validaciones", pre_validaciones)
workflow.add_node("load_product_flow", load_product_flow)
workflow.add_node("handle_product_flow", handle_product_flow)
workflow.add_node("handle_special_commands", handle_special_commands)
workflow.add_node("asistente", asistente)
workflow.add_node("send_messages", send_messages)
workflow.add_node("merge_responses", merge_responses)  # Nuevo nodo

# --- 2. Enlaces (Edges) ---
workflow.add_edge("load_session", "pre_validaciones")
workflow.add_edge("pre_validaciones", "load_product_flow")
workflow.add_edge("load_product_flow", "handle_product_flow")
workflow.add_edge("handle_product_flow", "handle_special_commands")

# Condicional entre comandos y asistente
def enrutar_despues_comandos(state: BotState) -> str:
    if state.get("skip_processing", False):
        return "send_messages"
    if state.get("response_data"):
        return "send_messages"
    return "asistente"

workflow.add_conditional_edges("handle_special_commands", enrutar_despues_comandos)
workflow.add_edge("asistente", "merge_responses")
workflow.add_edge("merge_responses", "send_messages")
workflow.add_edge("send_messages", END)

# --- Configurar punto de entrada
workflow.set_entry_point("load_session")

# --- Compilar
app_flow = workflow.compile()# ------------------------------------------
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


#from message_validator import MessageValidator


#Token de verificacion para la configuracion
TOKEN_WEBHOOK_WHATSAPP = f"{Config.TOKEN_WEBHOOK_WHATSAPP}"

@flask_app.route('/webhook', methods=['GET','POST'])
def webhook():
    if request.method == 'GET':
        challenge = verificar_token_whatsapp(request)
        return challenge
    elif request.method == 'POST':
        response = recibir_mensajes(request)
        return response

def verificar_token_whatsapp(req):
    token = req.args.get('hub.verify_token')
    challenge = req.args.get('hub.challenge')

    if challenge and token == TOKEN_WEBHOOK_WHATSAPP:
        return challenge
    else:
        return jsonify({'error':'Token Invalido'}),401

def recibir_mensajes(req):
    try:
        data = request.get_json()

        try:
            #agregar_mensajes_log(json.dumps(data, ensure_ascii=False))
            # Guardar el evento recibido
            agregar_mensajes_log(f"📥 Entrada cruda WhatsApp: {json.dumps(data)}")

        except TypeError as e:
            agregar_mensajes_log(f"[Log ignorado] No se pudo serializar data: {str(e)}")

        if not data or 'entry' not in data:
            agregar_mensajes_log("Error: JSON sin 'entry' o 'Data'")
            return jsonify({'message': 'EVENT_RECEIVED'})

        # Guardar el evento recibido
        #agregar_mensajes_log(f"📥 Entrada cruda WhatsApp: {json.dumps(data)}")

        # Filtro inicial: solo humanos
        #if not is_human_message("whatsapp", data):
        #    agregar_mensajes_log("🚫 Evento ignorado: no es mensaje humano", None)
        #    return jsonify({'status': 'ignored', 'reason': 'non_human_event'})
        
        ## Versión más limpia (opcional)
        #if not is_human_message("whatsapp", data):
        #    # Puedes comentar esto si no quieres ni siquiera registrar eventos no humanos
        #    # agregar_mensajes_log("🚫 Evento ignorado: no es mensaje humano", None)
        #    return jsonify({'status': 'ignored'})
#
        ## Validación de estructura
        #validation = MessageValidator.validate("whatsapp", data)
#
        #if not validation["is_valid"]:
        #    agregar_mensajes_log("🚫 Mensaje inválido detectado en webhook", None)
        #    return jsonify({'status': 'ignored', 'reason': 'invalid_message'})


        entry = data['entry'][0]
        changes = entry.get('changes', [])[0]
        value = changes.get('value', {})
        messages_list = value.get('messages', [])

#        if messages_list:
#            message = messages_list[0]
#            phone_number = message.get("from")
#
#            block("whatsapp", phone_number)

        if messages_list:
            message = messages_list[0]
            phone_number = message.get("from")
            
            # Verificar si el usuario está bloqueado
            block_result = block("whatsapp", phone_number)
            if block_result.get("status") == "blocked":
                agregar_mensajes_log(f"Usuario bloqueado intentó contactar: {phone_number}")
                return jsonify({'status': 'blocked', 'message': 'Usuario bloqueado'}), 403

            #session = load_or_create_session(phone_number)
            #if not session:
            #    session = load_or_create_session(phone_number)

            ## Guardar log
            #try:
            #    agregar_mensajes_log(json.dumps(message, ensure_ascii=False))
            #except TypeError as e:
            #    agregar_mensajes_log(f"[Log ignorado] No se pudo serializar message: {str(e)}")

            # Crea estado inicial
            initial_state = {
                "phone_number":phone_number,
                "user_msg": message,
                "response_data": [],
                "message_data": message,
                "logs": [],
                "source": "whatsapp"
            }
            agregar_mensajes_log(f"📥 Initial State: {json.dumps(initial_state)}")

            msg_type = message.get("type")

            if msg_type == "interactive":
                interactive = message.get("interactive", {})
                tipo_interactivo = interactive.get("type")

                if tipo_interactivo == "button_reply":
                    text = interactive.get("button_reply", {}).get("id")
                    if text:
                        # Actualizamos el user_msg en el estado con el texto del botón
                        initial_state["user_msg"] = text
                        #enviar_mensajes_whatsapp(text, phone_number)

                elif tipo_interactivo == "list_reply":
                    text = interactive.get("list_reply", {}).get("id")
                    if text:
                        # Actualizamos el user_msg en el estado con el texto del botón
                        initial_state["user_msg"] = text
                        #enviar_mensajes_whatsapp(text, phone_number)

            elif msg_type == "text":
                text = message.get("text", {}).get("body")
                if text:
                    # Actualizamos el user_msg en el estado con el texto del botón
                    initial_state["user_msg"] = text
                    #enviar_mensajes_whatsapp(text, phone_number)

            agregar_mensajes_log(f"📥 Mensaje a enviar: {json.dumps(initial_state)}")

            # Ejecuta el flujo
            app_flow.invoke(initial_state)

            return jsonify({'status': 'processed'})
        
        else:
            return jsonify({'status': 'ignored', 'reason': 'no_messages'}), 200

        #return jsonify({'message': 'EVENT_RECEIVED'})

    #except Exception as e:
    #    agregar_mensajes_log(f"Error en recibir_mensajes: {str(e)}")
    #    return jsonify({'message': 'EVENT_RECEIVED'})

    except Exception as e:
        error_msg = f"❌ Error procesando webhook WhatsApp: {str(e)}"
        agregar_mensajes_log(error_msg)
        return jsonify({'status': 'error', 'message': error_msg}), 500


@flask_app.route('/webhook/telegram', methods=['POST'])
def webhook_telegram():
    """Endpoint para Telegram."""
    try:
        data = request.get_json()
        validation = MessageValidator.validate("telegram", data)
        
        if not validation["is_valid"]:
            return jsonify({'status': 'ignored', 'reason': 'invalid_message'})
        
        initial_state = {
            "phone_number": validation["user_id"],
            "user_msg": validation["message_content"],
            "response_data": [],
            "message_data": {"chat_id": validation["user_id"]},
            "logs": [],
            "source": "telegram"
        }
        
        app_flow.invoke(initial_state)
        return jsonify({'status': 'processed'})
        
    except Exception as e:
        error_msg = f"Telegram webhook error: {str(e)}"
        agregar_mensajes_log(error_msg)
        return jsonify({'status': 'error', 'message': error_msg}), 500

@flask_app.route('/webhook/messenger', methods=['POST'])
def webhook_messenger():
    """Endpoint para Facebook Messenger."""
    try:
        data = request.get_json()
        validation = MessageValidator.validate("messenger", data)
        
        if not validation["is_valid"]:
            return jsonify({'status': 'ignored', 'reason': 'invalid_message'})
        
        initial_state = {
            "phone_number": "",  # Messenger usa ID, no teléfono
            "user_msg": validation["message_content"],
            "response_data": [],
            "message_data": {"recipient": {"id": validation["user_id"]}},
            "logs": [],
            "source": "messenger"
        }
        
        app_flow.invoke(initial_state)
        return jsonify({'status': 'processed'})
        
    except Exception as e:
        error_msg = f"Messenger webhook error: {str(e)}"
        agregar_mensajes_log(error_msg)
        return jsonify({'status': 'error', 'message': error_msg}), 500

@flask_app.route('/webhook/web', methods=['POST'])
def webhook_web():
    """Endpoint para chat web."""
    try:
        data = request.get_json()
        validation = MessageValidator.validate("web", data)
        
        if not validation["is_valid"]:
            return jsonify({'status': 'ignored', 'reason': 'invalid_message'})
        
        initial_state = {
            "phone_number": "",  # Web usa email
            "user_msg": validation["message_content"],
            "response_data": [],
            "message_data": {"email": validation["user_id"]},
            "logs": [],
            "source": "web"
        }
        
        app_flow.invoke(initial_state)
        return jsonify({'status': 'processed'})
        
    except Exception as e:
        error_msg = f"Web webhook error: {str(e)}"
        agregar_mensajes_log(error_msg)
        return jsonify({'status': 'error', 'message': error_msg}), 500

#def verificar_token_whatsapp(req):
#    """Verificación del token de WhatsApp"""
#    token = req.args.get('hub.verify_token')
#    challenge = req.args.get('hub.challenge')
#
#    if challenge and token == Config.TOKEN_WEBHOOK_WHATSAPP:
#        return challenge
#    else:
#        return jsonify({'error': 'Token Invalido'}), 401

def enrutar_despues_comandos(state: BotState) -> str:
    """
    Decide a dónde ir después de procesar comandos especiales:
    - Si ya hay respuesta en state["response_data"], saltar asistente y enviar directamente.
    - Si no, pasar al asistente.
    """
    if state.get("response_data"):
        return "send_messages"
    return "asistente"

# ------------------------------------------
# Inicialización
# ------------------------------------------

with flask_app.app_context():
    db.create_all()

if __name__ == '__main__':
    flask_app.run(host='0.0.0.0', port=80, debug=True)