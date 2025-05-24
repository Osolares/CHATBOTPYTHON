from typing import TypedDict, Optional, List, Dict, Any, Union
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from config import db, Config
from models import UserSession, Log, ProductModel, Configuration, Memory
#from woocommerce_service import WooCommerceService, obtener_producto_por_url, buscar_producto_por_nombre, formatear_producto_whatsapp
from woocommerce_service import WooCommerceService
from datetime import datetime
import json
import time
import http.client
import os
from flask import Flask, request, jsonify, render_template, redirect
from flask_sqlalchemy import SQLAlchemy
from formularios import formulario_motor, manejar_paso_actual
from menus import generar_list_menu, generar_menu_principal
from datetime import datetime, timedelta
from pytz import timezone
from config import now,GUATEMALA_TZ
import re
import threading
from collections import deque
from langchain_groq import ChatGroq
import random
import difflib

# Instancia global del servicio
woo_service = WooCommerceService()

# Configuración de DeepSeek
deepseek_key = os.environ["DEEPSEEK_API_KEY"]
model = ChatOpenAI(
    model="deepseek-chat",
    api_key=deepseek_key,
    base_url="https://api.deepseek.com/v1",
    temperature=0.5,
    max_tokens=100,
)

#llm = ChatGroq(
#    model="llama3-70b-8192"
#)
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
    additional_messages: List[Dict[str, Any]] 
    conversation_memory: Optional[Dict[str, Any]] 

# Guardará los últimos 1000 message_id procesados
mensajes_procesados = deque(maxlen=1000)
mensajes_lock = threading.Lock()  # para evitar condiciones de carrera
#GUATEMALA_TZ = timezone('America/Guatemala')
#
#def now():
#    return datetime.now(GUATEMALA_TZ)
def block(source, message):
    # --- BLOQUEO DE USUARIOS ---

    BLOQUEADOS = {
        "whatsapp": ["502123456", "50233334444","reaction"],
        "telegram": ["123456789"],
        "web": ["correo@ejemplo.com"]
    }

    #TIPOS_BLOQUEADOS = {
    #    "type": ["emoji", "reaction"]
    #}

    phone_number = message.get("from")
    #types = "type"
    type_msg = message.get("type")


    #if phone_number in BLOQUEADOS.get(source, []) or type_msg in TIPOS_BLOQUEADOS.get(types, []) :
    if phone_number in BLOQUEADOS.get(source, []) or type_msg in BLOQUEADOS.get(source, []) :

        # Para usuarios bloqueados SI interrumpimos el flujo
        error_msg = f"❌ Error Usuario bloqueado"
        agregar_mensajes_log(error_msg)
        return {"status": "blocked", "message": error_msg}
    
    return {"status": "success"}

def ya_esta_procesado(message_id: str) -> bool:
    with mensajes_lock:
        if message_id in mensajes_procesados:
            return True
        mensajes_procesados.append(message_id)
        return False

def guardar_memoria(session_id, clave, valor):
    mem = Memory.query.filter_by(session_id=session_id, key=clave).first()
    if not mem:
        mem = Memory(session_id=session_id, key=clave)
        db.session.add(mem)
    mem.value = valor
    db.session.commit()

def obtener_ultimas_memorias(session_id, limite=6):
    memorias = Memory.query.filter_by(session_id=session_id)\
                .order_by(Memory.created_at.desc())\
                .limit(limite).all()
    return list(reversed(memorias))  # Para orden cronológico

def guardar_memoria(session_id, key, value):
    try:
        memoria = Memory(session_id=session_id, key=key, value=value)
        db.session.add(memoria)
        db.session.commit()
    except Exception as e:
        error_text = f"❌ Error al guardar memoria ({key}): {str(e)}"
        agregar_mensajes_log(error_text, session_id)

def cargar_memoria_slots(session):
    mem = Memory.query.filter_by(session_id=session.idUser, key='slots_cotizacion').first()
    #agregar_mensajes_log(f"[DEBUG] cargar_memoria_slots para session {getattr(session, 'idUser', None)} devuelve: {mem.value if mem else None}")
    if mem and mem.value:
        return json.loads(mem.value)
    return {}


def guardar_memoria_slots(session, slots):
    mem = Memory.query.filter_by(session_id=session.idUser, key='slots_cotizacion').first()
    if not mem:
        mem = Memory(session_id=session.idUser, key='slots_cotizacion')
        db.session.add(mem)
    mem.value = json.dumps(slots, ensure_ascii=False)
    db.session.commit()

def resetear_memoria_slots(session):
    from models import Memory, db
    mem = Memory.query.filter_by(session_id=session.idUser, key='slots_cotizacion').first()
    if mem:
        mem.value = "{}"
        db.session.commit()


def should_process_message(session):
    now = datetime.now()
    if session.bloqueado:
        return False, "Usuario bloqueado"
    if session.modo_control == 'paused' and session.pausa_hasta and session.pausa_hasta > now:
        return False, "En pausa, esperando asesor"
    if session.modo_control == 'human':
        return False, "Modo humano"
    return True, None


# feriados configurables
DIAS_FESTIVOS = {"2025-01-01","2025-04-17","2025-04-18","2025-05-01"}

def es_dia_festivo(fecha: datetime) -> bool:
    return fecha.strftime("%Y-%m-%d") in DIAS_FESTIVOS

def pre_validaciones(state: BotState) -> BotState:
    ahora = now()
    session = state.get("session")
    phone_or_id = state.get("phone_number") or state.get("message_data", {}).get("email")
    source = state.get("source")

    state.setdefault("additional_messages", [])

    send_welcome, kind = False, None

    if session.modo_control == 'paused' and session.pausa_hasta and session.pausa_hasta <= datetime.now():
        session.modo_control = 'bot'
        session.pausa_hasta = None
        db.session.commit()


    # --- HORARIO ---
    HORARIO = {
        0: ("08:00", "17:30"), 1: ("08:00", "17:30"), 2: ("08:00", "17:30"),
        3: ("08:00", "17:30"), 4: ("08:00", "17:30"), 5: ("08:00", "12:30"), 6: (None, None)
    }

    dia = ahora.weekday()
    h_ini_str, h_fin_str = HORARIO.get(dia, (None, None))
    dentro_horario = False

    if h_ini_str and h_fin_str:
        h_ini = GUATEMALA_TZ.localize(datetime.combine(ahora.date(), datetime.strptime(h_ini_str, "%H:%M").time()))
        h_fin = GUATEMALA_TZ.localize(datetime.combine(ahora.date(), datetime.strptime(h_fin_str, "%H:%M").time()))
        dentro_horario = h_ini <= ahora <= h_fin

    try:
        if not dentro_horario:
            mostrar_alerta = False

            if session:
                ultima_alerta = session.ultima_alerta_horario or datetime.min.replace(tzinfo=GUATEMALA_TZ)
                if ultima_alerta.tzinfo is None:
                    ultima_alerta = GUATEMALA_TZ.localize(ultima_alerta)

                if ahora - ultima_alerta > timedelta(hours=1):
                    mostrar_alerta = True
                    session.ultima_alerta_horario = ahora
                    db.session.commit()
                    log_state(state, "⏰ Alerta de fuera de horario enviada.")
            else:
                mostrar_alerta = True  # Si no hay sesión, se muestra igual

            if mostrar_alerta:
                state["additional_messages"].append({
                    "messaging_product": "whatsapp" if source == "whatsapp" else "other",
                    "to": phone_or_id,
                    "type": "text",
                    "text": {
                        "body": "🕒 Gracias por comunicarte con nosotros. En este momento estamos fuera de nuestro horario de atención.\n\n💬 Puedes continuar usando nuestro asistente y nuestro equipo te atenderá lo más pronto posible."
                    }
                })

    except Exception as e:
        db.session.rollback()
        log_state(state, f"❌ Error al guardar alerta de horario: {str(e)}")


    try:
        # --- BIENVENIDA ---
        if session:
            last_interaction = session.last_interaction
            if last_interaction and last_interaction.tzinfo is None:
                last_interaction = GUATEMALA_TZ.localize(last_interaction)

            if not session.mostro_bienvenida:
                send_welcome, kind = True, "nueva"
            elif (ahora - last_interaction) > timedelta(hours=24):
                send_welcome, kind = True, "retorno"

        if send_welcome:
            msg = (
                "👋 ¡Bienvenido(a) a Intermotores! Estamos aquí para ayudarte a encontrar el repuesto ideal para tu vehículo. 🚗 \n\n🗒️ Consulta nuestro menú."
                if kind == "nueva" else
                "👋 ¡Hola de nuevo! Gracias por contactar a Intermotores. ¿En qué podemos ayudarte hoy? 🚗\n\n🗒️Consulta nuestro menú."
            )

            state["additional_messages"].append({
                "messaging_product": "whatsapp" if source == "whatsapp" else "other",
                "recipient_type": "individual",
                "to": phone_or_id,
                "type": "image",
                "image": {
                    "link": "https://intermotores.com/wp-content/uploads/2025/04/LOGO_INTERMOTORES.png",
                    "caption": msg
                }
            })

            if source == "whatsapp":
                menu_msg = generar_list_menu(phone_or_id)
                state["additional_messages"].append(menu_msg)

            session.mostro_bienvenida = True
            db.session.commit()
            log_state(state, "✅ Bienvenida enviada y marcada como mostrada.")

    except Exception as e:
        db.session.rollback()
        log_state(state, f"❌ Error al guardar mostro_bienvenida: {str(e)}")

    log_state(state, f"⏺️ Saliendo de pre_validaciones a las {ahora.isoformat()}")

    return state


def load_or_create_session(state: BotState) -> BotState:
    """Carga o crea una sesión de usuario, compatible con múltiples fuentes: WhatsApp, Telegram, Messenger, Web."""
    phone_number = state.get("phone_number")
    source = state.get("source")
    message_data = state.get("message_data", {})
    state.setdefault("logs", [])

    session = None
    #agregar_mensajes_log(f"Entrando En userSession: {state}")

    try:
        log_state(state, f"⏺️ Iniciando búsqueda o creación de sesión...")

        if source == "whatsapp":
            log_state(state, f"⏺️ Canal: WhatsApp")
            session = db.session.query(UserSession).filter_by(phone_number=phone_number).first()
            if not session:
                log_state(state, f"⏺️ No existe sesión previa. Creando nueva...")
                session = UserSession(phone_number=phone_number)
                db.session.add(session)
                db.session.flush()
                log_state(state, f"⏺️ Usuario creado en base de datos.")

        elif source == "telegram":
            chat_id = message_data.get("chat_id")
            log_state(state, f"⏺️ Canal: Telegram")
            session = db.session.query(UserSession).filter_by(telegram_id=chat_id).first()
            if not session:
                session = UserSession(telegram_id=chat_id)
                db.session.add(session)
                db.session.flush()

        elif source == "messenger":
            messenger_id = message_data.get("recipient", {}).get("id")
            log_state(state, f"⏺️ Canal: Messenger")
            session = db.session.query(UserSession).filter_by(messenger_id=messenger_id).first()
            if not session:
                session = UserSession(messenger_id=messenger_id)
                db.session.add(session)
                db.session.flush()

        elif source == "web":
            email = message_data.get("email")
            log_state(state, f"⏺️ Canal: Web")
            session = db.session.query(UserSession).filter_by(email=email).first()
            if not session and email:
                session = UserSession(email=email)
                db.session.add(session)
                db.session.flush()

        if session:
            log_state(state, f"⏺️ Actualizando timestamp de última interacción.")
            session.last_interaction = now()
            state["session"] = session

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        log_state(state, f"❌ Error al crear o cargar sesión: {str(e)}")

    if not state.get("session"):
        log_state(state, "⚠️ No se encontró o creó una sesión válida.")
    else:
        session_id = getattr(state["session"], "idUser", "sin sesión")
        #log_state(state, f"⏺️ Saliendo de load_or_create_session: sesión con id {session_id} a las {now().isoformat()}")

    return state

def load_product_flow(state: BotState) -> BotState:
    """Carga el estado del flujo de producto para el usuario actual"""
    #agregar_mensajes_log(f"En load_product_flow: {state}")

    if state["session"]:

        flujo_producto = db.session.query(ProductModel).filter_by(
            session_id=state["session"].idUser
        ).first()
        state["flujo_producto"] = flujo_producto

    log_state(state, f"⏺️ Saliendo de load product flow: {state['flujo_producto']} at {now().isoformat()}")
    return state

def handle_product_flow(state: BotState) -> BotState:
    """Maneja el flujo de producto si existe para el usuario"""
    #agregar_mensajes_log(f"En handle_product_flow: {state}")

    if state["flujo_producto"]:
        response = manejar_paso_actual(
            state["phone_number"],
            state["user_msg"]
        )
        # FUTURO: Aquí podríamos modificar 'response' si quisiéramos respuestas distintas por source.
        state["response_data"] = response
    log_state(state, f"⏺️ Saliendo de handle product flow: {state['flujo_producto']} at {now().isoformat()}")
    return state

def mensaje_parece_interes_en_producto(texto):
    texto = texto.lower()
    patron = r"hola, estoy interesado en el producto: .*? que se encuentra en https?://[^\s]+"
    #patron = r"(interesado|quiero|me interesa|información|info|detalles).*https?://[^\s]+"
    return re.search(patron, texto)

def extraer_url(texto):
    match = re.search(r"https?://[^\s]+", texto)
    return match.group(0) if match else None


def handle_special_commands(state: BotState) -> BotState:
    """Maneja comandos especiales (1-8, 0, hola) para cada usuario, considerando la fuente"""
    #agregar_mensajes_log(f"En handle_special_commands: {state}")

    texto = state["user_msg"].lower().strip()
    number = state.get("phone_number")
    source = state.get("source")

    # Verifica si el mensaje parece interés en un producto con URL
    if mensaje_parece_interes_en_producto(texto):
        url = extraer_url(texto)
        producto = None
        
        # Primero intentar por URL
        if url:
            producto = woo_service.obtener_producto_por_url(url)
        
        # Si no se encontró por URL, intentar por nombre
        if not producto:
            # Extraer nombre del producto del mensaje
            nombre_match = re.search(r"producto:\s*(.*?)\s*que se encuentra", texto, re.IGNORECASE)
            if nombre_match:
                nombre_producto = nombre_match.group(1)
                producto = woo_service.buscar_producto_por_nombre(nombre_producto)

        if producto:
            mensaje = woo_service.formatear_producto_whatsapp(producto)
            state["response_data"] = [{
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": True,  # Habilitar vista previa para el enlace
                    "body": mensaje
                }
            }]
        else:
            state["response_data"] = [{
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "😕 No pudimos encontrar el producto que buscas. Por favor verifica:\n\n"
                            "1. Que el enlace sea correcto\n"
                            "2. Que el nombre del producto esté bien escrito\n\n"
                            "Puedes intentar nuevamente o escribir '0' para ver nuestro menú principal."
                }
            }]
        return state

    # Dependiendo del source, podrías en el futuro mandar menús diferentes.
    if "hola" == texto:
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

    log_state(state, f"⏺️ Saliendo de handle special products: {state['response_data']} at {now().isoformat()}")
    return state


def asistente(state: BotState) -> BotState:
    """Maneja mensajes no reconocidos usando DeepSeek"""

    if not state.get("response_data"):
        user_msg = state["user_msg"]
        session = state.get("session")
        session_id = session.idUser if session else None

        # Verificar duplicado
        last_log = db.session.query(Log).filter(
            Log.session_id == session_id
        ).order_by(Log.fecha_y_hora.desc()).first()
        if last_log and user_msg in (last_log.texto or ""):
            agregar_mensajes_log("🔁 Mensaje duplicado detectado, ignorando respuesta asistente", session_id)
            return state

        # 🧠 Obtener contexto previo
        contexto_memoria = ""
        if session_id:
            memorias = obtener_ultimas_memorias(session_id, limite=6)
            if memorias:
                contexto_memoria = "\n".join([f"{m.key}: {m.value}" for m in memorias])

        # 🧾 Construir prompt con contexto
        prompt_usuario = f"Mensaje del usuario: {user_msg}"
        if contexto_memoria:
            prompt_usuario = f"""
Contexto de conversación previa:
{contexto_memoria}

{prompt_usuario}
"""

        safety_prompt = f"""
Eres un asistente llamado Boty especializado en motores y repuestos para vehículos de marcas japonesas y coreanas que labora en Intermotores, responde muy puntual y en las minimas palabras máximo 50 usa emojis ocasionalmente según sea necesario. 

Solo responde sobre:
- Motores y repuestos para vehículos
- Piezas, partes o repuestos de automóviles

No incluyas información innecesaria (como el número de palabras).
nunca confirmes disponibilidad, exitencias, precio, etc

Si el mensaje no está relacionado, responde cortésmente indicando que solo puedes ayudar con temas de motores y repuestos.
si es un mensaje de saludo, bienvenida, agradecimiento o despedida responde algo acorde

{prompt_usuario}
"""
        # 🤖 Llamar al modelo
        response = model.invoke([HumanMessage(content=safety_prompt)])
        body = response.content

        # 📝 Guardar memorias
        if session_id:
            guardar_memoria(session_id, "user", user_msg)
            guardar_memoria(session_id, "assistant", body)

        # 📤 Preparar respuesta
        if state["source"] in ["whatsapp", "telegram", "messenger", "web"]:
            state["response_data"] = [{
                "messaging_product": "whatsapp" if state["source"] == "whatsapp" else "other",
                "to": state.get("phone_number") or state.get("email"),
                "type": "text",
                "text": {"body": body}
            }]

        log_state(state, f"✅ Asistente respondió con memoria: {body[:100]}...")

    return state

#PROMPT_SLOT_FILL = """
#Extrae la siguiente información en JSON. Pon null si no se encuentra.
#Campos obligatorios: tipo_repuesto, marca, modelo, año, serie_motor, cc, combustible
#Campo opcional: descripcion (agrega cualquier dato extra, comentarios del cliente, detalles técnicos que ayuden a la cotización, como VGT, intercooler, importado, turbo, etc)
#
#Ejemplo:
#Entrada: "Quiero un motor 4D56 para L200, año 2017, es versión VGT con intercooler"
#Salida:
#{"tipo_repuesto":"motor","marca":null,"modelo":"L200","año":"2017","serie_motor":"4D56","cc":null,"combustible":null,"descripcion":"versión VGT con intercooler"}
#
#Entrada: "{MENSAJE}"
#Salida:
#"""

#def slot_filling_llm(mensaje):
#    agregar_mensajes_log(f"🔁mensaje entrante {json.dumps(mensaje)}")
#    prompt = PROMPT_SLOT_FILL.replace("{MENSAJE}", mensaje)
#    response = model.invoke([HumanMessage(content=prompt)], max_tokens=200)
#    try:
#        result = json.loads(response.content.strip())
#        agregar_mensajes_log(f"🔁Respuesta LLM {json.dumps(result)}")
#
#    except Exception:
#        agregar_mensajes_log(f"🔁Respuesta LLM EXCEPTTION")
#
#        result = {}
#    return result

# Prompt de slot filling
PROMPT_SLOT_FILL = """
Extrae la siguiente información en JSON. Pon null si no se encuentra.
Campos: tipo_repuesto, marca, modelo, año, serie_motor, cc, combustible

Ejemplo:
Entrada: "Turbo para sportero 2.5"
el año tambien te lo pueden decir como modelo y puede venir abreviado ejmplo "modelo 90"
la linea puede tener algunas variaciones o estar mal escrita ejemplo "colola" en vez de "corolla"
Salida:
{"tipo_repuesto":"turbo","marca":null,"linea":"sportero","año":null,"serie_motor":null,"cc":"2.5","combustible":null}

Entrada: "{MENSAJE}"
Salida:
"""

def extract_json(texto):
    try:
        match = re.search(r'\{[\s\S]*\}', texto)
        if match:
            return json.loads(match.group())
    except Exception as e:
        agregar_mensajes_log(f"[extract_json] Error: {str(e)}")
    return {}

def slot_filling_llm(mensaje):
    #agregar_mensajes_log(f"🔁mensaje entrante {json.dumps(mensaje)}")

    prompt = PROMPT_SLOT_FILL.replace("{MENSAJE}", mensaje)
    response = model.invoke([HumanMessage(content=prompt)], max_tokens=100)
    result = extract_json(response.content.strip())
    agregar_mensajes_log(f"🔁Respuesta LLM {response}")
    return result

# Reglas técnicas (comienza con tus casos más comunes)
REGLAS_SERIE_MOTOR = {
    "1kz": {"marca": "Toyota", "cilindros": "4",  "cc": "3.0", "combustible": "diésel", "caracteristicas": ["turbo", "culata de aluminio"], "lineas": ["Prado", "Hilux", "4Runner"]},
    "4d56": {"marca": "Mitsubishi", "cilindros": "4",  "cc": "2.5", "combustible": "diésel", "caracteristicas": ["turbo", "sin turbo"], "lineas": ["L200", "L300"]},

    "j3": {"marca": "Hyundai", "cc": "2.9", "combustible": "diésel", "lineas": ["Terracan"]}
}
REGLAS_MODELOS = {
    "Sportero": {"marca": "Mitsubishi", "serie_motor": "4D56U", "cc": "2.5", "combustible": "diésel"},
    "l200": {"marca": "Mitsubishi"}

}

# Estructura principal: MARCAS con sus LINEAS/VARIANTES
MARCAS_LINEAS = {
    "Toyota": {
        "corolla": ["corolla", "corola", "corolaa", "corolla xli", "corolla gli", "corola xli", "corola gli"],
        "hilux": ["hilux", "hiluxx", "hi lux", "hi-lux"],
        "prado": ["prado", "pradoo", "land cruiser prado", "prado land cruiser", "prado tx", "prado tz", "prado gx"],
        "rav4": ["rav4", "rav 4", "rav-4", "rav"],
        "fortuner": ["fortuner", "fortiner", "fortuner sw4", "sw4"],
        "yaris": ["yaris", "yaris sedan", "yariz", "yaris hatchback"],
        "camry": ["camry", "camri"],
        "4runner": ["4runner", "4 runner", "4-runner", "forerunner"],
        "tacoma": ["tacoma", "tacoma pickup", "takoma"],
        "hiace": ["hiace", "hi ace", "hi-ace", "hiaze", "hiaice", "hiaice"],
        "avanza": ["avanza", "avanze"],
        "land cruiser": ["land cruiser", "landcruiser", "land cruiser 70", "land cruiser 80"],
    },
    "Honda": {
        "civic": ["civic", "civik", "sibic"],
        "crv": ["crv", "cr-v", "cr v", "cruv"],
        "accord": ["accord", "acord"],
        "fit": ["fit", "fit hatchback", "honda fit"],
        "pilot": ["pilot", "piloto"],
        "city": ["city", "citi", "honda city"],
    },
    "Hyundai": {
        "accent": ["accent", "acscent", "ascen", "acscent"],
        "tucson": ["tucson", "tucsón", "tuczon", "tuckson"],
        "elantra": ["elantra", "elantra hd", "elantra gls"],
        "santa fe": ["santa fe", "santafe", "santa-fe", "santafé"],
        "creta": ["creta"],
        "grand i10": ["grand i10", "i10", "i-10", "grand i-10"],
        "h1": ["h1", "h-1", "hyundai h1", "h uno"],
        "sonata": ["sonata", "sonatta"],
        "veracruz": ["veracruz", "vera cruz"],
    },
    "Kia": {
        "sportage": ["sportage", "sportaje", "sportage r", "sportage revolution"],
        "sorento": ["sorento", "sorrento", "sorento prime"],
        "rio": ["rio", "río", "río sedan", "rio sedan"],
        "picanto": ["picanto", "pikanto"],
        "cerato": ["cerato", "ceratto"],
        "optima": ["optima", "óptima"],
        "forte": ["forte"],
    },
    "Mazda": {
        "3": ["mazda 3", "mazda3", "mazda tres", "3", "tres"],
        "6": ["mazda 6", "mazda6", "mazda seis", "6", "seis"],
        "cx-5": ["cx5", "cx-5", "cx 5"],
        "cx-3": ["cx3", "cx-3", "cx 3"],
        "bt-50": ["bt50", "bt-50", "bt 50"],
    },
    "suzuki": {
        "swift": ["swift", "switf"],
        "vitara": ["vitara", "vitara live", "vitarra", "gran vitara"],
        "jimny": ["jimny", "jimni"],
        "alto": ["alto"],
        "xl7": ["xl7", "xl 7", "xl-7", "xl siete", "x l 7", "xlseven"],
        "ertiga": ["ertiga", "ertiga suzuki"],
    },
    "Nissan": {
        "frontier": ["frontier", "fronter", "nissan frontier", "nissan frontera"],
        "sentra": ["sentra", "sentra b13", "sentra b14", "sentra b15"],
        "tiida": ["tiida", "tida"],
        "xtrail": ["xtrail", "x-trail", "x trail", "extrail", "xtrail t30", "xtrail t31"],
        "versa": ["versa", "bersa"],
        "murano": ["murano", "morano"],
        "altima": ["altima", "áltima"],
        "np300": ["np300", "np 300", "n p 300"],
        "urvan": ["urvan", "urban", "urvam"],
    },
    "Chevrolet": {
        "aveo": ["aveo", "aveo family"],
        "tracker": ["tracker", "trackker"],
        "spark": ["spark", "sparc", "sparck", "spark gt"],
        "captiva": ["captiva"],
        "cruze": ["cruze", "cruse"],
        "sail": ["sail", "sail sedan"],
    },
    "Mitsubishi": {
        "l200": ["l200", "l-200", "l 200", "l doscientos", "l dos cientos", "ldoscientos"],
        "montero": ["montero", "montero sport", "montero limited"],
        "outlander": ["outlander", "out lander"],
        "mirage": ["mirage", "miraje"],
        "pajero": ["pajero", "pallero"],
        "sportero": ["sportero", "sporttero"],
        "l300": ["l300", "l-300", "l 300", "l trescientos"],
    },
    "Volkswagen": {
        "golf": ["golf", "golfo"],
        "jetta": ["jetta", "jeta", "yeta"],
        "vento": ["vento", "bento"],
        "passat": ["passat", "pazat"],
        "amarok": ["amarok", "amarock"],
        "polo": ["polo"],
        "saveiro": ["saveiro", "saveyro"],
    },
    "Ford": {
        "ranger": ["ranger", "ranguer"],
        "escape": ["escape", "escap"],
        "fiesta": ["fiesta"],
        "explorer": ["explorer", "explorador"],
        "ecosport": ["ecosport", "eco sport"],
        "f150": ["f150", "f-150", "f 150"],
    },
    "Isuzu": {
        "dmax": ["dmax", "d-max", "d max"],
        "trooper": ["trooper"],
        "mu-x": ["mux", "mu-x", "mu x"],
    },
    # Agrega otras marcas y modelos populares aquí...
}


ALIAS_MODELOS = {
    "l200": "L200",
    "l-200": "L200",
    "l 200": "L200",
    # Agrega más si necesitas
}

FRASES_NO_SE = ["no sé", "no se", "nose", "no tengo", "no la tengo", "no recuerdo", "desconozco", "no aplica", "no", "x", "n/a"]

TIPOS_REPUESTO = [
    "motor", "culata", "turbina", "bomba", "inyector", "alternador", "radiador",
    "caja", "transmisión", "transmision", "computadora", "filtro", "embrague"
]

def extraer_tipo_repuesto(texto_usuario):
    texto_norm = texto_usuario.lower()
    for tipo in TIPOS_REPUESTO:
        if tipo in texto_norm:
            return tipo
    return None
#def es_no_se(texto):
#    texto = texto.strip().lower()
#    return any(f in texto for f in FRASES_NO_SE)
def es_no_se(texto):
    texto = texto.strip().lower()
    return any(f in texto for f in FRASES_NO_SE)

#def es_cotizacion_completa(slots):
#    # Ruta 1: tipo_repuesto, marca, modelo, año, serie_motor
#    if all(slots.get(k) not in [None, ""] for k in ["tipo_repuesto", "marca", "linea", "año", "serie_motor"]):
#        return True
#    # Ruta 2: tipo_repuesto, serie_motor, año
#    if all(slots.get(k) not in [None, ""] for k in ["tipo_repuesto", "serie_motor", "año"]):
#        return True
#    # Ruta 3: modelo, tipo_repuesto, combustible, cc, año
#    if all(slots.get(k) not in [None, ""] for k in ["linea", "tipo_repuesto", "combustible", "cc", "año"]):
#        return True
#    return False
def obtener_marca_y_linea(linea_usuario):
    # Normaliza para buscar (lowercase y sin espacios/guiones)
    normalizado = linea_usuario.lower().replace("-", "").replace(" ", "")
    for marca, lineas in MARCAS_LINEAS.items():
        for linea, alias_list in lineas.items():
            for alias in alias_list:
                alias_norm = alias.lower().replace("-", "").replace(" ", "")
                if normalizado == alias_norm:
                    return marca, linea  # Retorna la marca real y el modelo/linea estándar
    return None, None  # Si no encuentra

def extraer_linea_y_marca_usuario(texto_usuario):
    texto_norm = texto_usuario.lower().replace("-", "").replace("  ", " ").strip()
    # Recolecta todos los alias en una lista [(marca, linea, alias_normalizado)]
    alias_todos = []
    for marca, lineas in MARCAS_LINEAS.items():
        for linea, alias_list in lineas.items():
            for alias in alias_list:
                alias_norm = alias.lower().replace("-", "").replace(" ", "")
                alias_todos.append((marca, linea, alias_norm))
    # Busca alias más cercano en el mensaje
    palabras_usuario = texto_norm.replace(" ", "")
    mejores = difflib.get_close_matches(palabras_usuario, [alias_norm for (_, _, alias_norm) in alias_todos], n=1, cutoff=0.7)
    if mejores:
        for marca, linea, alias_norm in alias_todos:
            if alias_norm == mejores[0]:
                return marca, linea
    # Si no hay fuzzy match, intenta match parcial (por si el usuario pone varias palabras: "suzuki xl7")
    for marca, lineas in MARCAS_LINEAS.items():
        for linea, alias_list in lineas.items():
            for alias in alias_list:
                alias_norm = alias.lower().replace("-", "").replace(" ", "")
                if alias_norm in palabras_usuario:
                    return marca, linea
    return None, None


def es_cotizacion_completa(slots):
    # Ruta 1: Todos completos o con "no_sabe"
    if all(slots.get(k) not in [None, ""] for k in ["tipo_repuesto", "marca", "linea", "año", "serie_motor"]):
        return True
    # Ruta 2: tipo_repuesto, serie_motor, año (permite "no_sabe" en año)
    if (
        slots.get("tipo_repuesto") not in [None, "", "no_sabe"] and
        slots.get("serie_motor") not in [None, "", "no_sabe"] and
        slots.get("año") not in [None, ""]
    ):
        return True
    # Ruta 3: modelo, tipo_repuesto, combustible, cc, año (permite "no_sabe" en año)
    if (
        slots.get("linea") not in [None, "", "no_sabe"] and
        slots.get("tipo_repuesto") not in [None, "", "no_sabe"] and
        slots.get("combustible") not in [None, "", "no_sabe"] and
        slots.get("cc") not in [None, "", "no_sabe"] and
        slots.get("año") not in [None, ""]
    ):
        return True
    # Ruta alternativa: Todos menos año
    if all(slots.get(k) not in [None, "", "no_sabe"] for k in ["tipo_repuesto", "marca", "linea", "serie_motor", "cc", "combustible"]):
        return True
    return False


#def deducir_conocimiento(slots):
#    # Deducción por serie_motor (case-insensitive)
#    serie_motor = slots.get("serie_motor")
#    if serie_motor:
#        clave = serie_motor.lower().strip()
#        for key in REGLAS_SERIE_MOTOR:
#            if key.lower().strip() == clave:
#                for campo, valor in REGLAS_SERIE_MOTOR[key].items():
#                    if not slots.get(campo):
#                        slots[campo] = valor
#                break
#
#    # Deducción por modelo/linea (case-insensitive)
#    linea = slots.get("linea") or slots.get("modelo")  # según como uses los nombres de slot
#    if linea:
#        clave_linea = linea.lower().strip()
#        for key in REGLAS_MODELOS:
#            if key.lower().strip() == clave_linea:
#                for campo, valor in REGLAS_MODELOS[key].items():
#                    if not slots.get(campo):
#                        slots[campo] = valor
#                break
#
#    return slots
def deducir_conocimiento(slots):
    # Deducción por serie_motor (igual que antes)
    serie_motor = slots.get("serie_motor")
    if serie_motor:
        clave = serie_motor.lower().strip()
        for key in REGLAS_SERIE_MOTOR:
            if key.lower().strip() == clave:
                for campo, valor in REGLAS_SERIE_MOTOR[key].items():
                    if not slots.get(campo):
                        slots[campo] = valor
                break

    # Deducción por linea/modelo usando MARCAS_LINEAS y alias
    linea = slots.get("linea")
    if linea and not slots.get("marca"):
        marca, linea_std = obtener_marca_y_linea(linea)
        if marca:
            slots["marca"] = marca
            slots["linea"] = linea_std.capitalize()  # Guarda el nombre estándar

    return slots

#def campos_faltantes(slots):
#    necesarios = ["tipo_repuesto", "marca", "linea", "año", "serie_motor", "combustible"]
#    return [c for c in necesarios if not slots.get(c)]
def campos_faltantes(slots):
    necesarios = ["tipo_repuesto", "marca", "linea", "año", "serie_motor", "combustible", "cc"]
    # Solo pide los que son None, "", o no existen. IGNORA los slots marcados como "no_sabe"
    return [c for c in necesarios if (not slots.get(c) or slots.get(c) in ["", None])]


#def notificar_lead_via_whatsapp(numero_admin, session, memoria_slots, state):
#    resumen = "\n".join([f"{k}: {v}" for k, v in memoria_slots.items()])
#    mensaje = (
#        f"🚗 *Nuevo Lead para Cotización*\n\n"
#        f"📞 Cliente: {session.phone_number}\n"
#        f"Datos:\n{resumen}\n\n"
#        f"ID Sesión: {session.idUser}\n"
#    )
#    bot_enviar_mensaje_whatsapp({
#        "messaging_product": "whatsapp",
#        "to": numero_admin,
#        "type": "text",
#        "text": {"body": mensaje}
#    }, state)

# Frases random para cada slot (puedes ampliar)
PREGUNTAS_SLOTS = {
    "tipo_repuesto": [
        "¿Qué repuesto necesitas? (ejemplo: motor, culata, turbo, etc.)",
        "¿Sobre qué repuesto te gustaría cotizar?",
        "¿Cuál es el repuesto de tu interes?"
        "¿Qué tipo de repuesto necesitas?",
    ],
    "marca": [
        "¿Cuál es la marca de tu vehículo?",
        "¿Qué marca del auto?"
    ],
    "linea": [
        "¿Qué línea/modelo es tu vehículo?",
        "¿Podrías decirme la línea del vehículo?"
    ],
    "año": [
        "¿De qué año es tu vehículo?",
        "¿Sabes el año del auto?",
        "¿Para qué año necesitas?"

    ],
    "serie_motor": [
        "¿Conoces la serie del motor?",
        "¿Sabes la serie del motor?",
        "¿Tienes el número de serie del motor?"
    ],
    "comnbustible": [
        "¿El motor es diésel o gasolina?",
        "¿Su vehículo es diésel o gasolina?",
        "¿Diésel o gasolina?"
    ],
    "cc": [
        "¿Cuántos centímetros cúbicos es el motor?",
        "¿Cuántos c.c es el motor?"
    ]
}

def handle_cotizacion_slots(state: dict) -> dict:
    from datetime import datetime, timedelta

    session = state.get("session")
    user_msg = state.get("user_msg")

    # Limpia mensaje si viene en formato dict (WhatsApp)
    if isinstance(user_msg, dict):
        if user_msg.get("type") == "text":
            user_msg = user_msg.get("text", {}).get("body", "")
        elif user_msg.get("type") == "interactive":
            interactive = user_msg.get("interactive", {})
            tipo_interactivo = interactive.get("type")
            if tipo_interactivo == "button_reply":
                user_msg = interactive.get("button_reply", {}).get("id", "")
            elif tipo_interactivo == "list_reply":
                user_msg = interactive.get("list_reply", {}).get("id", "")
        else:
            user_msg = ""

    comandos_reset = ["nueva cotización", "/reset", "reiniciar_cotizacion"]
    if user_msg.strip().lower() in comandos_reset:
        resetear_memoria_slots(session)
        state["response_data"] = [{
            "messaging_product": "whatsapp",
            "to": state.get("phone_number"),
            "type": "text",
            "text": {"body": "👌 ¡Listo! Puedes empezar una nueva cotización cuando quieras. ¿Qué repuesto necesitas ahora?"}
        }]
        return state

    # 1. Cargar memoria de slots
    memoria_slots = cargar_memoria_slots(session)

    # Si la memoria está vacía, filtra por keywords (primer mensaje)
    if not memoria_slots or all(v in [None, "", "no_sabe"] for v in memoria_slots.values()):
        cotizacion_keywords = ["motor","necesito","que precio","qué precio", "quiero", "cuanto cuesta","cuánto cuesta","hay","tiene", "culata", "cotizar", "repuesto", "turbina", "bomba", "inyector", "alternador"]
        if not any(kw in user_msg.lower() for kw in cotizacion_keywords):
            return state
        
        agregar_mensajes_log(f"🔁reconocio cotizacion keywords {json.dumps(memoria_slots)}")

    # 2. Detecta "no sé" y marca el campo faltante como "no_sabe"
    #faltan = campos_faltantes(memoria_slots)
    #if len(faltan) == 1 and es_no_se(user_msg):
    #    campo_faltante = faltan[0]
    #    memoria_slots[campo_faltante] = "no_sabe"
    #    guardar_memoria_slots(session, memoria_slots)
    #    agregar_mensajes_log(f"[DEBUG] Usuario marcó {campo_faltante} como no_sabe")
    #    # Mensaje empático
    #    state["response_data"] = [{
    #        "messaging_product": "whatsapp",
    #        "to": state.get("phone_number"),
    #        "type": "text",
    #        "text": {"body": f"No te preocupes si no tienes el dato de {campo_faltante}. ¡Sigo con la cotización con lo que ya tenemos! 🚗"}
    #    }]
    #    state["cotizacion_completa"] = False
    #    return state

    # 3. Slot filling LLM (si el mensaje no es "no sé")
    if not es_no_se(user_msg):

        agregar_mensajes_log(f"🔁no es nose ")

        # Slot filling LLM
        nuevos_slots = slot_filling_llm(user_msg)
        agregar_mensajes_log(f"🔁nuevos slots {json.dumps(nuevos_slots)}")
        
        # Si no hay tipo_repuesto, intenta extraerlo por palabra clave
        if not nuevos_slots.get("tipo_repuesto"):
            tipo_detectado = extraer_tipo_repuesto(user_msg)
            if tipo_detectado:
                nuevos_slots["tipo_repuesto"] = tipo_detectado
        
        # Si no hay marca/linea, usa fuzzy helper
        if not nuevos_slots.get("linea") or not nuevos_slots.get("marca"):
            agregar_mensajes_log(f"🔁buscando linea y marca{json.dumps(nuevos_slots)}")

            marca_detectada, linea_detectada = extraer_linea_y_marca_usuario(user_msg)
            if linea_detectada and not nuevos_slots.get("linea"):
                nuevos_slots["linea"] = linea_detectada.capitalize()
            if marca_detectada and not nuevos_slots.get("marca"):
                nuevos_slots["marca"] = marca_detectada
        
        # Ahora sí, fusiona con memoria_slots
        for k, v in nuevos_slots.items():
            if v is not None and v != "" and v != "no_sabe":
                memoria_slots[k] = v
        
        # Aplica deducción técnica
        memoria_slots = deducir_conocimiento(memoria_slots)
        guardar_memoria_slots(session, memoria_slots)
        faltan = campos_faltantes(memoria_slots)

        # Normaliza modelos si es posible
        modelo = nuevos_slots.get("linea")
        if modelo:
            modelo_key = modelo.lower().replace("-", "").replace(" ", "")
            if modelo_key in ALIAS_MODELOS:
                nuevos_slots["linea"] = ALIAS_MODELOS[modelo_key]

        for k, v in nuevos_slots.items():
            if v is not None and v != "" and v != "no_sabe":
                memoria_slots[k] = v

        memoria_slots = deducir_conocimiento(memoria_slots)
        guardar_memoria_slots(session, memoria_slots)
        faltan = campos_faltantes(memoria_slots)


    faltan = campos_faltantes(memoria_slots)
    if len(faltan) == 1 and es_no_se(user_msg):
        campo_faltante = faltan[0]
        memoria_slots[campo_faltante] = "no_sabe"
        guardar_memoria_slots(session, memoria_slots)
        agregar_mensajes_log(f"[DEBUG] Usuario marcó {campo_faltante} como no_sabe")

        # ⬇️ Verifica inmediatamente si puedes cotizar tras marcar "no_sabe"
        if es_cotizacion_completa(memoria_slots):
            resumen = []
            for campo in ["tipo_repuesto","marca", "linea", "serie_motor","año", "cc", "combustible"]:
                val = memoria_slots.get(campo)
                if val and val != "no_sabe":
                    resumen.append(f"{campo.capitalize()}: {val}")

            notificar_lead_via_whatsapp('50255105350', session, memoria_slots, state)
            session.modo_control = 'paused'
            session.pausa_hasta = datetime.now() + timedelta(hours=2)
            from config import db
            db.session.commit()
            resetear_memoria_slots(session)
            state["response_data"] = [{
                "messaging_product": "whatsapp",
                "to": state.get("phone_number"),
                "type": "text",
                "text": {"body": (
                    f"No te preocupes si no tienes el dato de {campo_faltante}. "
                    "¡Sigo con la cotización con lo que ya tenemos! 🚗\n\n"
                    f"✅ Datos recibidos:\n" + "\n".join(resumen) + "\n\n"
                    "🎉 ¡Listo! Ya tengo toda la información para cotizar. Un asesor te contactará muy pronto. Gracias por tu confianza. 🚗✨"
                )}
            }]
            state["cotizacion_completa"] = True
            return state

        # Si no puedes cotizar aún, solo muestra el mensaje empático
        state["response_data"] = [{
            "messaging_product": "whatsapp",
            "to": state.get("phone_number"),
            "type": "text",
            "text": {"body": f"No te preocupes si no tienes el dato de {campo_faltante}. ¡Sigo con la cotización con lo que ya tenemos! 🚗"}
        }]
        state["cotizacion_completa"] = False
        return state


    # 4. Si aún no se cumple ninguna ruta, pregunta SOLO lo necesario (pero nunca lo de "no_sabe")
    if not es_cotizacion_completa(memoria_slots):
        frases = ["🚗 ¡Gracias por la información!"]
        resumen = []
        for campo in ["marca", "linea", "año", "serie_motor", "tipo_repuesto", "cc", "combustible"]:
            val = memoria_slots.get(campo)
            if val and val != "no_sabe":
                resumen.append(f"{campo.capitalize()}: {val}")
        if resumen:
            frases.append("📝 Datos que tengo hasta ahora:\n" + "\n".join(resumen))
            frases.append("🔁 Si necesitas cambiar algo sólo dimelo:\n")
        for campo in faltan:
            pregunta = random.choice(PREGUNTAS_SLOTS.get(campo, [f"¿Me das el dato de {campo}?"]))
            frases.append(f"👉 {pregunta}")
        mensaje = "\n\n".join(frases)
        state["response_data"] = [{
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": state.get("phone_number"),
            "type": "interactive",
            "interactive":{
                "type":"button",
                "body": {
                    "text": mensaje
                },
                "footer": {
                    "text": ""
                },
                "action": {
                    "buttons":[
                        {
                            "type": "reply",
                            "reply":{
                                "id":"reiniciar_cotizacion",
                                "title":"❌ Cancelar/Salir"
                            }
                        }
                    ]
                }
            }
        }]
        state["cotizacion_completa"] = False
        return state

    # 5. Si ya tienes lo necesario para alguna ruta, ¡notifica, pausa, resetea y cierra!
    frases = ["🚗 ¡Gracias por la información!"]
    resumen = []
    for campo in ["marca", "linea", "año", "serie_motor", "tipo_repuesto", "cc", "combustible"]:
        val = memoria_slots.get(campo)
        if val and val != "no_sabe":
            resumen.append(f"{campo.capitalize()}: {val}")

    notificar_lead_via_whatsapp('50255105350', session, memoria_slots, state)
    session.modo_control = 'paused'
    session.pausa_hasta = datetime.now() + timedelta(hours=2)
    from config import db
    db.session.commit()
    resetear_memoria_slots(session)
    state["response_data"] = [{
        "messaging_product": "whatsapp",
        "to": state.get("phone_number"),
        "type": "text",
        "text": {"body": f"✅ Datos recibidos: \n "+ "\n".join(resumen) + "\n\n 🎉 ¡Listo! Ya tengo toda la información para cotizar. Un asesor te contactará muy pronto. Gracias por tu confianza. 🚗✨"}
    }]
    state["cotizacion_completa"] = True
    return state

def notificar_lead_via_whatsapp(numero_admin, session, memoria_slots, state):
    resumen = "\n".join([f"{k}: {v}" for k, v in memoria_slots.items() if v and v != "no_sabe"])
    mensaje = (
        f"🚗 *Nuevo Lead para Cotización*\n\n"
        f"📞 Cliente: {session.phone_number}\n"
        f"Datos:\n{resumen}\n\n"
        f"ID Sesión: {session.idUser}\n"
    )
    bot_enviar_mensaje_whatsapp({
        "messaging_product": "whatsapp",
        "to": numero_admin,
        "type": "text",
        "text": {"body": mensaje}
    }, state)


#def extraer_json_llm(texto):
#    """
#    Extrae un JSON de la respuesta del LLM, aunque no tenga llaves.
#    """
#    agregar_mensajes_log("🔁 Mensaje en extraer json llm", texto)
#
#    # 1. Busca el primer bloque {...}
#    try:
#        match = re.search(r"\{[\s\S]*\}", texto)
#        if match:
#            return json.loads(match.group())
#    except Exception as e:
#        print("❌ Error extrayendo JSON estándar:", e)
#
#    # 2. Si NO tiene {}, intenta armar el dict con pares clave:valor
#    try:
#        # Saca todas las líneas tipo: "clave": valor
#        pairs = re.findall(r'["\']?([\w_]+)["\']?\s*:\s*("?[^",\n]+?"?|null)', texto)
#        if pairs:
#            d = {}
#            for k, v in pairs:
#                v = v.strip().strip('"')
#                if v.lower() == "null":
#                    v = None
#                d[k] = v
#            return d
#    except Exception as e:
#        print("❌ Error extrayendo pares clave:valor:", e)
#
#    # 3. Si nada, regresa dict vacío
#    return {}
#
#
#CAMPOS_COTIZACION = ["categoria", "marca", "modelo", "anio"]  # Puedes añadir "serie", "combustible" si quieres
#
#PROMPT_EXTRACCION = """
#Eres un asistente de cotizaciones para repuestos de autos. 
#Recibe un mensaje y extrae SOLO la información relevante en formato JSON, dejando en null los campos que no puedas identificar. 
#Responde solo el JSON.
#
#Ejemplo:
#Entrada: "Quiero un alternador Toyota Hilux 2016 diésel"
#Salida:
#{{
#    "categoria": "alternador",
#    "marca": "Toyota",
#    "modelo": "Hilux",
#    "anio": "2016",
#    "serie": null,
#    "combustible": "diésel"
#}}
#
#Entrada: "{user_msg}"
#Salida:
#"""
#
#
#def asistente(state: BotState) -> BotState:
#    user_msg = state["user_msg"]
#    session = state.get("session")
#    session_id = session.idUser if session else None
#
#    # 1. Recuperar memoria de slots actual
#    memoria_actual = None
#    if session_id:
#        memorias = obtener_ultimas_memorias(session_id, limite=10)
#        for m in reversed(memorias):
#            if m.key == "slots_cotizacion":
#                try:
#                    memoria_actual = json.loads(m.value)
#                except:
#                    memoria_actual = None
#                break
#    if not memoria_actual:
#        memoria_actual = {campo: None for campo in CAMPOS_COTIZACION + ["serie", "combustible"]}
#
#    # 2. Enviar el mensaje al LLM para extraer datos
#    prompt = PROMPT_EXTRACCION.format(user_msg=user_msg)
#    response = model.invoke([HumanMessage(content=prompt)])
#    extraidos = extraer_json_llm(response.content)
#
#    # 3. Actualizar los slots
#    for campo in memoria_actual:
#        nuevo = extraidos.get(campo)
#        if nuevo:
#            memoria_actual[campo] = nuevo
#
#    # 4. Guardar slots actualizados
#    if session_id:
#        guardar_memoria(session_id, "slots_cotizacion", json.dumps(memoria_actual, ensure_ascii=False))
#
#    # 5. ¿Faltan datos?
#    faltantes = [campo for campo in CAMPOS_COTIZACION if not memoria_actual.get(campo)]
#    if faltantes:
#        pregunta = "Para cotizar necesito que me indiques: " + ", ".join(faltantes) + "."
#        state["response_data"] = [{
#            "messaging_product": "whatsapp" if state["source"] == "whatsapp" else "other",
#            "to": state.get("phone_number") or state.get("email"),
#            "type": "text",
#            "text": {"body": pregunta}
#        }]
#    else:
#        # 6. Consultar WooCommerce y responder
#        productos = woo_service.buscar_productos_con_filtros(memoria_actual)
#        if productos:
#            mensaje = woo_service.formatear_producto_whatsapp(productos[0])
#        else:
#            mensaje = "No encontramos ese producto exacto en inventario. ¿Quieres intentar con otra marca/modelo?"
#
#        state["response_data"] = [{
#            "messaging_product": "whatsapp" if state["source"] == "whatsapp" else "other",
#            "to": state.get("phone_number") or state.get("email"),
#            "type": "text",
#            "text": {"body": mensaje}
#        }]
#        # Si quieres limpiar la memoria de slots aquí puedes hacerlo
#
#    log_state(state, f"Slots actuales: {memoria_actual}")
#    return state


def send_messages(state: BotState) -> BotState:
    """Envía mensajes al canal correcto según la fuente."""
    session_id = state["session"].idUser if state.get("session") else None
    source = state.get("source")
    messages = state.get("response_data", [])

    #message_id = state.get("message_data", {}).get("id", "")  # Versión segura (evita KeyError)
    #si estás seguro de que message_data siempre existe y es un diccionario:
    message_id = state["message_data"]["id"]  # Directo (puede lanzar KeyError si falta algún campo)

    #agregar_mensajes_log(f"🔁 Iniciando envío de mensajes para {source}...", session_id)

    if not messages:
        log_state(state, "⚠️ No hay mensajes para enviar.")
        return state

    for index, mensaje in enumerate(messages):
        try:
            #log_state(state, f"📤 Enviando mensaje {index + 1} de {len(messages)}: {mensaje}")

            if source == "whatsapp":

                if message_id :

                    typing_indicator = ({
                      "messaging_product": "whatsapp",
                      "status": "read",
                      "message_id": message_id,
                      "typing_indicator": {
                        "type": "text"
                      }
                    })
                    bot_enviar_mensaje_whatsapp(typing_indicator, state)

                time.sleep(4)

                bot_enviar_mensaje_whatsapp(mensaje, state)


            elif source == "telegram":
                bot_enviar_mensaje_telegram(mensaje, state)
            elif source == "messenger":
                bot_enviar_mensaje_messenger(mensaje, state)
            elif source == "web":
                bot_enviar_mensaje_web(mensaje, state)
            else:
                log_state(state, f"❌ Fuente no soportada: {source}")

            #agregar_mensajes_log(json.dumps(mensaje, ensure_ascii=False), session_id)


            # Espera prudente entre mensajes para no saturar el canal (WhatsApp sobre todo)
            time.sleep(1.0)

        except Exception as e:
            error_msg = f"❌ Error enviando mensaje ({source}): {str(e)}"
            agregar_mensajes_log(error_msg, session_id)
            log_state(state, f"⏺️ ERROR en send_messages: {error_msg}")

    log_state(state, f"✅ Envío de mensajes completado para {source}")

    return state

# ------------------------------------------
# Funciones Auxiliares (Mantenidas de tu código original)
# ------------------------------------------

def merge_responses(state: BotState) -> BotState:
    """
    Combina los mensajes adicionales del middleware con las respuestas normales.
    Los mensajes adicionales van primero.
    """
    #agregar_mensajes_log(f"En merge_responses: {state}")

    additional = state.pop("additional_messages", [])
    main_responses = state.get("response_data", [])
    
    state["response_data"] = additional + main_responses

    log_state(state, f"⏺️ Saliendo de merge responses: {state['response_data']} at {now().isoformat()}")

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

def log_state(state: BotState, mensaje: str) -> None:
    # 1) append al estado en memoria
    state["logs"].append(mensaje)
    # 2) persiste en base de datos
    #agregar_mensajes_log(mensaje, state["session"].idUser if state.get("session") else None)


#def agregar_mensajes_log(texto: Union[str, dict, list], session_id: Optional[int] = None) -> None:
#    """Guarda un mensaje en memoria y en la base de datos."""
#    #agregar_mensajes_log(f"En agregar_mensajes_log: {state}")
#
#    try:
#        texto_str = json.dumps(texto, ensure_ascii=False) if isinstance(texto, (dict, list)) else str(texto)
#        
#        with db.session.begin():
#            nuevo_registro = Log(texto=texto_str, session_id=session_id)
#            db.session.add(nuevo_registro)
#    except Exception as e:
#        fallback = f"[ERROR LOG] No se pudo guardar: {str(texto)[:200]}... | Error: {str(e)}"
#        try:
#            with db.session.begin():
#                fallback_registro = Log(texto=fallback, session_id=session_id)
#                db.session.add(fallback_registro)
#        except Exception as e2:
#            pass

def agregar_mensajes_log(texto: Union[str, dict, list], session_id: Optional[int] = None) -> None:
    """Guarda un mensaje en memoria y en la base de datos."""
    try:
        texto_str = json.dumps(texto, ensure_ascii=False) if isinstance(texto, (dict, list)) else str(texto)
        log = Log(texto=texto_str, session_id=session_id)
        db.session.add(log)
        db.session.commit()  # <-- Hacer commit aquí de forma directa
    except Exception as e:
        fallback = f"[ERROR LOG] No se pudo guardar: {str(texto)[:200]}... | Error: {str(e)}"
        try:
            fallback_log = Log(texto=fallback)
            db.session.add(fallback_log)
            db.session.commit()
        except Exception as e2:
            print("❌ ERROR al guardar el error del log:", e2)

def bot_enviar_mensaje_whatsapp(data: Dict[str, Any], state: BotState) -> Optional[bytes]:

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"{Config.WHATSAPP_TOKEN}"
    }

    try:
        connection = http.client.HTTPSConnection("graph.facebook.com")
        json_data = json.dumps(data)
        connection.request("POST", f"/v22.0/{Config.PHONE_NUMBER_ID}/messages", json_data, headers)
        agregar_mensajes_log(f"✅ Mensaje enviado a whatsapp: {state['phone_number']}, {json_data}")
        log_state(state, f"⏺️ Mensaje enviado en bot_enviar_mensaje_whatsapp: {data}")

        response = connection.getresponse()
        return response.read()
    except Exception as e:
        log_state(state, f"⏺️ Error enviando a WhatsApp: {str(e)}")
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
                            {"type": "reply", "reply": {"id": "1", "title": "🔧 Cotizar"}},
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

def manejar_producto_interesado(number: str, mensaje: str) -> List[Dict[str, Any]]:
    try:
        # Extraer URL y nombre del producto
        patron = r"Hola, estoy interesado en el producto: (.*?) que se encuentra en (https?://[^\s]+)"
        coincidencia = re.search(patron, mensaje.strip())
        
        if not coincidencia:
            return [{
                "messaging_product": "whatsapp",
                "to": number,
                "type": "text",
                "text": {"body": "❌ No logré identificar el producto en tu mensaje. Por favor revisa el formato."}
            }]

        nombre_producto = coincidencia.group(1).strip()
        url_producto = coincidencia.group(2).strip()

        # Intentar buscar por URL primero
        producto = woo_service.obtener_producto_por_url(url_producto)

        if not producto:
            # Si no se encuentra, intentar por nombre
            producto = woo_service.buscar_producto_por_nombre(nombre_producto)

        if not producto:
            return [{
                "messaging_product": "whatsapp",
                "to": number,
                "type": "text",
                "text": {"body": f"⚠️ No encontré el producto *{nombre_producto}*. Por favor verifica el enlace o nombre."}
            }]

        # Verificar disponibilidad
        stock_status = producto.get('stock_status', '')
        if stock_status != 'instock':
            return [{
                "messaging_product": "whatsapp",
                "to": number,
                "type": "text",
                "text": {"body": f"⛔ El producto *{producto['name']}* no se encuentra disponible actualmente."}
            }]

        # Formatear respuesta
        mensaje_formateado = woo_service.formatear_producto_whatsapp(producto)

        return [{
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {"preview_url": True, "body": mensaje_formateado}
        }]

    except Exception as e:
        print(f"Error en manejar_producto_interesado: {str(e)}")
        return [{
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {"body": "❌ Ocurrió un error al procesar tu solicitud. Por favor intenta más tarde."}
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
# En la definición de tu grafo (workflow)
workflow.add_node("handle_cotizacion_slots", handle_cotizacion_slots)
# --- 2. Enlaces (Edges) ---
workflow.add_edge("load_session", "pre_validaciones")
workflow.add_edge("pre_validaciones", "load_product_flow")
workflow.add_edge("load_product_flow", "handle_product_flow")
workflow.add_edge("handle_product_flow", "handle_special_commands")

# Condicional entre comandos y asistente
def enrutar_despues_comandos(state: BotState) -> str:
    if state.get("skip_processing", False):
        return "merge_responses"
    if state.get("response_data"):
        return "merge_responses"
    return "handle_cotizacion_slots"

workflow.add_conditional_edges("handle_special_commands", enrutar_despues_comandos)
#workflow.add_edge("handle_special_commands", "handle_cotizacion_slots")

def ruta_despues_cotizacion(state: dict) -> str:
    if state.get("cotizacion_completa", False):
        return "merge_responses"
    return "asistente"

workflow.add_conditional_edges("handle_cotizacion_slots", ruta_despues_cotizacion)

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
        registros = Log.query.order_by(Log.fecha_y_hora.desc()).limit(500).all()
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

    try:
        memories = Memory.query.order_by(Memory.created_at.desc()).limit(100).all()
    except Exception as e:
        memories = []
        agregar_mensajes_log(f"Error cargando memorias: {str(e)}")

    try:
        config = Configuration.query.order_by(Configuration.key.asc()).all()
    except Exception as e:
        config = []
        agregar_mensajes_log(f"Error cargando configuración: {str(e)}")

    return render_template(
        'index.html',
        registros=registros,
        users=users,
        products=products,
        memories=memories,
        config=config
    )

#from message_validator import MessageValidator


#Token de verificacion para la configuracion
TOKEN_WEBHOOK_WHATSAPP = f"{Config.TOKEN_WEBHOOK_WHATSAPP}"

#@flask_app.route('/webhook', methods=['GET','POST'])
#def webhook():
#    if request.method == 'GET':
#        challenge = verificar_token_whatsapp(request)
#        return challenge
#    elif request.method == 'POST':
#        response = recibir_mensajes(request)
#        return response

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

        #try:
        #    #agregar_mensajes_log(json.dumps(data, ensure_ascii=False))
        #    # Guardar el evento recibido
        #    agregar_mensajes_log(f"📥 Entrada cruda WhatsApp: {json.dumps(data)}")

        #except TypeError as e:
        #    agregar_mensajes_log(f"[Log ignorado] No se pudo serializar data: {str(e)}")

        if not data or 'entry' not in data:
            agregar_mensajes_log("Error: JSON sin 'entry' o 'Data'")
            return jsonify({'message': 'EVENT_RECEIVED'}), 401

        # Filtro inicial: solo humanos
        #if not is_human_message("whatsapp", data):
        #    agregar_mensajes_log("🚫 Evento ignorado: no es mensaje humano", None)
        #    return jsonify({'status': 'ignored', 'reason': 'non_human_event'})

        entry = data['entry'][0]
        changes = entry.get('changes', [])[0]
        value = changes.get('value', {})
        messages_list = value.get('messages', [])

        if messages_list:
            message = messages_list[0]
            phone_number = message.get("from")
            
            # Verificar si el usuario está bloqueado
            block_result = block("whatsapp", phone_number)
            if block_result.get("status") == "blocked":
                agregar_mensajes_log(f"Usuario bloqueado intentó contactar: {phone_number}")
                return jsonify({'status': 'blocked', 'message': 'Usuario bloqueado'}), 200

            # Crea estado inicial
            initial_state = {
                "phone_number":phone_number,
                "user_msg": message,
                "response_data": [],
                "message_data": message,
                "logs": [],
                "source": "whatsapp"
            }
            #agregar_mensajes_log(f"📥 Initial State: {json.dumps(initial_state)}")

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

            agregar_mensajes_log(f"📥 Mensaje recibido initial_state: {json.dumps(initial_state)}")

            # Ejecuta el flujo
            #app_flow.invoke(initial_state)
            final_state = app_flow.invoke(initial_state)

            # Ahora sí tienes todos los logs en final_state["logs"]
            print(final_state["logs"])
            # O persístelos de una vez:
            #for msg in final_state["logs"]:
            #    agregar_mensajes_log({"final_log": msg}, final_state["session"].idUser)

            return jsonify({'status': 'processed'}), 200
        
        else:
            return jsonify({'status': 'ignored', 'reason': 'no_messages'}), 500

        #return jsonify({'message': 'EVENT_RECEIVED'})

    except Exception as e:
        error_msg = f"❌ Error procesando webhook WhatsApp: {str(e)}"
        agregar_mensajes_log(error_msg)
        return jsonify({'status': 'error', 'message': error_msg}), 500

@flask_app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return verificar_token_whatsapp(request)
    elif request.method == 'POST':
        try:
            data = request.get_json()

            # Procesar en segundo plano para no bloquear la respuesta del webhook
            threading.Thread(target=procesar_mensaje_entrada, args=(data,)).start()


            #try:
            #    whatsapp_message_id = (
            #        data.get('entry', [{}])[0]
            #        .get('changes', [{}])[0]
            #        .get('value', {})
            #        .get('messages', [{}])[0]
            #        .get('id')
            #    )
#
            #    #if not whatsapp_message_id:
            #    #    raise ValueError(f"No se encontró el WhatsApp Message ID en el webhook :  {data}")
#
            #except (IndexError, AttributeError, KeyError) as e:
            #    print(f"Error extrayendo el message_id: {e}")
            #    whatsapp_message_id = None
#
            #if whatsapp_message_id :
            #    # Respuesta inmediata a WhatsApp para evitar reintentos
            #    fake_state: BotState = {
            #        "phone_number": "unknown",  # o extraerlo del webhook si está disponible
            #        "user_msg": "",
            #        "response_data": [],
            #        "logs": [],
            #        "source": "whatsapp",
            #        "additional_messages": [],
            #        "session": None,
            #        "flujo_producto": None,
            #        "message_data": None,
            #    }
#
            #    typing_indicator = ({
            #      "messaging_product": "whatsapp",
            #      "status": "read",
            #      "message_id": whatsapp_message_id,
            #      "typing_indicator": {
            #        "type": "text"
            #      }
            #    })
            #    bot_enviar_mensaje_whatsapp(typing_indicator, fake_state)

            return jsonify({'status': 'received'}), 200

        except Exception as e:
            error_msg = f"❌ Error al recibir webhook: {str(e)}"
            agregar_mensajes_log(error_msg)
            return jsonify({'status': 'error', 'message': error_msg}), 500


def procesar_mensaje_entrada(data):
    from app import flask_app  # Asegúrate que esta es tu instancia Flask global

    with flask_app.app_context():
        try:
            if not data or 'entry' not in data:
                agregar_mensajes_log(f"⚠️ Entrada inválida: falta 'entry' : {data}")
                return

            entry = data['entry'][0]
            changes = entry.get('changes', [])[0]
            value = changes.get('value', {})
            messages_list = value.get('messages', [])

            if not messages_list:
                #agregar_mensajes_log(f"⚠️ No hay mensajes en el evento recibido : {data} ")
                return

            message = messages_list[0]
            phone_number = message.get("from")
            message_id = message.get("id")

            if ya_esta_procesado(message_id):
                agregar_mensajes_log(f"⚠️ Mensaje duplicado detectado y omitido: {message_id}")
                return  # No procesar de nuevo
            
            # Verificar si el usuario está bloqueado
            #block_result = block("whatsapp", phone_number)
            block_result = block("whatsapp", message)

            if block_result.get("status") == "blocked":
                agregar_mensajes_log(f"⛔ Usuario o mensaje bloqueado intentó contactar: {phone_number} > {data}")
                return

            # Estado inicial del bot
            initial_state = {
                "phone_number": phone_number,
                "user_msg": message,
                "response_data": [],
                "message_data": message,
                "logs": [],
                "source": "whatsapp"
            }

            # Procesamiento de tipo de mensaje
            msg_type = message.get("type")

            if msg_type == "interactive":
                interactive = message.get("interactive", {})
                tipo_interactivo = interactive.get("type")

                if tipo_interactivo == "button_reply":
                    text = interactive.get("button_reply", {}).get("id")
                    if text:
                        initial_state["user_msg"] = text

                elif tipo_interactivo == "list_reply":
                    text = interactive.get("list_reply", {}).get("id")
                    if text:
                        initial_state["user_msg"] = text

            elif msg_type == "text":
                text = message.get("text", {}).get("body")
                if text:
                    initial_state["user_msg"] = text

            agregar_mensajes_log(f"Mensaje completo recibido: {data} \n\n 📥 Mensaje recibido initial_state: {json.dumps(initial_state)}")

            # Ejecutar el flujo del boT
            final_state = app_flow.invoke(initial_state)

            # Guardar todos los logs una vez finalizado el flujo
            #for msg in final_state["logs"]:
            #    agregar_mensajes_log({"final_log": msg}, final_state["session"].idUser)

        except Exception as e:
            agregar_mensajes_log(f"❌ Error en procesar_mensaje_entrada: {str(e)}")


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
        
        #app_flow.invoke(initial_state)
        final_state = app_flow.invoke(initial_state)

        # Ahora sí tienes todos los logs en final_state["logs"]
        print(final_state["logs"])
        # O persístelos de una vez:
        for msg in final_state["logs"]:
            agregar_mensajes_log({"final_log": msg}, final_state["session"].idUser)

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

# --- PANEL WEB DE CONFIGURACIONES ---
from flask import render_template, request, redirect, jsonify
from models import Configuration
from config import db

@flask_app.route('/configuracion', methods=['GET', 'POST'])
def configuracion():
    if request.method == 'POST':
        key = request.form.get('key')
        value = request.form.get('value')
        descripcion = request.form.get('descripcion', '')

        if key and value:
            config_item = Configuration.query.filter_by(key=key).first()
            if not config_item:
                config_item = Configuration(key=key)
                db.session.add(config_item)
            config_item.value = value
            config_item.descripcion = descripcion
            db.session.commit()
        return redirect('/configuracion')

    configuraciones = Configuration.query.order_by(Configuration.key.asc()).all()
    return render_template('configuracion.html', config=configuraciones)

@flask_app.route('/delete-config', methods=['POST'])
def delete_config():
    config_id = request.form.get('id')
    try:
        config_item = Configuration.query.get(config_id)
        if config_item:
            db.session.delete(config_item)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
    return redirect('/configuracion')

@flask_app.route('/update-config-inline', methods=['POST'])
def update_config_inline():
    data = request.get_json()
    config_id = data.get('id')
    value = data.get('value')
    try:
        config_item = Configuration.query.get(config_id)
        if config_item:
            config_item.value = value
            db.session.commit()
            return jsonify({"message": "✅ Configuración actualizada correctamente"})
        else:
            return jsonify({"message": "❌ Configuración no encontrada"}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"❌ Error interno: {str(e)}"}), 500

@flask_app.route('/sincronizar-woocommerce', methods=['POST'])
def sincronizar_woocommerce():
    from woocommerce_service import WooCommerceService
    from models import Configuration
    import json

    woo = WooCommerceService()

    def guardar_config(key, value, descripcion=""):
        config_item = Configuration.query.filter_by(key=key).first()
        if not config_item:
            config_item = Configuration(key=key, descripcion=descripcion)
            db.session.add(config_item)
        config_item.value = json.dumps(value, ensure_ascii=False)
        db.session.commit()

    try:
        # Categorías
        categorias = woo.obtener_categorias()
        categorias_lista = [{"id": c["id"], "nombre": c["name"], "slug": c["slug"]} for c in categorias]
        guardar_config("categorias_disponibles", categorias_lista, "Categorías WooCommerce")

        # Atributos y términos (marca, motor, etc.)
        atributos = woo.obtener_atributos()
        for atributo in atributos:
            nombre_atributo = atributo["name"].lower()
            terminos = woo.obtener_terminos_atributo(atributo["id"])
            if terminos:
                terminos_lista = [{"id": t["id"], "nombre": t["name"], "slug": t["slug"]} for t in terminos]
                guardar_config(f"{nombre_atributo}_disponibles", terminos_lista, f"Términos atributo {nombre_atributo}")

        # Etiquetas
        etiquetas = woo.obtener_etiquetas()
        etiquetas_lista = [{"id": t["id"], "nombre": t["name"], "slug": t["slug"]} for t in etiquetas]
        guardar_config("etiquetas_disponibles", etiquetas_lista, "Etiquetas de productos WooCommerce")

        return jsonify({"ok": True, "message": "Sincronización completada"}), 200
    except Exception as e:
        return jsonify({"ok": False, "message": f"Error al sincronizar: {str(e)}"}), 500


@flask_app.route('/usuarios')
def vista_usuarios():
    tipo = request.args.get('tipo')  # ?tipo=admin
    if tipo:
        usuarios = UserSession.query.filter_by(tipo_usuario=tipo).order_by(UserSession.last_interaction.desc()).all()
    else:
        usuarios = UserSession.query.order_by(UserSession.last_interaction.desc()).all()
    return render_template('users.html', usuarios=usuarios, tipo_filtro=tipo)

@flask_app.route('/update-usuario-inline', methods=['POST'])
def update_usuario_inline():
    data = request.get_json()
    user_id = data.get('id')
    nombre = data.get('nombre')
    apellido = data.get('apellido')
    tipo_usuario = data.get('tipo_usuario')

    try:
        user = UserSession.query.get(user_id)
        if user:
            user.nombre = nombre
            user.apellido = apellido
            user.tipo_usuario = tipo_usuario
            db.session.commit()
            return jsonify({"message": "✅ Usuario actualizado correctamente"})
        else:
            return jsonify({"message": "❌ Usuario no encontrado"}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"❌ Error interno: {str(e)}"}), 500

@flask_app.route('/crear-usuario', methods=['POST'])
def crear_usuario():
    phone_number = request.form.get('phone_number')
    nombre = request.form.get('nombre')
    apellido = request.form.get('apellido')
    tipo_usuario = request.form.get('tipo_usuario', 'cliente')

    if not phone_number or not nombre or not apellido:
        return "❌ Faltan campos requeridos", 400

    try:
        existente = UserSession.query.filter_by(phone_number=phone_number).first()
        if existente:
            return "❌ El usuario con ese número ya existe", 400

        nuevo = UserSession(
            phone_number=phone_number,
            nombre=nombre,
            apellido=apellido,
            tipo_usuario=tipo_usuario,
            last_interaction=now()
        )
        db.session.add(nuevo)
        db.session.commit()
        return redirect('/usuarios')
    except Exception as e:
        db.session.rollback()
        return f"❌ Error creando usuario: {str(e)}", 500

# ------------------------------------------
# Inicialización
# ------------------------------------------

#with flask_app.app_context():
#    db.create_all()
with flask_app.app_context():
    db.create_all()

    from init_data import inicializar_todo
    inicializar_todo()


if __name__ == '__main__':
    flask_app.run(host='0.0.0.0', port=80, debug=True)