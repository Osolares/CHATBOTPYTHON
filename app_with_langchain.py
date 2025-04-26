from flask import Flask, request, jsonify, render_template, current_app
from config import db, migrate, Config
from models import UserSession, Log, ProductModel
from formularios import formulario_motor, manejar_paso_actual
from session_manager import load_or_create_session, get_session
from menus import generar_list_menu, generar_menu_principal
from woocommerce_service import WooCommerceService
from datetime import datetime
import http.client
import json
import time
import os

# LangChain imports
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain.memory import ConversationBufferMemory
from langchain_community.llms import OpenAI
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from langchain.agents import Tool, AgentExecutor, LLMSingleActionAgent, AgentOutputParser
from langchain.prompts import StringPromptTemplate
from typing import List, Union

# Instancia global del servicio
woo_service = WooCommerceService()

# Configuración de LangChain
def setup_langchain():
    # Plantilla para el asistente
    prompt_template = """
    Eres un asistente virtual de Intermotores, especializado en la venta de motores y repuestos automotrices.
    Tu función es ayudar a los clientes con cotizaciones, información de productos, horarios, ubicación y formas de pago.
    
    Historial de conversación:
    {chat_history}
    
    Mensaje del usuario: {user_input}
    Respuesta del asistente:
    """
    
    prompt = PromptTemplate(
        input_variables=["chat_history", "user_input"],
        template=prompt_template
    )
    
    # Configuración de memoria para mantener el contexto
    memory = ConversationBufferMemory(memory_key="chat_history")
    
    # Configuración del LLM (puedes cambiar el modelo según necesidades)
    llm = OpenAI(temperature=0.7)
    
    # Creación de la cadena de conversación
    conversation_chain = LLMChain(
        llm=llm,
        prompt=prompt,
        verbose=True,
        memory=memory
    )
    
    return conversation_chain

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Inicialización segura
    db.init_app(app)
    migrate.init_app(app, db)
    
    with app.app_context():
        db.create_all()
        # Configura LangChain al iniciar la aplicación
        app.conversation_chain = setup_langchain()
    
    return app

def asistente(user_msg):
    """Función del asistente que utiliza LangChain para generar respuestas"""
    try:
        # Obtener la cadena de conversación del contexto de la aplicación
        chain = current_app.conversation_chain
        
        # Ejecutar la cadena con el mensaje del usuario
        response = chain.run(user_input=user_msg)
        
        # Formatear la respuesta para WhatsApp
        whatsapp_response = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "type": "text",
            "text": {
                "preview_url": False,
                "body": response
            }
        }
        
        return whatsapp_response
        
    except Exception as e:
        # En caso de error, devolver un mensaje predeterminado
        error_msg = f"Error en el asistente: {str(e)}"
        agregar_mensajes_log(error_msg)
        
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "type": "text",
            "text": {
                "preview_url": False,
                "body": "Disculpa, estoy teniendo dificultades para procesar tu solicitud. Por favor intenta nuevamente o selecciona una opción del menú."
            }
        }

app = create_app()

# ------------------------------------------
# Funciones auxiliares (se mantienen igual que en el original)
# ------------------------------------------

@app.route('/')
def index():
    try:
        registros = Log.query.order_by(Log.fecha_y_hora.desc()).limit(100).all()
    except Exception as e:
        registros = []
        agregar_mensajes_log(f"Error cargando registros: {json.dumps(str(e))}")

    try:
        users = UserSession.query.order_by(UserSession.last_interaction.desc()).all()
    except Exception as e:
        users = []
        agregar_mensajes_log(f"Error cargando usuarios: {json.dumps(str(e))}")

    try:
        products = ProductModel.query.order_by(ProductModel.session_id.desc()).all()
    except Exception as e:
        products = []
        agregar_mensajes_log(f"Error cargando productos: {json.dumps(str(e))}")

    return render_template('index.html', registros=registros, users=users, products=products)

mensajes_log = []

def agregar_mensajes_log(texto, session_id=None):
    """
    Guarda un mensaje en memoria y en la base de datos.
    Si el mensaje no es serializable, lo convierte a string.
    Puede vincularse a una sesión si se proporciona session_id.
    """
    try:
        # Serializar texto si es necesario
        if isinstance(texto, (dict, list)):
            texto_str = json.dumps(texto, ensure_ascii=False)
        else:
            texto_str = str(texto)

        mensajes_log.append(texto_str)

        nuevo_registro = Log(texto=texto_str, session_id=session_id)
        db.session.add(nuevo_registro)
        db.session.commit()

    except Exception as e:
        fallback = f"[ERROR LOG] No se pudo guardar el log original: {str(texto)} | Error: {str(e)}"
        mensajes_log.append(fallback)

        try:
            fallback_registro = Log(texto=fallback, session_id=session_id)
            db.session.add(fallback_registro)
            db.session.commit()
        except:
            pass

#Token de verificacion para la configuracion
TOKEN_WEBHOOK_WHATSAPP = f"{Config.TOKEN_WEBHOOK_WHATSAPP}"

@app.route('/webhook', methods=['GET','POST'])
def webhook():
    if request.method == 'GET':
        challenge = verificar_token_whatsapp(request)
        return challenge
    elif request.method == 'POST':
        reponse = recibir_mensajes(request)
        return reponse

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
            agregar_mensajes_log(json.dumps(data, ensure_ascii=False))
        except TypeError as e:
            agregar_mensajes_log(f"[Log ignorado] No se pudo serializar data: {str(e)}")

        if not data or 'entry' not in data:
            agregar_mensajes_log("Error: JSON sin 'entry' o 'Data'")
            return jsonify({'message': 'EVENT_RECEIVED'})

        entry = data['entry'][0]
        changes = entry.get('changes', [])[0]
        value = changes.get('value', {})
        messages_list = value.get('messages', [])

        if messages_list:
            message = messages_list[0]
            phone_number = message.get("from")

            session = load_or_create_session(phone_number)
            if not session:
                session = load_or_create_session(phone_number)

            # Guardar log
            try:
                agregar_mensajes_log(json.dumps(message, ensure_ascii=False))
            except TypeError as e:
                agregar_mensajes_log(f"[Log ignorado] No se pudo serializar message: {str(e)}")
            msg_type = message.get("type")

            if msg_type == "interactive":
                interactive = message.get("interactive", {})
                tipo_interactivo = interactive.get("type")

                if tipo_interactivo == "button_reply":
                    text = interactive.get("button_reply", {}).get("id")
                    if text:
                        enviar_mensajes_whatsapp(text, phone_number)

                elif tipo_interactivo == "list_reply":
                    text = interactive.get("list_reply", {}).get("id")
                    if text:
                        enviar_mensajes_whatsapp(text, phone_number)

            elif msg_type == "text":
                text = message.get("text", {}).get("body")
                if text:
                    enviar_mensajes_whatsapp(text, phone_number)

        return jsonify({'message': 'EVENT_RECEIVED'})

    except Exception as e:
        agregar_mensajes_log(f"Error en recibir_mensajes: {str(e)}")
        return jsonify({'message': 'EVENT_RECEIVED'})

def bot_enviar_mensaje_whatsapp(data):
    headers = {
        "Content-Type" : "application/json",
        "Authorization" : f"{Config.WHATSAPP_TOKEN}"
    }
    
    connection = http.client.HTTPSConnection("graph.facebook.com")
    try:
        #Convertir el diccionaria a formato JSON
        json_data = json.dumps(data)
        connection.request("POST", f"/v22.0/{Config.PHONE_NUMBER_ID}/messages", json_data, headers)
        response = connection.getresponse()
        print(f"Estado: {response.status} - {response.reason}")
        return response.read()
    except Exception as e:
        agregar_mensajes_log(json.dumps(e))
        return None
    finally:
        connection.close()

def manejar_comando_ofertas(number):
    """Procesa el comando de ofertas con mejor logging"""
    try:
        agregar_mensajes_log(f"Inicio comando ofertas para {number}")
        
        productos = woo_service.obtener_ofertas_recientes()
        agregar_mensajes_log(f"Productos crudos recibidos: {len(productos)} items")
        
        # Validación adicional de productos
        if not isinstance(productos, list):
            agregar_mensajes_log("Error: La respuesta de productos no es una lista")
            productos = []
        
        mensajes = woo_service.formatear_ofertas_whatsapp(productos)
        agregar_mensajes_log(f"Mensajes formateados: {len(mensajes)}")
        
        respuesta = [{
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {"body": "📢 *OFERTAS ESPECIALES* 🎁\n\nEstas son nuestras mejores ofertas:"}
        }]
        
        for msg in mensajes:
            # Validar que el mensaje no esté vacío
            if msg and isinstance(msg, str):
                respuesta.append({
                    "messaging_product": "whatsapp",
                    "to": number,
                    "type": "text",
                    "text": {
                        "preview_url": True,
                        "body": msg
                    }
                })

        # Botón final solo si hay mensajes válidos
        if len(respuesta) > 1:  # Si hay al menos un producto
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
        
        agregar_mensajes_log(f"Respuesta final construida con {len(respuesta)} mensajes")
        return respuesta
        
    except Exception as e:
        error_msg = f"Error crítico en manejar_comando_ofertas: {str(e)}"
        agregar_mensajes_log(error_msg)
        return [{
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {"body": "⚠️ Ocurrió un error al cargar las ofertas. Por favor intenta más tarde."}
        }]

def enviar_mensajes_whatsapp(texto,number):
    texto = texto.lower()
    user_msg = texto
    data = []
    session = load_or_create_session(number)
    flujo_producto = ProductModel.query.filter_by(session_id=session.idUser).first()

    if flujo_producto:
        data = manejar_paso_actual(number, texto)

    elif "hola" in texto.strip():
        data = [
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
    elif "1" == texto.strip():
        data = formulario_motor(number)

    elif "2" == texto.strip():
        data = manejar_comando_ofertas(number)

    elif "3" == texto.strip():        
        data = [
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
    elif "4" == texto.strip():
        data = [
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
    elif "5" == texto.strip():
        data = [
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
    elif "6" == texto.strip():
        data = [
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
    elif "7" == texto.strip():
        data = [
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
    elif "8" == texto.strip():
        data = [
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
    elif "0" == texto.strip():
        data = [
            generar_menu_principal(number)
        ]
    else:
        # Aquí es donde ahora usamos LangChain para manejar mensajes no estructurados
        data = [
            asistente(user_msg)
        ]

    # Envío secuencial con pausas
    for mensaje in data:
        bot_enviar_mensaje_whatsapp(mensaje)
        agregar_mensajes_log(json.dumps(mensaje))
        time.sleep(1)  # Pausa para cumplir con rate limits de WhatsApp

if __name__=='__main__':
    app.run(host='0.0.0.0',port=80,debug=True)