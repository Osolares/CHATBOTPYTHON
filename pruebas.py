# Frases random para cada slot (puedes ampliar)
PREGUNTAS_SLOTS = {
    "tipo_repuesto": [
        "¿Qué repuesto necesitas? (ejemplo: motor, culata, etc.)",
        "¿Sobre qué repuesto te gustaría cotizar?"
    ],
    "marca": [
        "¿Cuál es la marca de tu vehículo?",
        "¿Me indicas la marca del auto?"
    ],
    "modelo": [
        "¿Qué modelo es tu vehículo?",
        "¿Podrías decirme el modelo?"
    ],
    "año": [
        "¿De qué año es tu vehículo?",
        "¿Sabes el año del auto?"
    ],
    "serie_motor": [
        "¿Conoces la serie del motor?",
        "¿Me das la serie del motor?"
    ]
}

def handle_cotizacion_slots(state: dict) -> dict:
    session = state.get("session")
    user_msg = state.get("user_msg")

    comandos_reset = ["nueva cotización", "empezar de nuevo"]

    if user_msg.strip().lower() in comandos_reset:
        resetear_memoria_slots(session)
        state["response_data"] = [{
            "messaging_product": "whatsapp",
            "to": state.get("phone_number"),
            "type": "text",
            "text": {"body": "👌 ¡Listo! Puedes empezar una nueva cotización cuando quieras. ¿Qué repuesto necesitas ahora?"}
        }]
        return state
    # 🟢 Limpieza para WhatsApp (sólo acepta mensajes tipo texto y botón)
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

    # 1. Cargar memoria de slots
    memoria_slots = cargar_memoria_slots(session)

    # 🟢 Nuevo: si la memoria ya tiene algún dato relevante, no filtra por keywords
    # Solo filtra si es el primer mensaje de la conversación
    if not memoria_slots or all(v in [None, ""] for v in memoria_slots.values()):
        cotizacion_keywords = ["motor", "necesito un", "culata", "cotizar", "repuesto", "turbina", "bomba", "inyector", "alternador"]
        if not any(kw in user_msg.lower() for kw in cotizacion_keywords):
            return state  # No es cotización, sigue el flujo normal

    # 1. Cargar memoria de slots
    #memoria_slots = cargar_memoria_slots(session)

    # 2. LLM slot filling (string limpio)
    nuevos_slots = slot_filling_llm(user_msg)
    agregar_mensajes_log(f"🔁nuevos slots {json.dumps(nuevos_slots)}")

    # 3. Actualiza memoria acumulativa SOLO si viene nuevo dato (no borra con None)
    for k, v in nuevos_slots.items():
        if v is not None and v != "":
            memoria_slots[k] = v

    # 4. Deducción técnica de conocimiento propio
    memoria_slots = deducir_conocimiento(memoria_slots)
    guardar_memoria_slots(session, memoria_slots)

    # 5. Checa lo que falta
    faltan = campos_faltantes(memoria_slots)
    if faltan:
        frases = []
        frases.append("🚗 ¡Gracias por la info!")
        resumen = []
        if memoria_slots.get("marca"):
            resumen.append(f"Marca: {memoria_slots['marca']}")
        if memoria_slots.get("modelo"):
            resumen.append(f"Modelo: {memoria_slots['modelo']}")
        if memoria_slots.get("año"):
            resumen.append(f"Año: {memoria_slots['año']}")
        if memoria_slots.get("serie_motor"):
            resumen.append(f"Serie de motor: {memoria_slots['serie_motor']}")
        if memoria_slots.get("tipo_repuesto"):
            resumen.append(f"Repuesto: {memoria_slots['tipo_repuesto']}")
        if resumen:
            frases.append("📝 Datos que tengo hasta ahora:\n" + "\n".join(resumen))

        # Frases random con emojis por cada dato faltante
        for campo in faltan:
            pregunta = random.choice(PREGUNTAS_SLOTS.get(campo, [f"¿Me das el dato de {campo}?"]))
            frases.append(f"👉 {pregunta}")
        mensaje = "\n\n".join(frases)
        state["response_data"] = [{
            "messaging_product": "whatsapp",
            "to": state.get("phone_number"),
            "type": "text",
            "text": {"body": mensaje}
        }]
        state["cotizacion_completa"] = False
        return state

    # 6. ¡Ya tienes todo! Notifica, pausa y responde con emoción para WhatsApp
    notificar_lead_via_whatsapp('50255105350', session, memoria_slots)
    session.modo_control = 'paused'
    session.pausa_hasta = datetime.now() + timedelta(hours=2)
    from config import db
    db.session.commit()
    state["response_data"] = [{
        "messaging_product": "whatsapp",
        "to": state.get("phone_number"),
        "type": "text",
        "text": {"body": "🎉 ¡Listo! Ya tengo toda la información para cotizar. Un asesor te contactará muy pronto. Gracias por tu confianza. 🚗✨"}
    }]
    state["cotizacion_completa"] = True
    resetear_memoria_slots(session)

    return state










def handle_cotizacion_slots(state: dict) -> dict:
    session = state.get("session")
    user_msg = state.get("user_msg")

    #agregar_mensajes_log(f"[DEBUG] session en nodo: {str(session)}")
    #agregar_mensajes_log(f"[DEBUG] session.idUser en nodo: {getattr(session, 'idUser', None)}")

    # Keywords básicas para cotización, ajusta según tu negocio:
    cotizacion_keywords = ["motor", "culata", "cotizar", "repuesto", "turbina", "bomba", "inyector", "alternador"]
    #if not any(kw in user_msg.lower() for kw in cotizacion_keywords):
    #    return state  # No es cotización, sigue el flujo normal

    # --- 1. Cargar slots existentes ---
    memoria_slots = cargar_memoria_slots(session)
    # --- 2. Extraer nuevos del mensaje ---
    nuevos_slots = slot_filling_llm(user_msg)     
    for k, v in nuevos_slots.items():
        memoria_slots[k] = v
    
    agregar_mensajes_log(f"🔁nuevos slots {json.dumps(nuevos_slots)}")

    # --- 3. Deducción técnica ---

    memoria_slots = deducir_conocimiento(memoria_slots)
    #agregar_mensajes_log(f"[DEBUG] Antes de guardar - memoria_slots: {json.dumps(memoria_slots)} session.idUser: {getattr(session, 'idUser', None)}")
    guardar_memoria_slots(session, memoria_slots)
    # --- 4. Pregunta por lo faltante, si aplica ---
    faltan = campos_faltantes(memoria_slots)
    if faltan:
        pregunta = f"Para cotizar necesito: {', '.join(faltan)}."
        state["response_data"] = [{
            "messaging_product": "whatsapp" if state["source"] == "whatsapp" else "other",
            "to": state.get("phone_number") or state.get("email"),
            "type": "text",
            "text": {"body": pregunta}
        }]
        state["cotizacion_completa"] = False
        return state

    # --- 5. Si tienes todo, notifica y pausa ---
    notificar_lead_via_whatsapp('50255105350', session, memoria_slots)
    session.modo_control = 'paused'
    session.pausa_hasta = datetime.now() + timedelta(hours=2)
    db.session.commit()
    state["response_data"] = [{
        "messaging_product": "whatsapp" if state["source"] == "whatsapp" else "other",
        "to": state.get("phone_number") or state.get("email"),
        "type": "text",
        "text": {"body": "¡Gracias! Un asesor te contactará pronto para finalizar tu cotización."}
    }]
    state["cotizacion_completa"] = True
    return state
