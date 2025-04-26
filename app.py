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

# ------------------------------------------
# Nodos del Grafo para Manejo de Usuarios
# ------------------------------------------

def load_or_create_session(state: BotState) -> BotState:
    """Carga o crea una sesión de usuario, compatible con múltiples usuarios"""
    phone_number = state["phone_number"]
    
    with db.session.begin():
        session = db.session.query(UserSession).filter_by(phone_number=phone_number).first()
        
        if not session:
            session = UserSession(phone_number=phone_number)
            db.session.add(session)
            db.session.flush()  # Para obtener el ID si es necesario
        
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
        state["response_data"] = response
    return state

def handle_special_commands(state: BotState) -> BotState:
    """Maneja comandos especiales (1-8, 0, hola) para cada usuario"""
    texto = state["user_msg"].lower().strip()
    number = state["phone_number"]
    
    if "hola" in texto:
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
            },
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
                    "body": "📍 Estamos ubicados en km 13.5 carretera a El Salvador frente a Plaza Express a un costado de farmacia Galeno, en Intermotores"
                }
            },
            generar_list_menu(number)
        ]

    elif texto == "4":
        state["response_data"] = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "📅 Horario de Atención: \n\n Lunes a Viernes. \n🕜 Horario : 8:00 am a 5:00 pm \n\n Sábado. \n🕜 Horario : 8:00 am a 12:00 pm \n\n Domingo. Cerrado 🤓"
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
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "🤝 Gracias por esperar es un placer atenderle, indíquenos *¿cómo podemos apoyarle?* pronto será atendido por nuestro personal de atención al cliente. 🤵‍♂"
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
    """Maneja mensajes no reconocidos usando DeepSeek para cada usuario"""
    if not state.get("response_data"):
        user_msg = state["user_msg"]
        response = model.invoke([HumanMessage(content=user_msg)])
        
        state["response_data"] = [{
            "messaging_product": "whatsapp",
            "to": state["phone_number"],
            "type": "text",
            "text": {"body": response.content}
        }]
    
    return state

def send_messages(state: BotState) -> BotState:
    """Envía mensajes a WhatsApp con manejo seguro para múltiples usuarios"""
    for mensaje in state["response_data"]:
        try:
            bot_enviar_mensaje_whatsapp(mensaje)
            agregar_mensajes_log(
                json.dumps(mensaje), 
                state["session"].idUser if state["session"] else None
            )
            time.sleep(1)
        except Exception as e:
            agregar_mensajes_log(
                f"Error enviando mensaje a {state['phone_number']}: {str(e)}",
                state["session"].idUser if state["session"] else None
            )
    return state

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

def bot_enviar_mensaje_whatsapp(data: Dict[str, Any]) -> Optional[bytes]:
    """Envía un mensaje a WhatsApp con manejo de errores"""
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

@flask_app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        challenge = verificar_token_whatsapp(request)
        return challenge
    
    try:
        data = request.get_json()
        agregar_mensajes_log(data)

        entry = data['entry'][0]
        changes = entry.get('changes', [])[0]
        value = changes.get('value', {})
        messages_list = value.get('messages', [])

        if messages_list:
            message = messages_list[0]
            phone_number = message.get("from")
            
            # Determinar el texto del mensaje
            if message.get("type") == "interactive":
                interactive = message.get("interactive", {})
                if interactive.get("type") == "button_reply":
                    text = interactive.get("button_reply", {}).get("id")
                elif interactive.get("type") == "list_reply":
                    text = interactive.get("list_reply", {}).get("id")
                else:
                    text = ""
            elif message.get("type") == "text":
                text = message.get("text", {}).get("body", "")
            else:
                text = ""

            # Ejecutar el flujo para este usuario
            initial_state = {
                "phone_number": phone_number,
                "user_msg": text,
                "response_data": [],
                "message_data": message,
                "logs": []
            }
            
            app_flow.invoke(initial_state)
            
        return jsonify({'message': 'EVENT_RECEIVED'})
    
    except Exception as e:
        agregar_mensajes_log(f"Error en webhook: {str(e)}")
        return jsonify({'message': 'EVENT_RECEIVED'}), 500

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