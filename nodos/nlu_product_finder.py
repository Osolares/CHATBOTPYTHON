import json
from extractor.extractor_de_atributos import extraer_atributos_desde_texto
from woocommerce.buscar_por_atributos import buscar_productos_por_atributos
from models import guardar_memoria

def nlu_product_finder(state):
    user_msg = state.get("user_msg", "")
    session = state.get("session")
    session_id = session.idUser if session else None

    atributos = extraer_atributos_desde_texto(user_msg)

    faltantes = []
    for campo in ["marca", "motor", "anio"]:
        if not atributos.get(campo):
            faltantes.append(campo)

    if faltantes:
        preguntas = {
            "marca": "¿Sabes la marca del vehículo? (Ej: Hyundai, Kia, Toyota...)",
            "motor": "¿Tienes el código o serie del motor? (Ej: D4EA, 1NZ, R20A...)",
            "anio": "¿De qué año es tu vehículo?"
        }
        mensajes = []
        for f in faltantes:
            pregunta = preguntas.get(f)
            if pregunta:
                mensajes.append({
                    "messaging_product": "whatsapp",
                    "to": state.get("phone_number"),
                    "type": "text",
                    "text": {"body": pregunta}
                })

        state["response_data"] = mensajes
        return state

    productos = buscar_productos_por_atributos(atributos)

    if not productos:
        state["response_data"] = [{
            "messaging_product": "whatsapp",
            "to": state.get("phone_number"),
            "type": "text",
            "text": {
                "body": "🚫 No encontramos motores que coincidan con tu solicitud. ¿Deseas buscar otra opción o especificar más datos?"
            }
        }]
        return state

    if session_id:
        guardar_memoria(session_id, "consulta_woo", json.dumps(atributos))
        guardar_memoria(session_id, "resultados_woo", json.dumps(productos[:3]))

    respuestas = []
    for p in productos[:3]:
        nombre = p.get("name")
        precio = p.get("price")
        url = p.get("permalink")
        respuestas.append({
            "messaging_product": "whatsapp",
            "to": state.get("phone_number"),
            "type": "text",
            "text": {
                "preview_url": True,
                "body": f"✅ Encontramos: *{nombre}*💲 Q{precio}🔗 {url}"
            }
        })

    state["response_data"] = respuestas
    return state