from typing import TypedDict, Optional, List, Dict, Any, Union
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from config import db, Config
from models import UserSession, Log, ProductModel, Configuration, Memory, MensajeBot, KnowledgeBase, UsuarioBloqueado, LLMConfig
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
#from pytz import timezone
from config import now,GUATEMALA_TZ
import re
import threading
from collections import deque
from langchain_groq import ChatGroq
import random
#import difflib
from rapidfuzz import fuzz, process
from init_data import INTENCIONES_BOT_DEFECTO, PROMPT_ASISTENTE_DEFECTO, PROMPT_SLOT_FILL_DEFECTO
import unicodedata
from init_data import inicializar_todo

# Instancia global del servicio
woo_service = WooCommerceService()

def get_llm_config_list():
    # Devuelve todas las configuraciones activas ordenadas por prioridad (para fallback)
    configs = LLMConfig.query.filter_by(status="active").order_by(LLMConfig.prioridad.asc()).all()
    return configs

from langchain_openai import ChatOpenAI
#from langchain_groq import ChatGroq   # Si usas Groq, importa el correcto

def create_llm_instance(config):
    provider = config.provider
    model = config.model
    temperature = config.temperature
    max_tokens = config.max_tokens

    if provider == "deepseek":
        api_key = Config.DEEPSEEK_API_KEY
        base_url = "https://api.deepseek.com/v1"
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens
        )
    elif provider == "openai":
        api_key = Config.OPENAI_API_KEY
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens
        )
    # Agrega aquí otros proveedores
    #elif provider == "groq":
    #    api_key = Config.GROQ_API_KEY
    #    return ChatGroq(...)

    else:
        raise Exception(f"Proveedor LLM no soportado: {provider}")

def run_llm_with_fallback(prompt):
    configs = get_llm_config_list()
    error = None
    for config in configs:
        try:
            llm = create_llm_instance(config)
            response = llm.invoke([HumanMessage(content=prompt)])
            return response.content
        except Exception as e:
            # Loguea error, intenta el siguiente
            error = str(e)
            print(f"[LLM ERROR] {config.provider} - {config.model}: {error}")
            continue
    # Si ninguno respondió, lanza el último error
    raise Exception(f"Ningún LLM respondió correctamente. Último error: {error}")

# Configuración de DeepSeek
#deepseek_key = os.environ["DEEPSEEK_API_KEY"]
#deepseek_key = f"{Config.DEEPSEEK_API_KEY}"
#model = ChatOpenAI(
#    model="deepseek-chat",
#    api_key=deepseek_key,
#    base_url="https://api.deepseek.com/v1",
#    temperature=0.5,
#    max_tokens=100,
#)

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

def obtener_mensaje_bot(tipo, mensaje_default=None, canal='whatsapp', idioma='es'):
    # Busca primero por canal específico
    mensajes = MensajeBot.query.filter_by(tipo=tipo, activo=True, canal=canal, idioma=idioma).all()
    # Si no encuentra, busca globales 'all'
    if not mensajes:
        mensajes = MensajeBot.query.filter_by(tipo=tipo, activo=True, canal='all', idioma=idioma).all()
    if mensajes:
        return random.choice(mensajes).mensaje
    return mensaje_default

def cargar_usuarios_bloqueados():
    # Devuelve un dict: {'whatsapp': [nros], 'telegram': [ids], ...}
    res = {}
    for user in UsuarioBloqueado.query.filter_by(activo=True).all():
        if user.tipo not in res:
            res[user.tipo] = []
        res[user.tipo].append(user.identificador)
    return res

def cargar_tipos_mensajes_bloqueados():
    config = Configuration.query.filter_by(key="TIPOS_MENSAJES_BLOQUEADOS").first()
    if config and config.value:
        return json.loads(config.value)
    return {}


def block(source, message):
    BLOQUEADOS = cargar_usuarios_bloqueados()
    TIPOS_BLOQUEADOS = cargar_tipos_mensajes_bloqueados()

    phone_number = message.get("from")
    type_msg = message.get("type")

    if phone_number in BLOQUEADOS.get(source, []):
        error_msg = f"❌ Usuario bloqueado: {phone_number} ({source})"
        agregar_mensajes_log(error_msg)
        return {"status": "blocked", "message": error_msg}

    if type_msg in TIPOS_BLOQUEADOS.get(source, []):
        error_msg = f"❌ Tipo de mensaje bloqueado: {type_msg} ({source})"
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
    try:
        # Serializa si es necesario
        if isinstance(valor, (dict, list)):
            valor_guardar = json.dumps(valor, ensure_ascii=False)
        else:
            valor_guardar = str(valor)

        # Casos especiales: "assistant" y "user" SIEMPRE crean nueva memoria
        if clave in ["assistant", "user"]:
            mem = Memory(session_id=session_id, key=clave, value=valor_guardar)
            db.session.add(mem)
            db.session.commit()
            return

        # Caso slots_cotizacion: upsert (actualiza si existe, sino crea)
        elif clave == "slots_cotizacion":
            mem = Memory.query.filter_by(session_id=session_id, key=clave).first()
            if not mem:
                mem = Memory(session_id=session_id, key=clave)
                db.session.add(mem)
            mem.value = valor_guardar
            db.session.commit()
            return

        # Otros: puedes dejar upsert (igual que slots) o solo crear nuevo (elige)
        else:
            mem = Memory.query.filter_by(session_id=session_id, key=clave).first()
            if not mem:
                mem = Memory(session_id=session_id, key=clave)
                db.session.add(mem)
            mem.value = valor_guardar
            db.session.commit()
    except Exception as e:
        error_text = f"❌ Error al guardar memoria ({clave}): {str(e)}"
        agregar_mensajes_log(error_text, session_id)

def obtener_ultimas_memorias(session_id, limite=6):
    """
    Devuelve una lista de los últimos 'limite' objetos Memory de tipo 'user' o 'assistant'
    para esa sesión, ordenados cronológicamente.
    Si ocurre un error, retorna lista vacía.
    """
    try:
        memorias = (
            Memory.query
            .filter(
                Memory.session_id == session_id,
                Memory.key.in_(["user", "assistant"])
            )
            .order_by(Memory.created_at.desc())
            .limit(limite)
            .all()
        )
        return list(reversed(memorias))  # Para orden cronológico
    except Exception as e:
        error_text = f"[ERROR] obtener_ultimas_memorias ({session_id}): {e}"
        print(error_text)
        # agregar_mensajes_log(error_text, session_id)
        return []


def cargar_memoria_slots(session):
    """
    Devuelve un diccionario con los slots de cotización guardados para la sesión dada.
    Si no encuentra nada, devuelve {}.
    """
    try:
        mem = Memory.query.filter_by(session_id=session.idUser, key='slots_cotizacion').first()
        # Log opcional
        # agregar_mensajes_log(f"[DEBUG] cargar_memoria_slots para session {getattr(session, 'idUser', None)} devuelve: {mem.value if mem else None}")
        if mem and mem.value:
            return json.loads(mem.value)
    except Exception as e:
        error_text = f"[ERROR] cargar_memoria_slots (session {getattr(session, 'idUser', None)}): {e}"
        print(error_text)
        # agregar_mensajes_log(error_text, getattr(session, 'idUser', None))
    return {}

def resetear_memoria_slots(session):
    from models import Memory, db
    mem = Memory.query.filter_by(session_id=session.idUser, key='slots_cotizacion').first()
    if mem:
        mem.value = "{}"
        db.session.commit()

def actualizar_slots_memoria(memoria_slots, nuevos_slots, user_msg, campos_protegidos=["marca", "linea"]):
    user_msg_lower = user_msg.lower()
    for k, v in nuevos_slots.items():
        if v is not None and v != "" and v != "no_sabe":
            if k in campos_protegidos:
                # Permitir corrección si el usuario lo indica explícitamente
                if (
                    memoria_slots.get(k) in [None, "", "no_sabe"]
                    or f"{k}" in user_msg_lower
                    or ("marca" in user_msg_lower and k == "marca")
                    or ("modelo" in user_msg_lower and k == "linea")
                    or ("línea" in user_msg_lower and k == "linea")
                ):
                    memoria_slots[k] = v
                # De lo contrario, NO sobreescribe
            else:
                memoria_slots[k] = v
    return memoria_slots

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

HORARIOS_DEFECTO = {
    0: "08:00-17:30",  # Lunes
    1: "08:00-17:30",
    2: "08:00-17:30",
    3: "08:00-17:30",
    4: "08:00-17:30",
    5: "08:00-12:30",  # Sábado
    6: None            # Domingo
}
# 1. Días festivos (fijos y por año específico)
#DIAS_FESTIVOS_DEFECTO = [
#    "01-01",         # Año Nuevo (cada año)
#    "05-01",         # Día del Trabajo (cada año)
#    "12-25",         # Navidad (cada año)
#    "2025-04-17",    # Jueves Santo (sólo 2025)
#    "2025-12-31"     # Fin de año (sólo 2025)
#]

def cargar_horario_dia(dia_semana):
    dias = [
        "HORARIO_LUNES", "HORARIO_MARTES", "HORARIO_MIERCOLES", "HORARIO_JUEVES",
        "HORARIO_VIERNES", "HORARIO_SABADO", "HORARIO_DOMINGO"
    ]
    key = dias[dia_semana]
    config = Configuration.query.filter_by(key=key).first()
    if config and config.value:
        return config.value
    return HORARIOS_DEFECTO.get(dia_semana)

def cargar_dias_festivos():
    config = Configuration.query.filter_by(key="DIAS_FESTIVOS").first()
    if config and config.value:
        try:
            return set(json.loads(config.value))
        except Exception:
            # Soporta CSV si hay error
            return set([d.strip() for d in config.value.split(",") if d.strip()])
    # Si falla, regresa los de inicialización
    return set(["01-01", "05-01", "12-25", "2025-04-17", "2025-12-31"])

def es_dia_festivo(fecha: datetime) -> bool:
    dias_festivos = cargar_dias_festivos()
    fecha_str = fecha.strftime("%Y-%m-%d")
    fecha_mmdd = fecha.strftime("%m-%d")
    return fecha_str in dias_festivos or fecha_mmdd in dias_festivos

def obtener_mensaje_festivo(fecha, canal='whatsapp', idioma='es'):
    tipo1 = f"alerta_dia_festivo_{fecha.strftime('%m-%d')}"
    tipo2 = f"alerta_dia_festivo_{fecha.strftime('%Y-%m-%d')}"
    mensaje = obtener_mensaje_bot(tipo2, None, canal=canal, idioma=idioma)
    if not mensaje:
        mensaje = obtener_mensaje_bot(tipo1, None, canal=canal, idioma=idioma)
    if not mensaje:
        mensaje = obtener_mensaje_bot(
            "alerta_dia_festivo",
            "🎉 Lo sentimos en este momento no podemos atenderte, estamos en feriado nacional. Puedes dejar tu mensaje y te responderemos en el próximo día hábil.",
            canal=canal,
            idioma=idioma
        )
    return mensaje

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

    # --- HORARIO DESDE CONFIG --- 
    HORARIO = {}
    for i in range(7):
        h = cargar_horario_dia(i)
        if h and '-' in str(h):
            h_ini, h_fin = h.split("-")
        else:
            h_ini = h_fin = None
        HORARIO[i] = (h_ini, h_fin)

    dia = ahora.weekday()
    h_ini_str, h_fin_str = HORARIO.get(dia, (None, None))
    dentro_horario = False

    if h_ini_str and h_fin_str:
        h_ini = GUATEMALA_TZ.localize(datetime.combine(ahora.date(), datetime.strptime(h_ini_str, "%H:%M").time()))
        h_fin = GUATEMALA_TZ.localize(datetime.combine(ahora.date(), datetime.strptime(h_fin_str, "%H:%M").time()))
        dentro_horario = h_ini <= ahora <= h_fin

    try:
        mostrar_alerta = False
        tipo_mensaje = None

        # ⏰ Controla frecuencia de alertas, tanto para feriado como fuera de horario
        alerta_permitida = True
        if session:
            ultima_alerta = session.ultima_alerta_horario or datetime.min.replace(tzinfo=GUATEMALA_TZ)
            if ultima_alerta.tzinfo is None:
                ultima_alerta = GUATEMALA_TZ.localize(ultima_alerta)
            # Si han pasado más de 1 hora desde la última alerta, permite mostrar
            if (ahora - ultima_alerta) < timedelta(hours=1):
                alerta_permitida = False

        if es_dia_festivo(ahora):
            if alerta_permitida:
                mostrar_alerta = True
                tipo_mensaje = "feriado"
        elif not dentro_horario:
            if alerta_permitida:
                mostrar_alerta = True
                tipo_mensaje = "fuera_horario"

        if mostrar_alerta:
            if tipo_mensaje == "feriado":
                mensaje_alerta = obtener_mensaje_festivo(ahora, canal=source)
            else:
                mensaje_alerta = obtener_mensaje_bot(
                    "alerta_fuera_horario",
                    "🕒 Gracias por comunicarte con nosotros. En este momento estamos fuera de nuestro horario de atención.\n\n💬 Puedes continuar usando nuestro asistente y nuestro equipo te atenderá lo más pronto posible.",
                    canal=source
                )
            state["additional_messages"].append({
                "messaging_product": "whatsapp" if source == "whatsapp" else "other",
                "to": phone_or_id,
                "type": "text",
                "text": {"body": mensaje_alerta}
            })
            # 🔄 Marca hora de la última alerta solo si fue mostrada
            if session:
                session.ultima_alerta_horario = ahora
                db.session.commit()
                log_state(state, "⏰ Alerta fuera de horario/feriado enviada y hora actualizada.")

    except Exception as e:
        db.session.rollback()
        log_state(state, f"❌ Error al guardar alerta de horario: {str(e)}")

    # ... (tu lógica de bienvenida y resto sigue igual)

    # ... tu código de bienvenida, etc. ...

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
            #msg = (
            #    "👋 ¡Bienvenido(a) a Intermotores! Estamos aquí para ayudarte a encontrar el repuesto ideal para tu vehículo. 🚗 \n\n🗒️ Consulta nuestro menú."
            #    if kind == "nueva" else
            #    "👋 ¡Hola de nuevo! Gracias por contactar a Intermotores. ¿En qué podemos ayudarte hoy? 🚗\n\n🗒️Consulta nuestro menú."
            #)

            if kind == "nueva":
                msg = obtener_mensaje_bot(
                    "bienvenida",
                    "👋 ¡Bienvenido(a) a Intermotores Guatemala! Estamos aquí para ayudarte a encontrar el repuesto ideal para tu vehículo. 🚗\n\n🗒️ Consulta nuestro menú.",
                    canal=source
                )
            else:
                msg = obtener_mensaje_bot(
                    "re_bienvenida",
                    "👋 ¡Hola de nuevo! Gracias por contactar a Intermotores Guatemala. ¿En qué podemos ayudarte hoy? 🚗\n\n🗒️ Consulta nuestro menú.",
                    canal=source
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

def cargar_intenciones_bot():
    config = Configuration.query.filter_by(key="INTENCIONES_BOT").first()
    if config and config.value:
        try:
            return json.loads(config.value)
        except Exception:
            pass
    return INTENCIONES_BOT_DEFECTO

def cargar_threshold_intencion():
    config = Configuration.query.filter_by(key="INTENCION_THRESHOLD").first()
    if config and config.value:
        try:
            return int(config.value)
        except Exception:
            pass
    return 90  # Valor por defecto


def quitar_acentos(texto):
    """Elimina acentos/tildes y normaliza el texto a ASCII básico"""
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )

def detectar_intencion(mensaje, session_id=None):
    threshold = cargar_threshold_intencion()
    mensaje_norm = quitar_acentos(mensaje.lower())
    INTENCIONES_BOT = cargar_intenciones_bot()
    mejor_score = 0
    mejor_match = None
    mejor_intencion = None

    for intencion, variantes in INTENCIONES_BOT.items():
        for variante in variantes:
            variante_norm = quitar_acentos(variante.lower())
            # Coincidencia exacta
            if variante_norm in mensaje_norm:
                log_text = f"[INTENCIÓN] Coincidencia EXACTA con '{variante}' para intención '{intencion}'"
                if session_id:
                    agregar_mensajes_log(log_text, session_id)
                else:
                    print(log_text)
                return intencion
            # Fuzzy matching
            score = fuzz.partial_ratio(variante_norm, mensaje_norm)
            if score > mejor_score:
                mejor_score = score
                mejor_match = variante
                mejor_intencion = intencion
            if score >= threshold:
                log_text = f"[INTENCIÓN] Coincidencia FUZZY con '{variante}' (score: {score}) para intención '{intencion}'"
                if session_id:
                    agregar_mensajes_log(log_text, session_id)
                else:
                    print(log_text)
                return intencion

    if mejor_match and mejor_score > 0:
        log_text = f"[INTENCIÓN] Mejor coincidencia: '{mejor_match}' para '{mensaje}' (score: {mejor_score}), intención '{mejor_intencion}'"
        if session_id:
            agregar_mensajes_log(log_text, session_id)
        else:
            print(log_text)

    return None


def handle_special_commands(state: BotState) -> BotState:
    """Maneja comandos especiales (1-8, 0, hola) para cada usuario, considerando la fuente"""
    #agregar_mensajes_log(f"En handle_special_commands: {state}")

    texto = state["user_msg"].lower().strip()
    number = state.get("phone_number")
    source = state.get("source")
    session = state.get("session")
    # --- BLOQUE NUEVO: Intenciones básicas y fuzzy matching ---
    #intencion = detectar_intencion(texto)
    #intencion = detectar_intencion(texto, session_id=session.idUser)
    intencion = detectar_intencion(texto, session_id=getattr(session, "idUser", None))


    if intencion == "ubicacion" or texto == "3":
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
                    "body": obtener_mensaje_bot(
                        "ubicacion",
                        "📍  Estamos ubicados en km 13.5 carretera a El Salvador frente a Plaza Express a un costado de farmacia Galeno, en Intermotores"
                    )
                }
            }
        ]
        return state

    elif intencion == "horario" or texto == "4":
        state["response_data"] = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": obtener_mensaje_bot(
                        "horario",
                        "📅 Horario de Atención:\n\n Lunes a Viernes\n🕜 8:00 am a 5:00 pm\n\nSábado\n🕜 8:00 am a 12:00 pm\n\nDomingo Cerrado 🤓"
                    )
                }
            }
        ]
        return state

    elif intencion == "contacto" or texto == "5":
        state["response_data"] = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": obtener_mensaje_bot(
                        "contacto",
                        "☎*Comunícate con nosotros será un placer atenderte* \n\n 📞 6637-9834 \n\n 📞 6646-6137 \n\n 📱 5510-5350 \n\n 🌐 www.intermotores.com  \n\n 📧 intermotores.ventas@gmail.com \n\n *Facebook* \n Intermotores GT\n\n *Instagram* \n Intermotores GT "
                    )
                }
            },
            generar_list_menu(number)
        ]
        return state  
    
    if intencion == "formas_pago"  or texto == "6":
        state["response_data"] = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": obtener_mensaje_bot(
                        "formas_pago",
                        "*💲Medios de pago:* \n\n 💵 Efectivo. \n\n 🏦 Depósitos o transferencias bancarias. \n\n 📦 Pago contra Entrega. \nPagas al recibir tu producto, aplica para envíos por medio de Guatex, el monto máximo es de Q5,000. \n\n💳 Visa Cuotas. \nHasta 12 cuotas con tu tarjeta visa \n\n💳 Cuotas Credomatic. \nHasta 12 cuotas con tu tarjeta BAC Credomatic \n\n🔗 Neo Link. \nTe enviamos un link para que pagues con tu tarjeta sin salir de casa"
                    )
                }
            },
            generar_list_menu(number)
        ]
        return state

    elif intencion == "envios" or texto == "8":
        state["response_data"] = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": obtener_mensaje_bot(
                        "envios",
                        "🏠*Enviamos nuestros productos hasta la puerta de su casa* \n\n 🛵 *Envíos dentro de la capital.* \n Hacemos envíos directos dentro de la ciudad capital, aldea Puerta Parada, Santa Catarina Pinula y sus alrededores \n\n 🚚 *Envío a Departamentos.* \nHacemos envíos a los diferentes departamentos del país por medio de terceros o empresas de transporte como Guatex, Cargo Express, Forza o el de su preferencia. \n\n ⏳📦 *Tiempo de envío.* \nLos pedidos deben hacerse con 24 horas de anticipación y el tiempo de entrega para los envíos directos es de 24 a 48 horas y para los envíos a departamentos depende directamente de la empresa encargarda."
                    )
                }
            },
            generar_list_menu(number)
        ]
        return state

    elif intencion == "cuentas":
        state["response_data"] = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "image",
                "image": {
                    "link": "https://intermotores.com/wp-content/uploads/2025/04/numeros_de_cuenta_intermotores.jpg",
                    "caption": "💳Estos son nuestros números de cuenta \n*Todas son monetarias* \n\n"
                }
            }
        ]
        return state
            
    elif intencion == "mensaje_despedida":
        state["response_data"] = [
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": obtener_mensaje_bot(
                        "mensaje_despedida",
                        "De nada, ¡qué tengas buen día! 🚗💨"
                    )
                }
            }
        ]
        return state 
    # --- FIN BLOQUE NUEVO ---

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

    elif texto == "7":
        state["response_data"] = [
            {
                "messaging_product": "whatsapp" if source == "whatsapp" else "other",
                "recipient_type": "individual",
                "to": number,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": "🤝 Gracias por esperar, indique *¿cómo podemos apoyarle?* \n\nTu consulta es muy importante para nosotros. ¡Te responderemos pronto!"
                }
            }
        ]

    elif texto == "0":
        state["response_data"] = [generar_menu_principal(number)]




    log_state(state, f"⏺️ Saliendo de handle special products: {state['response_data']} at {now().isoformat()}")
    return state


def cargar_prompt_asistente():
    config = Configuration.query.filter_by(key="PROMPT_ASISTENTE").first()
    if config and config.value:
        return config.value
    # Si no existe en BD, fallback al defecto
    return PROMPT_ASISTENTE_DEFECTO

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

        # 👉 Carga el prompt base editable desde la BD
        prompt_base = cargar_prompt_asistente()
        safety_prompt = prompt_base.replace("{prompt_usuario}", prompt_usuario)

        # 🤖 Llamar al modelo
        #response = model.invoke([HumanMessage(content=safety_prompt)])
        #body = response.content

        try:
            body = run_llm_with_fallback(safety_prompt)
        except Exception as e:
            body = "❌ Ocurrió un error técnico al consultar el asistente. Intenta nuevamente en unos minutos."
            agregar_mensajes_log(str(e), session_id)


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

        log_state(state, f"✅ Asistente respondió con memoria: {body[:100]}... y el state {state}")

    return state

# Prompt de slot filling
#PROMPT_SLOT_FILL = """
#Extrae la siguiente información en JSON. Pon null si no se encuentra.
#Campos: tipo_repuesto, marca, modelo, año, serie_motor, cc, combustible
#
#Ejemplo:
#Entrada: "Turbo para sportero 2.5 28231-27000"
#el año tambien te lo pueden decir como modelo y puede venir abreviado ejmplo "modelo 90"
#la linea puede tener algunas variaciones o estar mal escrita ejemplo "colola" en vez de "corolla"
#Salida:
#{"tipo_repuesto":"turbo","marca":null,"linea":"sportero","año":null,"serie_motor":null,"cc":"2.5","combustible":null,"codigo_repuesto":"28231-27000"}
#
#Entrada: "{MENSAJE}"
#Salida:
#"""

def extract_json(texto):
    try:
        match = re.search(r'\{[\s\S]*\}', texto)
        if match:
            return json.loads(match.group())
    except Exception as e:
        agregar_mensajes_log(f"[extract_json] Error: {str(e)}")
    return {}

def cargar_prompt_slot_fill():
    config = Configuration.query.filter_by(key="PROMPT_SLOT_FILL").first()
    if config and config.value:
        return config.value
    return PROMPT_SLOT_FILL_DEFECTO

def slot_filling_llm(mensaje):
    #agregar_mensajes_log(f"🔁mensaje entrante {json.dumps(mensaje)}")
    prompt = cargar_prompt_slot_fill().replace("{MENSAJE}", mensaje)
    #response = model.invoke([HumanMessage(content=prompt)], max_tokens=100)
    #result = extract_json(response.content.strip())

    try:
        body = run_llm_with_fallback(prompt)
    except Exception as e:
        body = "❌ Ocurrió un error técnico al consultar el asistente. Intenta nuevamente en unos minutos."
        agregar_mensajes_log(str(e), body)

    #agregar_mensajes_log(f"🔁Respuesta LLM {response}")
    return body


#def slot_filling_llm(mensaje):
#    #agregar_mensajes_log(f"🔁mensaje entrante {json.dumps(mensaje)}")
#
#    prompt = PROMPT_SLOT_FILL.replace("{MENSAJE}", mensaje)
#    response = model.invoke([HumanMessage(content=prompt)], max_tokens=100)
#    result = extract_json(response.content.strip())
#
#    #agregar_mensajes_log(f"🔁Respuesta LLM {response}")
#    return result


# Reglas técnicas (comienza con tus casos más comunes)
REGLAS_SERIE_MOTOR = {
    #Toyota
    "1kz": {"marca": "Toyota", "cilindros": "4", "cc": "3.0", "combustible": "diésel", "caracteristicas": ["turbo", "culata de aluminio"], "lineas": ["Hilux", "Prado", "4Runner"]},
    "2kd": {"marca": "Toyota", "cilindros": "4", "cc": "2.5", "combustible": "diésel", "caracteristicas": ["turbo", "common rail"], "lineas": ["Hilux", "Fortuner", "Innova"]},
    "1kd": {"marca": "Toyota", "cilindros": "4", "cc": "3.0", "combustible": "diésel", "caracteristicas": ["turbo", "common rail"], "lineas": ["Hilux", "Fortuner", "Prado"]},
    "2tr": {"marca": "Toyota", "cilindros": "4", "cc": "2.7", "combustible": "gasolina", "caracteristicas": ["VVT-i"], "lineas": ["Hilux", "Fortuner", "Hiace"]},
    "1tr": {"marca": "Toyota", "cilindros": "4", "cc": "2.0", "combustible": "gasolina", "caracteristicas": ["VVT-i"], "lineas": ["Hiace", "Hilux"]},
    "3rz": {"marca": "Toyota", "cilindros": "4", "cc": "2.7", "combustible": "gasolina", "caracteristicas": [], "lineas": ["Hilux", "Tacoma"]},
    "5vz": {"marca": "Toyota", "cilindros": "6", "cc": "3.4", "combustible": "gasolina", "caracteristicas": ["V6"], "lineas": ["4Runner", "Tacoma", "T100"]},
    "2nz": {"marca": "Toyota", "cilindros": "4", "cc": "1.3", "combustible": "gasolina", "caracteristicas": ["VVT-i"], "lineas": ["Yaris", "Platz"]},
    "1nz": {"marca": "Toyota", "cilindros": "4", "cc": "1.5", "combustible": "gasolina", "caracteristicas": ["VVT-i"], "lineas": ["Yaris", "Vios", "Echo"]},
    "1zr": {"marca": "Toyota", "cilindros": "4", "cc": "1.6", "combustible": "gasolina", "caracteristicas": ["Dual VVT-i"], "lineas": ["Corolla", "Auris"]},
    "2zr": {"marca": "Toyota", "cilindros": "4", "cc": "1.8", "combustible": "gasolina", "caracteristicas": ["Dual VVT-i"], "lineas": ["Corolla", "Auris"]},
    "1gr": {"marca": "Toyota", "cilindros": "6", "cc": "4.0", "combustible": "gasolina", "caracteristicas": ["V6", "VVT-i"], "lineas": ["Hilux", "Prado", "4Runner"]},
    "3l": {"marca": "Toyota", "cilindros": "4", "cc": "2.8", "combustible": "diésel", "caracteristicas": [], "lineas": ["Hilux", "Hiace", "Dyna"]},
    "1hz": {"marca": "Toyota", "cilindros": "6", "cc": "4.2", "combustible": "diésel", "caracteristicas": [], "lineas": ["Land Cruiser", "Coaster"]},
    "1hd": {"marca": "Toyota", "cilindros": "6", "cc": "4.2", "combustible": "diésel", "caracteristicas": ["turbo"], "lineas": ["Land Cruiser", "Coaster"]},
    "5l": {"marca": "Toyota", "cilindros": "4", "cc": "3.0", "combustible": "diésel", "caracteristicas": [], "lineas": ["Hiace", "Hilux"]},
    "1gr": {"marca": "Toyota", "cilindros": "6", "cc": "4.0", "combustible": "gasolina", "caracteristicas": ["V6", "VVT-i"], "lineas": ["4Runner", "Prado", "FJ Cruiser"]},
    "3s": {"marca": "Toyota", "cilindros": "4", "cc": "2.0", "combustible": "gasolina", "caracteristicas": ["DOHC"], "lineas": ["Camry", "RAV4", "Carina"]},
    "22r": {"marca": "Toyota", "cilindros": "4", "cc": "2.4", "combustible": "gasolina", "caracteristicas": ["SOHC", "legendario", "carburado/EFI (según año)"], "lineas": ["Hilux", "Pickup", "4Runner", "Corona"]},

    #Mitsubishi
    "4d56": {"marca": "Mitsubishi", "cilindros": "4", "cc": "2.5", "combustible": "diésel", "caracteristicas": ["turbo", "intercooler"], "lineas": ["L200", "Montero Sport", "Pajero", "L300"]},
    "4d56u": {"marca": "Mitsubishi", "cilindros": "4", "cc": "2.5", "combustible": "diésel", "caracteristicas": ["turbo", "common rail", "intercooler"], "lineas": ["L200 Sportero", "Montero Sport"]},
    "4m40": {"marca": "Mitsubishi", "cilindros": "4", "cc": "2.8", "combustible": "diésel", "caracteristicas": ["turbo", "intercooler"], "lineas": ["Montero", "Pajero", "L200"]},
    "4g63": {"marca": "Mitsubishi", "cilindros": "4", "cc": "2.0", "combustible": "gasolina", "caracteristicas": ["DOHC"], "lineas": ["Eclipse", "Lancer", "Galant"]},
    "4g64": {"marca": "Mitsubishi", "cilindros": "4", "cc": "2.4", "combustible": "gasolina", "caracteristicas": ["SOHC"], "lineas": ["L200", "Montero Sport", "Outlander"]},
    "6g72": {"marca": "Mitsubishi", "cilindros": "6", "cc": "3.0", "combustible": "gasolina", "caracteristicas": ["V6"], "lineas": ["Montero", "Pajero", "3000GT"]},
    "4g54": {"marca": "Mitsubishi", "cilindros": "4", "cc": "2.6", "combustible": "gasolina", "caracteristicas": ["SOHC"], "lineas": ["L200", "Montero"]},
    "6g74": {"marca": "Mitsubishi", "cilindros": "6", "cc": "3.5", "combustible": "gasolina", "caracteristicas": ["V6"], "lineas": ["Montero", "Pajero"]},
    "4b11": {"marca": "Mitsubishi", "cilindros": "4", "cc": "2.0", "combustible": "gasolina", "caracteristicas": ["DOHC", "MIVEC"], "lineas": ["Lancer", "Outlander"]},
    "4b12": {"marca": "Mitsubishi", "cilindros": "4", "cc": "2.4", "combustible": "gasolina", "caracteristicas": ["DOHC", "MIVEC"], "lineas": ["Lancer", "Outlander"]},
    "4m42": {"marca": "Mitsubishi/Fuso", "cilindros": "4", "cc": "3.9", "combustible": "diésel", "caracteristicas": ["turbo"], "lineas": ["Canter"]},

    #Nissan
    "qd32": {"marca": "Nissan", "cilindros": "4", "cc": "3.2", "combustible": "diésel", "caracteristicas": [], "lineas": ["D21", "Terrano", "Urvan"]},
    "td27": {"marca": "Nissan", "cilindros": "4", "cc": "2.7", "combustible": "diésel", "caracteristicas": [], "lineas": ["D21", "Terrano", "Urvan"]},
    "yd25": {"marca": "Nissan", "cilindros": "4", "cc": "2.5", "combustible": "diésel", "caracteristicas": ["turbo", "common rail"], "lineas": ["Navara", "Frontier", "NP300"]},
    "ka24": {"marca": "Nissan", "cilindros": "4", "cc": "2.4", "combustible": "gasolina", "caracteristicas": [], "lineas": ["Frontier", "Xterra", "Altima"]},
    "hr16": {"marca": "Nissan", "cilindros": "4", "cc": "1.6", "combustible": "gasolina", "caracteristicas": ["DOHC"], "lineas": ["Versa", "Tiida", "March"]},
    "sr20de": {"marca": "Nissan", "cilindros": "4", "cc": "2.0", "combustible": "gasolina", "caracteristicas": ["DOHC"], "lineas": ["Primera", "Sentra", "200SX"]},
    "ga16de": {"marca": "Nissan", "cilindros": "4", "cc": "1.6", "combustible": "gasolina", "caracteristicas": ["DOHC"], "lineas": ["Sentra", "Tsuru", "Sunny"]},
    "qr25de": {"marca": "Nissan", "cilindros": "4", "cc": "2.5", "combustible": "gasolina", "caracteristicas": ["DOHC"], "lineas": ["Altima", "X-Trail", "Sentra"]},
    "vg30e": {"marca": "Nissan", "cilindros": "6", "cc": "3.0", "combustible": "gasolina", "caracteristicas": ["V6"], "lineas": ["Pathfinder", "D21", "300ZX"]},
    "rb25det": {"marca": "Nissan", "cilindros": "6", "cc": "2.5", "combustible": "gasolina", "caracteristicas": ["turbo", "DOHC"], "lineas": ["Skyline"]},

    #Mazda
    "wl": {"marca": "Mazda", "cilindros": "4", "cc": "2.5", "combustible": "diésel", "caracteristicas": ["turbo"], "lineas": ["BT-50", "B2500"]},
    "rf": {"marca": "Mazda", "cilindros": "4", "cc": "2.0", "combustible": "diésel", "caracteristicas": [], "lineas": ["323", "626"]},
    "fe": {"marca": "Mazda", "cilindros": "4", "cc": "2.0", "combustible": "gasolina", "caracteristicas": ["SOHC"], "lineas": ["626", "B2000", "MPV"]},
    "f2": {"marca": "Mazda", "cilindros": "4", "cc": "2.2", "combustible": "gasolina", "caracteristicas": [], "lineas": ["B2200", "626"]},
    "fs": {"marca": "Mazda", "cilindros": "4", "cc": "2.0", "combustible": "gasolina", "caracteristicas": ["DOHC"], "lineas": ["626", "Premacy"]},
    "rf-t": {"marca": "Mazda", "cilindros": "4", "cc": "2.0", "combustible": "diésel", "caracteristicas": ["turbo"], "lineas": ["626", "Bongo"]},
    "z5": {"marca": "Mazda", "cilindros": "4", "cc": "1.5", "combustible": "gasolina", "caracteristicas": [], "lineas": ["323", "Familia"]},
    "wlt": {"marca": "Mazda", "cilindros": "4", "cc": "2.5", "combustible": "diésel", "caracteristicas": ["turbo"], "lineas": ["BT-50", "B2500"]},

    #Honda
    "r18": {"marca": "Honda", "cilindros": "4", "cc": "1.8", "combustible": "gasolina", "caracteristicas": ["i-VTEC"], "lineas": ["Civic", "CR-V"]},
    "l15": {"marca": "Honda", "cilindros": "4", "cc": "1.5", "combustible": "gasolina", "caracteristicas": ["i-VTEC", "Turbo (algunas versiones)"], "lineas": ["Fit", "City", "HR-V", "Civic"]},
    "k24": {"marca": "Honda", "cilindros": "4", "cc": "2.4", "combustible": "gasolina", "caracteristicas": ["i-VTEC"], "lineas": ["CR-V", "Accord", "Odyssey"]},
    "d15b": {"marca": "Honda", "cilindros": "4", "cc": "1.5", "combustible": "gasolina", "caracteristicas": ["SOHC", "VTEC"], "lineas": ["Civic", "City"]},
    "d17a": {"marca": "Honda", "cilindros": "4", "cc": "1.7", "combustible": "gasolina", "caracteristicas": ["SOHC", "VTEC"], "lineas": ["Civic"]},
    "b16a": {"marca": "Honda", "cilindros": "4", "cc": "1.6", "combustible": "gasolina", "caracteristicas": ["DOHC", "VTEC"], "lineas": ["Civic", "CRX", "Integra"]},
    "b18b": {"marca": "Honda", "cilindros": "4", "cc": "1.8", "combustible": "gasolina", "caracteristicas": ["DOHC"], "lineas": ["Integra", "Civic"]},
    "f23a": {"marca": "Honda", "cilindros": "4", "cc": "2.3", "combustible": "gasolina", "caracteristicas": ["SOHC"], "lineas": ["Accord", "Odyssey"]},

    #Suzuki
    "m13a": {"marca": "Suzuki", "cilindros": "4", "cc": "1.3", "combustible": "gasolina", "caracteristicas": ["DOHC"], "lineas": ["Swift", "Jimny"]},
    "m15a": {"marca": "Suzuki", "cilindros": "4", "cc": "1.5", "combustible": "gasolina", "caracteristicas": ["DOHC"], "lineas": ["Swift", "SX4", "Ertiga"]},
    "j20a": {"marca": "Suzuki", "cilindros": "4", "cc": "2.0", "combustible": "gasolina", "caracteristicas": ["DOHC"], "lineas": ["Grand Vitara", "SX4"]},
    "h27a": {"marca": "Suzuki", "cilindros": "6", "cc": "2.7", "combustible": "gasolina", "caracteristicas": ["V6"], "lineas": ["XL-7", "Grand Vitara"]},
    "g13bb": {"marca": "Suzuki", "cilindros": "4", "cc": "1.3", "combustible": "gasolina", "caracteristicas": ["SOHC"], "lineas": ["Swift", "Baleno"]},
    "m18a": {"marca": "Suzuki", "cilindros": "4", "cc": "1.8", "combustible": "gasolina", "caracteristicas": ["DOHC"], "lineas": ["Grand Vitara"]},
    "h25a": {"marca": "Suzuki", "cilindros": "6", "cc": "2.5", "combustible": "gasolina", "caracteristicas": ["V6"], "lineas": ["Grand Vitara"]},

    #Hyundai/Kia
    "j3": {"marca": "Hyundai/Kia", "cilindros": "4", "cc": "2.9", "combustible": "diésel", "caracteristicas": ["turbo", "CRDI"], "lineas": ["Terracan", "Bongo"]},
    "d4cb": {"marca": "Hyundai/Kia", "cilindros": "4", "cc": "2.5", "combustible": "diésel", "caracteristicas": ["CRDI", "turbo"], "lineas": ["H1", "Starex", "Grand Starex", "porter"]},
    "d4ea": {"marca": "Hyundai/Kia", "cilindros": "4", "cc": "2.0", "combustible": "diésel", "caracteristicas": ["CRDI", "turbo"], "lineas": ["Tucson", "Sportage"]},
    "d4fb": {"marca": "Hyundai/Kia", "cilindros": "4", "cc": "1.6", "combustible": "diésel", "caracteristicas": ["CRDI", "turbo"], "lineas": ["Accent", "Rio", "i20"]},
    "g4gc": {"marca": "Hyundai/Kia", "cilindros": "4", "cc": "2.0", "combustible": "gasolina", "caracteristicas": [], "lineas": ["Elantra", "Tucson"]},
    "g4kd": {"marca": "Hyundai/Kia", "cilindros": "4", "cc": "2.0", "combustible": "gasolina", "caracteristicas": ["DOHC"], "lineas": ["Tucson", "Sportage", "Cerato"]},
    "g4ke": {"marca": "Hyundai/Kia", "cilindros": "4", "cc": "2.4", "combustible": "gasolina", "caracteristicas": ["DOHC"], "lineas": ["Santa Fe", "Sonata", "Optima"]},
    "d4ea": {"marca": "Hyundai/Kia", "cilindros": "4", "cc": "2.0", "combustible": "diésel", "caracteristicas": ["CRDI", "turbo"], "lineas": ["Tucson", "Sportage"]},
    "g6ea": {"marca": "Hyundai/Kia", "cilindros": "6", "cc": "2.7", "combustible": "gasolina", "caracteristicas": ["V6"], "lineas": ["Santa Fe", "Terracan"]},
    "g4fa": {"marca": "Hyundai/Kia", "cilindros": "4", "cc": "1.4", "combustible": "gasolina", "caracteristicas": ["DOHC"], "lineas": ["i20", "Accent"]},
    "g4fj": {"marca": "Hyundai/Kia", "cilindros": "4", "cc": "1.0", "combustible": "gasolina", "caracteristicas": ["turbo", "DOHC"], "lineas": ["i10", "Picanto"]},

    #Isuzu
    "4jb1": {"marca": "Isuzu", "cilindros": "4", "cc": "2.8", "combustible": "diésel", "caracteristicas": ["turbo (algunas versiones)"], "lineas": ["D-Max", "Trooper"]},
    "4ja1": {"marca": "Isuzu", "cilindros": "4", "cc": "2.5", "combustible": "diésel", "caracteristicas": [], "lineas": ["D-Max", "Trooper"]},
    "4jh1": {"marca": "Isuzu", "cilindros": "4", "cc": "3.0", "combustible": "diésel", "caracteristicas": ["turbo"], "lineas": ["D-Max", "NPR"]},
    "4hk1": {"marca": "Isuzu", "cilindros": "4", "cc": "5.2", "combustible": "diésel", "caracteristicas": ["turbo", "intercooler"], "lineas": ["NQR", "NPR"]},

    #subaru
    "ej20": {"marca": "Subaru", "cilindros": "4", "cc": "2.0", "combustible": "gasolina", "caracteristicas": ["Boxer", "DOHC", "turbo (algunas versiones)"], "lineas": ["Impreza", "Legacy", "Forester"]},
    "ez30": {"marca": "Subaru", "cilindros": "6", "cc": "3.0", "combustible": "gasolina", "caracteristicas": ["Boxer", "DOHC"], "lineas": ["Legacy", "Outback"]},
    "fb20": {"marca": "Subaru", "cilindros": "4", "cc": "2.0", "combustible": "gasolina", "caracteristicas": ["Boxer", "DOHC"], "lineas": ["XV", "Impreza", "Forester"]},

    #Daihatsu
    "hc-e": {"marca": "Daihatsu", "cilindros": "3", "cc": "1.0", "combustible": "gasolina", "caracteristicas": [], "lineas": ["Charade"]},
    "ej-ve": {"marca": "Daihatsu", "cilindros": "3", "cc": "1.0", "combustible": "gasolina", "caracteristicas": ["DOHC"], "lineas": ["Sirion", "Cuore"]},

    #Hino
    "n04c": {"marca": "Hino", "cilindros": "4", "cc": "4.0", "combustible": "diésel", "caracteristicas": ["common rail"], "lineas": ["300", "Dutro"]},
    "j05e": {"marca": "Hino", "cilindros": "4", "cc": "5.1", "combustible": "diésel", "caracteristicas": [], "lineas": ["500"]},

}
#REGLAS_MODELOS = {
#    "Sportero": {"marca": "Mitsubishi", "serie_motor": "4D56U", "cc": "2.5", "combustible": "diésel"},
#    "l200": {"marca": "Mitsubishi"}
#
#}

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
        "22R": ["22r", "22-r", "22 r", "22erre"],

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

FRASES_NO_SE = ["no sé", "no se", "nose", "no tengo", "no la tengo", "no recuerdo", "desconozco", "no aplica"]

TIPOS_REPUESTO = [
    "motor", "culata", "turbina", "bomba", "inyector", "alternador", "radiador", "turbo", "caja de velocidades", "eje de levas", "termostato", 
    "caja", "transmisión", "transmision", "computadora", "filtro", "embrague",
    "cigueñal", "cigüeñal", "eje de cigüeñal", "balancin", "eje de balance", "cojinete",
    "carburador", "flauta", "barilla", "boster", "booster", "piston",

]

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

def cargar_reglas_serie_motor():
    reglas = KnowledgeBase.query.filter_by(tipo="serie_motor", activo=True).all()
    return {k.clave: json.loads(k.valor) for k in reglas}

def cargar_marcas_lineas():
    kb = KnowledgeBase.query.filter_by(tipo="marca_linea", clave="all", activo=True).first()
    if kb:
        return json.loads(kb.valor)
    return {}

def cargar_alias_modelos():
    alias = KnowledgeBase.query.filter_by(tipo="alias_modelo", activo=True).all()
    return {k.clave: json.loads(k.valor) for k in alias}

def cargar_frases_no_se():
    frases = KnowledgeBase.query.filter_by(tipo="frase_no_se", activo=True).all()
    return [json.loads(k.valor) for k in frases]

def cargar_tipos_repuesto():
    tipos = KnowledgeBase.query.filter_by(tipo="tipo_repuesto", activo=True).all()
    return [json.loads(k.valor) for k in tipos]

def cargar_preguntas_slots():
    slots = KnowledgeBase.query.filter_by(tipo="pregunta_slot", activo=True).all()
    return {k.clave: json.loads(k.valor) for k in slots}

def cargar_fuzzy_threshold():
    config = Configuration.query.filter_by(key="FUZZY_MATCH_SCORE").first()
    if config and config.value:
        try:
            return int(config.value)
        except Exception:
            pass
    return 90  # Valor por defecto


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

#def extraer_linea_y_marca_usuario(texto_usuario):
#    texto_norm = texto_usuario.lower().replace("-", "").replace("  ", " ").strip()
#    # Recolecta todos los alias en una lista [(marca, linea, alias_normalizado)]
#    alias_todos = []
#    for marca, lineas in MARCAS_LINEAS.items():
#        for linea, alias_list in lineas.items():
#            for alias in alias_list:
#                alias_norm = alias.lower().replace("-", "").replace(" ", "")
#                alias_todos.append((marca, linea, alias_norm))
#    # Busca alias más cercano en el mensaje
#    palabras_usuario = texto_norm.replace(" ", "")
#    mejores = difflib.get_close_matches(palabras_usuario, [alias_norm for (_, _, alias_norm) in alias_todos], n=1, cutoff=0.7)
#    if mejores:
#        for marca, linea, alias_norm in alias_todos:
#            if alias_norm == mejores[0]:
#                return marca, linea
#    # Si no hay fuzzy match, intenta match parcial (por si el usuario pone varias palabras: "suzuki xl7")
#    for marca, lineas in MARCAS_LINEAS.items():
#        for linea, alias_list in lineas.items():
#            for alias in alias_list:
#                alias_norm = alias.lower().replace("-", "").replace(" ", "")
#                if alias_norm in palabras_usuario:
#                    return marca, linea
#    return None, None

from rapidfuzz import fuzz, process

def extraer_linea_y_marca_usuario(texto_usuario, log_func=None, score_threshold=80):
    """
    Busca el alias de línea/modelo con mejor coincidencia (fuzzy) usando RapidFuzz.
    Retorna: (marca, linea_estandar, alias_coincidido, score)
    log_func: función para loggear si quieres, ejemplo agregar_mensajes_log
    """
    texto_norm = texto_usuario.lower().replace("-", "").replace("  ", " ").strip()
    alias_todos = []
    for marca, lineas in MARCAS_LINEAS.items():
        for linea, alias_list in lineas.items():
            for alias in alias_list:
                alias_norm = alias.lower().replace("-", "").replace(" ", "")
                alias_todos.append((marca, linea, alias, alias_norm))

    # Arma lista solo de los alias normalizados
    alias_norm_list = [item[3] for item in alias_todos]
    # Score fuzzy contra cada alias
    result = process.extractOne(
        texto_norm.replace(" ", ""),
        alias_norm_list,
        scorer=fuzz.ratio
    )
    if result and result[1] >= score_threshold:
        alias_norm_coinc = result[0]
        score = result[1]
        # Busca marca/linea original para ese alias_norm
        for marca, linea, alias, alias_norm in alias_todos:
            if alias_norm == alias_norm_coinc:
                if log_func:
                    log_func(f"🔍 Fuzzy match: '{texto_usuario}' ≈ '{alias}' [{marca} {linea}] (score={score})")
                return marca, linea, alias, score
    # Si no hay fuzzy match, intenta match parcial (por si el usuario pone varias palabras)
    for marca, lineas in MARCAS_LINEAS.items():
        for linea, alias_list in lineas.items():
            for alias in alias_list:
                alias_norm = alias.lower().replace("-", "").replace(" ", "")
                if alias_norm in texto_norm.replace(" ", ""):
                    if log_func:
                        log_func(f"🔍 Partial match: '{texto_usuario}' contiene '{alias}' [{marca} {linea}]")
                    return marca, linea, alias, 100
    return None, None, None, 0


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


def handle_cotizacion_slots(state: dict) -> dict:
    from datetime import datetime, timedelta

    session = state.get("session")
    user_msg = state.get("user_msg")

    REGLAS_SERIE_MOTOR = cargar_reglas_serie_motor() or REGLAS_SERIE_MOTOR
    FRASES_NO_SE = cargar_frases_no_se() or FRASES_NO_SE
    TIPOS_REPUESTO = cargar_tipos_repuesto() or TIPOS_REPUESTO
    PREGUNTAS_SLOTS = cargar_preguntas_slots() or PREGUNTAS_SLOTS
    MARCAS_LINEAS = cargar_marcas_lineas() or MARCAS_LINEAS  # El fallback es opcional si quieres

# Luego puedes usar MARCAS_LINEAS["Toyota"]["corolla"] etc...

    #REGLAS_SERIE_MOTOR = cargar_reglas_serie_motor() or {
    #    # aquí tu diccionario por defecto (opcional, solo si quieres fallback)
    #}

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
    #agregar_mensajes_log(f"🔁memoria slots cargada {json.dumps(memoria_slots)}")

    # Si la memoria está vacía, filtra por keywords (primer mensaje)
    if not memoria_slots or all(v in [None, "", "no_sabe"] for v in memoria_slots.values()):
        cotizacion_keywords = ["motor","necesito","que precio","qué precio", "precio","cuesta", "vale","bale", "quiero", "cuanto cuesta","cuánto cuesta","hay ","tiene", "culata", "cotizar", "repuesto", "turbina", "bomba", "inyector", "alternador","turbo","cigüeñal","cigueñal","ciguenal","starter","eje de levas"]
        if not any(kw in user_msg.lower() for kw in cotizacion_keywords):
            #agregar_mensajes_log(f"🔁no hay cotizacion keywords {json.dumps(memoria_slots)}")

            return state
        
    if not es_no_se(user_msg):

        #agregar_mensajes_log(f"🔁no es nose ")

        # Slot filling LLM
        nuevos_slots = slot_filling_llm(user_msg)
        #agregar_mensajes_log(f"🔁nuevos slots {json.dumps(nuevos_slots)}")
        
        # Si no hay tipo_repuesto, intenta extraerlo por palabra clave
        if not nuevos_slots.get("tipo_repuesto"):
            tipo_detectado = extraer_tipo_repuesto(user_msg)
            if tipo_detectado:
                nuevos_slots["tipo_repuesto"] = tipo_detectado
        
        # Si no hay marca/linea, usa fuzzy helper
        if not nuevos_slots.get("linea") or not nuevos_slots.get("marca"):
            #agregar_mensajes_log(f"🔁buscando linea y marca{json.dumps(nuevos_slots)}")
            # Si no hay marca/linea, usa fuzzy helper mejorado

            #marca_detectada, linea_detectada = extraer_linea_y_marca_usuario(user_msg)
            #if linea_detectada and not nuevos_slots.get("linea"):
            #    nuevos_slots["linea"] = linea_detectada.capitalize()
            #if marca_detectada and not nuevos_slots.get("marca"):
            #    nuevos_slots["marca"] = marca_detectada
        
            score_threshold = cargar_fuzzy_threshold()  # Lee el threshold de la base de datos
            marca, linea, alias, score = extraer_linea_y_marca_usuario(
                user_msg,
                log_func=agregar_mensajes_log,
                score_threshold=score_threshold
            )
            if linea and not nuevos_slots.get("linea"):
                nuevos_slots["linea"] = linea.capitalize()
            if marca and not nuevos_slots.get("marca"):
                nuevos_slots["marca"] = marca
            # Puedes dejar aquí un log más explícito si quieres:
            if score >= score_threshold:
                agregar_mensajes_log(f"🎯 Coincidencia fuzzy: '{user_msg}' ≈ '{alias}' (score={score}) -> {marca} {linea}")

        # Ahora sí, fusiona con memoria_slots
        #for k, v in nuevos_slots.items():
        #    if v is not None and v != "" and v != "no_sabe":
        #        memoria_slots[k] = v
        memoria_slots = actualizar_slots_memoria(memoria_slots, nuevos_slots, user_msg)

        # Aplica deducción técnica
        memoria_slots = deducir_conocimiento(memoria_slots)
        #guardar_memoria_slots(session, memoria_slots)
        guardar_memoria(session.idUser, 'slots_cotizacion', memoria_slots)
        faltan = campos_faltantes(memoria_slots)

        # Normaliza modelos si es posible
        #modelo = nuevos_slots.get("linea")
        #if modelo:
        #    modelo_key = modelo.lower().replace("-", "").replace(" ", "")
        #    if modelo_key in ALIAS_MODELOS:
        #        nuevos_slots["linea"] = ALIAS_MODELOS[modelo_key]

        #for k, v in nuevos_slots.items():
        #    if v is not None and v != "" and v != "no_sabe":
        #        memoria_slots[k] = v
        memoria_slots = actualizar_slots_memoria(memoria_slots, nuevos_slots, user_msg)

        memoria_slots = deducir_conocimiento(memoria_slots)
        #guardar_memoria_slots(session, memoria_slots)
        guardar_memoria(session.idUser, 'slots_cotizacion', memoria_slots)
        faltan = campos_faltantes(memoria_slots)


    faltan = campos_faltantes(memoria_slots)
    if len(faltan) == 1 and es_no_se(user_msg):
        campo_faltante = faltan[0]
        memoria_slots[campo_faltante] = "no_sabe"
        #guardar_memoria_slots(session, memoria_slots)
        guardar_memoria(session.idUser, 'slots_cotizacion', memoria_slots)
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
            db.session.commit()
            #guardar_memoria(session.idUser, 'assistant', memoria_slots)

            # 📝 Guardar memorias
            if session:
                guardar_memoria(session.idUser, "user", user_msg)
                guardar_memoria(session.idUser, "assistant", resumen)

            log_state(state, f"⏺️ Saliendo de Handle Cotizacion Slots : {json.dumps(resumen)} at {now().isoformat()}")

            resetear_memoria_slots(session)
            #guardar_memoria(session, "assistant", {json.dumps(resumen)})

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

    # 📝 Guardar memorias
    if session:
        guardar_memoria(session.idUser, "user", user_msg)
        guardar_memoria(session.idUser, "assistant", resumen)

    #guardar_memoria(session.idUser, 'assistant', memoria_slots)
    #guardar_memoria(session, "assistant", {json.dumps(resumen)})
    log_state(state, f"⏺️ Saliendo de Handle Cotizacion Slots : {json.dumps(resumen)} at {now().isoformat()}")

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

def get_whatsapp_delay():
    from models import Configuration
    config = Configuration.query.filter_by(key="WHATSAPP_DELAY_SECONDS").first()
    try:
        return float(config.value)
    except Exception:
        return 4.0  # fallback


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

                # Usa el delay configurable
                delay = get_whatsapp_delay()
                time.sleep(delay)
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
    agregar_mensajes_log(f"✅ Respuesta: {state}")

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
        #agregar_mensajes_log(f"✅ Mensaje enviado a whatsapp: {state['phone_number']}, {json_data}")
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

            # ...
            block_result = block("whatsapp", message)
            if block_result.get("status") == "blocked":
                agregar_mensajes_log(f"Usuario o tipo de mensaje bloqueado intentó contactar: {message.get('from')}")
                return jsonify({'status': 'blocked', 'message': block_result['message']}), 200

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
    inicializar_todo()


if __name__ == '__main__':
    flask_app.run(host='0.0.0.0', port=80, debug=True)