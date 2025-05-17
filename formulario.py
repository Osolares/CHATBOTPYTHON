from datetime import datetime
from models import ProductModel, db
from session_manager import load_or_create_session, get_session
from catalog_service import get_marcas_permitidas, get_series_disponibles
from woocommerce_service import buscar_productos
from menus import generar_list_menu

def analizar_mensaje_inicial(mensaje):
    marca = None
    linea = None
    anio = None
    combustible = None
    tipo = None
    serie = None

    mensaje_lower = mensaje.lower()
    marcas = get_marcas_permitidas()
    for m in marcas:
        if m.lower() in mensaje_lower:
            marca = m
            break

    series = get_series_disponibles()
    for s in series:
        if s.lower() in mensaje_lower:
            serie = s
            break

    posibles_lineas = ["tucson", "sportage", "hilux", "l200", "santa fe"]
    for l in posibles_lineas:
        if l in mensaje_lower:
            linea = l
            break

    combustibles = ["gasolina", "diesel", "diésel", "disel"]
    for c in combustibles:
        if c in mensaje_lower:
            combustible = "Diésel" if "diesel" in c or "diésel" in c or "disel" in c else "Gasolina"
            break

    import re
    match = re.search(r'(19|20)\d{2}', mensaje_lower)
    if match:
        anio = match.group(0)

    tipos = ["motor", "culata", "turbo", "cigüeñal", "inyector", "bomba"]
    for t in tipos:
        if t in mensaje_lower:
            tipo = t
            break

    return {
        "marca": marca,
        "linea": linea,
        "modelo_anio": anio,
        "combustible": combustible,
        "tipo_repuesto": tipo,
        "serie_motor": serie,
    }

def iniciar_flujo(number, mensaje_usuario):
    session = load_or_create_session(number)
    producto = ProductModel.query.filter_by(session_id=session.idUser).first()
    if not producto:
        producto = ProductModel(session_id=session.idUser)
        db.session.add(producto)

    resultado = analizar_mensaje_inicial(mensaje_usuario)
    for campo, valor in resultado.items():
        if valor:
            setattr(producto, campo, valor)

    # Secuencia de pasos según faltantes
    if not producto.marca:
        return pedir_marca(number, producto)
    if not producto.linea:
        return pedir_linea(number, producto)
    if not producto.combustible:
        return pedir_combustible(number, producto)
    if not producto.modelo_anio:
        return pedir_anio(number, producto)
    if not producto.tipo_repuesto:
        return pedir_tipo(number, producto)
    # Si tienes serie_motor y quieres que sea obligatoria, agrégalo aquí

    return confirmar_datos(number, producto)

def pedir_marca(number, producto):
    marcas = get_marcas_permitidas()
    opciones = ', '.join(marcas)
    producto.current_step = 'awaiting_marca'
    db.session.commit()
    return [{
        "messaging_product": "whatsapp",
        "to": number,
        "type": "text",
        "text": {
            "body": f"¿Cuál es la marca? Opciones: {opciones}"
        }
    }]

def pedir_linea(number, producto):
    producto.current_step = 'awaiting_modelo'
    db.session.commit()
    return [{
        "messaging_product": "whatsapp",
        "to": number,
        "type": "text",
        "text": {
            "body": "¿Cuál es la línea/modelo del vehículo?"
        }
    }]

def pedir_combustible(number, producto):
    producto.current_step = 'awaiting_combustible'
    db.session.commit()
    return [{
        "messaging_product": "whatsapp",
        "to": number,
        "type": "text",
        "text": {
            "body": "¿El combustible es gasolina o diésel?"
        }
    }]

def pedir_anio(number, producto):
    producto.current_step = 'awaiting_año'
    db.session.commit()
    return [{
        "messaging_product": "whatsapp",
        "to": number,
        "type": "text",
        "text": {
            "body": "¿Qué año es tu vehículo?"
        }
    }]

def pedir_tipo(number, producto):
    producto.current_step = 'awaiting_tipo_repuesto'
    db.session.commit()
    return [{
        "messaging_product": "whatsapp",
        "to": number,
        "type": "text",
        "text": {
            "body": "¿Qué tipo de repuesto necesitas? (Ej: Motor, Culata, Turbo)"
        }
    }]

def confirmar_datos(number, producto):
    producto.current_step = 'awaiting_confirm'
    db.session.commit()
    return [{
        "messaging_product": "whatsapp",
        "to": number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": f"¿Son correctos estos datos?\nMarca: {producto.marca}\nModelo: {producto.linea}\nAño: {producto.modelo_anio}\nCombustible: {producto.combustible}\nTipo: {producto.tipo_repuesto}"
            },
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "cotizar_si", "title": "✅ Sí, cotizar"}},
                    {"type": "reply", "reply": {"id": "editar", "title": "✏️ Editar"}}
                ]
            }
        }
    }]

def manejar_confirmacion(number, user_message, producto):
    if user_message == "cotizar_si":
        productos = buscar_productos(
            marca=producto.marca,
            linea=producto.linea,
            combustible=producto.combustible,
            anio=producto.modelo_anio,
            tipo=producto.tipo_repuesto,
            serie=producto.serie_motor
        )
        if productos:
            textos = []
            for p in productos:
                textos.append({
                    "messaging_product": "whatsapp",
                    "to": number,
                    "type": "text",
                    "text": {
                        "body": f"Producto: {p['name']}\nPrecio: Q{p['price']}\nStock: {p['stock_quantity']}\nLink: {p['permalink']}"
                    }
                })
            textos.append(generar_list_menu(number))
            return textos
        else:
            return [{
                "messaging_product": "whatsapp",
                "to": number,
                "type": "text",
                "text": {"body": "❌ No se encontraron productos para tu búsqueda."}
            }, generar_list_menu(number)]
    elif user_message == "editar":
        # Aquí puedes redirigir al paso que necesite editar
        return pedir_marca(number, producto)
