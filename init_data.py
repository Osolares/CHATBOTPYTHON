# init_data.py

from models import db, Configuration, UserSession, KnowledgeBase, UsuarioBloqueado
from config import now
import json

# 1. Días festivos (fijos y por año específico)
DIAS_FESTIVOS_DEFECTO = [
    "01-01",         # Año Nuevo (cada año)
    "05-01",         # Día del Trabajo (cada año)
    "12-25",         # Navidad (cada año)
    "2025-04-17",    # Jueves Santo (sólo 2025)
    "2025-12-31"     # Fin de año (sólo 2025)
]

def inicializar_configuracion():
    configuraciones_defecto = {
        "HORARIO_LUNES": "08:00-17:30",
        "HORARIO_MARTES": "08:00-17:30",
        "HORARIO_MIERCOLES": "08:00-17:30",
        "HORARIO_JUEVES": "08:00-17:30",
        "HORARIO_VIERNES": "08:00-17:30",
        "HORARIO_SABADO": "08:00-12:30",
        "HORARIO_DOMINGO": None,
        "DIAS_FESTIVOS": json.dumps(DIAS_FESTIVOS_DEFECTO, ensure_ascii=False),
        # otros config...
            # ...Fuzzy Slot Fill...
        "FUZZY_MATCH_SCORE": "90",  # Puedes poner 80, 85, 90 según prefieras

    }

    for clave, valor in configuraciones_defecto.items():
        existente = Configuration.query.filter_by(key=clave).first()
        if not existente:
            nueva = Configuration(key=clave, value=valor if valor is not None else "")
            db.session.add(nueva)
    db.session.commit()
    print("✅ Configuración inicial creada")

# Estructura de intenciones por defecto
INTENCIONES_BOT_DEFECTO = {
    "formas_pago": [
        "formas de pago", "transferencia","medios de pago", "pagar con tarjeta", "aceptan tarjeta", "aceptan visa",
        "visa cuotas", "puedo pagar con", "puedo pagar", "metodos de pago", "pago contra entrega"
    ],
    "envios": [
        "envio", "hacen envíos", "métodos de env", "metodos de env", "entregan", "delivery", "a domicilio", "puerta de mi casa", "mandan a casa",
        "hacen envios", "enviar producto", "pueden enviar", "envian el "
    ],
    "ubicacion": [
        "donde estan","ustedes estan", "ubicacion", "ubicación", "direccion", "dirección", "donde queda", "donde están",
        "ubicados", "mapa", "ubicacion tienda", "como llegar", "tienda fisica"
    ],
    "cuentas": [
        "numero de cuenta", "donde deposito ", "bancarias", "banrural", "industrial", "banco", "para depositar"
    ],
    "horario": [
        "horario", "atienden ", "abierto", "cierran", "abren", "a que hora", "a qué hora", "cuando abren", "horario de atencion"
    ],
    "contacto": [
        "contacto", "telefono", "celular", "comunicarme", "llamar", "numero de telefono", "donde puedo llamar"
    ],
    "mensaje_despedida": [
        "gracias por la informacion","ok gracias", "muy amable", "le agradezco", "feliz tarde", "adios", "saludos", "los visito", "feliz dia" , "feliz noche"
    ]
}

def inicializar_intenciones_bot():
    clave = "INTENCIONES_BOT"
    existente = Configuration.query.filter_by(key=clave).first()
    if not existente:
        config = Configuration(
            key=clave,
            value=json.dumps(INTENCIONES_BOT_DEFECTO, ensure_ascii=False)
        )
        db.session.add(config)
        db.session.commit()
        print("✅ Intenciones Bot inicializadas")
    else:
        print("🔹 Ya existen las intenciones bot")

def inicializar_threshold_intencion():
    clave = "INTENCION_THRESHOLD"
    valor_defecto = "90"
    existente = Configuration.query.filter_by(key=clave).first()
    if not existente:
        config = Configuration(key=clave, value=valor_defecto)
        db.session.add(config)
        db.session.commit()
        print("✅ Threshold de intención inicializado")
    else:
        print("🔹 Ya existe threshold de intención")


# init_data.py
PROMPT_ASISTENTE_DEFECTO = """
Eres un asistente llamado Boty especializado en motores y repuestos para vehículos de marcas japonesas y coreanas que labora en Intermotores, responde muy puntual y en las minimas palabras máximo 50 usa emojis ocasionalmente según sea necesario. 

Solo responde sobre:
- Motores y repuestos para vehículos
- Piezas, partes o repuestos de automóviles

No incluyas información innecesaria (como el número de palabras).
nunca confirmes disponibilidad, existencias, precio, etc

Si el mensaje no está relacionado, responde cortésmente indicando que solo puedes ayudar con temas de motores y repuestos.
si es un mensaje de saludo, bienvenida, agradecimiento o despedida responde algo acorde

{prompt_usuario}
"""

def inicializar_prompt_asistente():
    clave = "PROMPT_ASISTENTE"
    existente = Configuration.query.filter_by(key=clave).first()
    if not existente:
        config = Configuration(key=clave, value=PROMPT_ASISTENTE_DEFECTO)
        db.session.add(config)
        db.session.commit()
        print("✅ Prompt asistente inicializado")
    else:
        print("🔹 Ya existe prompt asistente")


PROMPT_SLOT_FILL_DEFECTO = """
Extrae la siguiente información en JSON. Pon null si no se encuentra.
Campos: tipo_repuesto, marca, modelo, año, serie_motor, cc, combustible, codigo_repuesto

Ejemplo:
Entrada: "Turbo para sportero 2.5 28231-27000"
el año tambien te lo pueden decir como modelo y puede venir abreviado ejmplo "modelo 90"
la linea puede tener algunas variaciones o estar mal escrita ejemplo "colola" en vez de "corolla"
Salida:
{"tipo_repuesto":"turbo","marca":null,"linea":"sportero","año":null,"serie_motor":null,"cc":"2.5","combustible":null,"codigo_repuesto":"28231-27000"}

Entrada: "{MENSAJE}"
Salida:
"""

def inicializar_prompt_slot_fill():
    clave = "PROMPT_SLOT_FILL"
    existente = Configuration.query.filter_by(key=clave).first()
    if not existente:
        config = Configuration(key=clave, value=PROMPT_SLOT_FILL_DEFECTO)
        db.session.add(config)
        db.session.commit()
        print("✅ Prompt slot filling inicializado")
    else:
        print("🔹 Ya existe prompt slot filling")


def inicializar_knowledge_base():
    # -- Reglas de serie motor --
    reglas_serie_motor = {

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
    for clave, valor in reglas_serie_motor.items():
        existente = KnowledgeBase.query.filter_by(tipo="serie_motor", clave=clave).first()
        if not existente:
            kb = KnowledgeBase(tipo="serie_motor", clave=clave, valor=json.dumps(valor, ensure_ascii=False))
            db.session.add(kb)


    # Marcas con sus líneas/alias (estructura MARCAS_LINEAS)
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


    }
    # Guarda todo el diccionario como un solo registro
    existente = KnowledgeBase.query.filter_by(tipo="marca_linea", clave="all").first()
    if not existente:
        kb = KnowledgeBase(
            tipo="marca_linea",
            clave="all",
            valor=json.dumps(MARCAS_LINEAS, ensure_ascii=False),
            descripcion="Todas las marcas, líneas/modelos y sus variantes de alias"
        )
        db.session.add(kb)

    # Frases "no sé"
    frases_no_se = ["no sé", "no se", "nose", "no tengo", "no la tengo", "no recuerdo", "desconozco", "no aplica"]
    for frase in frases_no_se:
        existente = KnowledgeBase.query.filter_by(tipo="frase_no_se", clave=frase).first()
        if not existente:
            kb = KnowledgeBase(tipo="frase_no_se", clave=frase, valor=json.dumps(frase, ensure_ascii=False))
            db.session.add(kb)

    # Tipos de repuesto
    tipos_repuesto = [
        "motor", "culata", "turbina", "bomba", "inyector", "alternador", "radiador", "turbo", 
        "caja de velocidades", "eje de levas", "termostato", "caja", "transmisión", "transmision", "computadora",
        # ... el resto
    ]
    for tipo in tipos_repuesto:
        existente = KnowledgeBase.query.filter_by(tipo="tipo_repuesto", clave=tipo).first()
        if not existente:
            kb = KnowledgeBase(tipo="tipo_repuesto", clave=tipo, valor=json.dumps(tipo, ensure_ascii=False))
            db.session.add(kb)

    # Preguntas slots
    preguntas_slots = {
        "tipo_repuesto": [
            "¿Qué repuesto necesitas? (ejemplo: motor, culata, turbo, etc.)",
            "¿Sobre qué repuesto te gustaría cotizar?",
            "¿Cuál es el repuesto de tu interes?",
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
            # ... agrega para cada slot
    }
    for slot, preguntas in preguntas_slots.items():
        existente = KnowledgeBase.query.filter_by(tipo="pregunta_slot", clave=slot).first()
        if not existente:
            kb = KnowledgeBase(tipo="pregunta_slot", clave=slot, valor=json.dumps(preguntas, ensure_ascii=False))
            db.session.add(kb)

    db.session.commit()
    print("✅ Knowledge base inicializada")

def inicializar_usuarios_bloqueados():
    usuarios = [
        ("whatsapp", "502123456", "usuario problemático"),
        ("whatsapp", "50233334444", "spam"),
        ("web", "correo@ejemplo.com", "abuso"),
    ]
    for tipo, identificador, razon in usuarios:
        if not UsuarioBloqueado.query.filter_by(tipo=tipo, identificador=identificador).first():
            db.session.add(UsuarioBloqueado(tipo=tipo, identificador=identificador, razon=razon))
    db.session.commit()

def inicializar_tipos_mensajes_bloqueados():
    from models import Configuration
    tipos_bloqueados = {
        "whatsapp": ["reaction"],
        "telegram": ["sticker"],
        "web": []
    }
    if not Configuration.query.filter_by(key="TIPOS_MENSAJES_BLOQUEADOS").first():
        db.session.add(Configuration(key="TIPOS_MENSAJES_BLOQUEADOS", value=json.dumps(tipos_bloqueados)))
    db.session.commit()


def inicializar_configuracion_delay():
    clave = "WHATSAPP_DELAY_SECONDS"
    valor_defecto = "4"
    if not Configuration.query.filter_by(key=clave).first():
        config = Configuration(key=clave, value=valor_defecto, descripcion="Delay entre mensajes WhatsApp (segundos)")
        db.session.add(config)
        db.session.commit()

def inicializar_usuarios():
    usuarios_defecto = [
        {"phone_number": "50255105350", "nombre": "Oscar", "apellido": "Solares", "tipo_usuario": "admin"},
        {"phone_number": "50212342468", "nombre": "Soporte", "apellido": "Técnico", "tipo_usuario": "colaborador"},
        {"phone_number": "50212345678", "nombre": "Carlos", "apellido": "Cliente", "tipo_usuario": "cliente"}
    ]

    for usr in usuarios_defecto:
        existente = UserSession.query.filter_by(phone_number=usr["phone_number"]).first()
        if not existente:
            nuevo_usuario = UserSession(
                phone_number=usr["phone_number"],
                nombre=usr["nombre"],
                apellido=usr["apellido"],
                tipo_usuario=usr["tipo_usuario"],
                last_interaction=now()
            )
            db.session.add(nuevo_usuario)
    db.session.commit()
    print("✅ Usuarios de prueba creados")

from models import MensajeBot, db
from config import now

def inicializar_mensajes_bot():
    mensajes = [
        # Bienvenidas (WhatsApp)
        {"tipo": "bienvenida", "mensaje": "😃 ¡Bienvenido(a) a Intermotores Guatemala, qué gusto tenerte aquí! Dinos qué necesitas. 🚗\n\n🗒️ Consulta nuestro menú.", "canal": "whatsapp"},
        {"tipo": "bienvenida", "mensaje": "👋 ¡Bienvenido(a) a Intermotores Guatemala! Estamos aquí para ayudarte a encontrar el repuesto ideal para tu vehículo. 🚗\n\n🗒️ Consulta nuestro menú.", "canal": "whatsapp"},

        # Alerta fuera de horario (WhatsApp)
        {"tipo": "alerta_fuera_horario", "mensaje": "⌚ Gracias por comunicarte. Ahora mismo estamos fuera de horario, pero tu consulta es importante para nosotros. ¡Te responderemos pronto!", "canal": "all"},
        {"tipo": "alerta_fuera_horario", "mensaje": "🕒 Gracias por comunicarte con nosotros. En este momento estamos fuera de nuestro horario de atención.\n\n💬 Puedes continuar usando nuestro asistente y nuestro equipo te atenderá lo más pronto posible.", "canal": "all"},
        {"tipo": "alerta_fuera_horario", "mensaje": "⌛ Nuestro equipo está fuera de horario. Puedes dejar tu mensaje aquí y te reponderemos lo mas pronto posible.", "canal": "all"},

        # Re-bienvenida (WhatsApp)
        {"tipo": "re_bienvenida", "mensaje": "👋 ¡Hola de nuevo! ¿Te ayudamos con otra cotización? 🚗\n\n🗒️ Consulta nuestro menú.", "canal": "whatsapp"},
        {"tipo": "re_bienvenida", "mensaje": "🚗 ¿Necesitas otro repuesto? Estamos para servirte 🚗\n\n🗒️ Consulta nuestro menú..", "canal": "whatsapp"},
        {"tipo": "re_bienvenida", "mensaje": "👋 ¡Hola de nuevo! Gracias por contactar a Intermotores Guatemala. ¿En qué podemos ayudarte hoy? 🚗\n\n🗒️ Consulta nuestro menú.", "canal": "whatsapp"},
        {"tipo": "re_bienvenida", "mensaje": "👋 ¡Bienvenido(a) de nuevo! ¿En qué podemos ayudarte hoy?", "canal": "whatsapp"},
        {"tipo": "re_bienvenida", "mensaje": "🚗 ¡Hola Bienvenido(a) de nuevo a Intermotores Guatemala ¿Buscas un motor o repuesto? Pregúntanos sin compromiso.", "canal": "whatsapp"},
        # Mensaje global, para todos los canales (canal='all')

        #DIAS FESTIVOS
        {"tipo": "alerta_dia_festivo_01-01", "mensaje": "🎉 Hoy es 1 de enero (Año Nuevo). ¡Estamos cerrados! Disfruta tu día y escríbenos mañana.", "canal": "all"},
        {"tipo": "alerta_dia_festivo_05-01", "mensaje": "🎉 Hoy es 1 de mayo (Día del Trabajo). ¡Estamos cerrados! Gracias por tu preferencia.", "canal": "all"},
        {"tipo": "alerta_dia_festivo_12-25", "mensaje": "🎄 ¡Feliz Navidad! Hoy no laboramos. Puedes dejar tu mensaje y te atenderemos el siguiente día hábil.", "canal": "all"},
        {"tipo": "alerta_dia_festivo_2025-04-17", "mensaje": "⛪ Hoy es Jueves Santo y estamos de descanso. Te responderemos el próximo día hábil.", "canal": "all"},
        {"tipo": "alerta_dia_festivo", "mensaje": "🎉 Hoy es día festivo y estamos cerrados. Puedes dejar tu mensaje y te responderemos en el próximo día hábil.", "canal": "all"},

        # Formas de pago (varios, para rotar)
        #{"tipo": "formas_pago", "mensaje": "💳 Aceptamos efectivo, depósitos, transferencias, Visa Cuotas y pago contra entrega.", "canal": "whatsapp"},
        {"tipo": "formas_pago", "mensaje": "*💲Medios de pago:* \n\n 💵 Efectivo. \n\n 🏦 Depósitos o transferencias bancarias. \n\n 📦 Pago contra Entrega. \nPagas al recibir tu producto, aplica para envíos por medio de Guatex, el monto máximo es de Q5,000. \n\n💳 Visa Cuotas. \nHasta 12 cuotas con tu tarjeta visa \n\n💳 Cuotas Credomatic. \nHasta 12 cuotas con tu tarjeta BAC Credomatic \n\n🔗 Neo Link. \nTe enviamos un link para que pagues con tu tarjeta sin salir de casa", "canal": "whatsapp"},
        # Envíos
        {"tipo": "envios", "mensaje": "🏠*Enviamos nuestros productos hasta la puerta de su casa* \n\n 🛵 *Envíos dentro de la capital.* \n Hacemos envíos directos dentro de la ciudad capital, aldea Puerta Parada, Santa Catarina Pinula y sus alrededores \n\n 🚚 *Envío a Departamentos.* \nHacemos envíos a los diferentes departamentos del país por medio de terceros o empresas de transporte como Guatex, Cargo Express, Forza o el de su preferencia. \n\n ⏳📦 *Tiempo de envío.* \nLos pedidos deben hacerse con 24 horas de anticipación y el tiempo de entrega para los envíos directos es de 24 a 48 horas y para los envíos a departamentos depende directamente de la empresa encargarda.", "canal": "whatsapp"},
        # Ubicación
        {"tipo": "ubicacion", "mensaje": "📍  Estamos ubicados en km 13.5 carretera a El Salvador frente a Plaza Express a un costado de farmacia Galeno, en Intermotores", "canal": "whatsapp"},
        # Horario
        {"tipo": "horario", "mensaje": "📅 Horario de Atención:\n\n Lunes a Viernes\n🕜 8:00 am a 5:00 pm\n\nSábado\n🕜 8:00 am a 12:00 pm\n\nDomingo Cerrado 🤓", "canal": "whatsapp"},

        {"tipo": "contacto", "mensaje": "☎*Comunícate con nosotros será un placer atenderte* \n\n 📞 6637-9834 \n\n 📞 6646-6137 \n\n 📱 5510-5350 \n\n 🌐 www.intermotores.com  \n\n 📧 intermotores.ventas@gmail.com \n\n *Facebook* \n Intermotores GT\n\n *Instagram* \n Intermotores GT ", "canal": "whatsapp"},

        {"tipo": "mensaje_despedida", "mensaje": "De nada, ¡qué tengas buen día! 🚗💨", "canal": "whatsapp"},
        {"tipo": "mensaje_despedida", "mensaje": "De nada, ¡qué tengas un gran día! 😊🚗💨", "canal": "whatsapp"},
        {"tipo": "mensaje_despedida", "mensaje": "Fue un gusto ayudarte. ¡Hasta la próxima! 😊🔧", "canal": "whatsapp"},

    ]
    for datos in mensajes:
        existe = MensajeBot.query.filter_by(
            tipo=datos["tipo"], mensaje=datos["mensaje"], canal=datos["canal"]
        ).first()
        if not existe:
            nuevo = MensajeBot(
                tipo=datos["tipo"],
                mensaje=datos["mensaje"],
                canal=datos.get("canal", "all"),
                idioma=datos.get("idioma", "es"),
                activo=True,
                created_at=now(),
                updated_at=now()
            )
            db.session.add(nuevo)
    db.session.commit()
    print("✅ Mensajes dinámicos iniciales creados")

def inicializar_todo():
    inicializar_configuracion()
    inicializar_usuarios()
    inicializar_mensajes_bot()
    inicializar_intenciones_bot()
    inicializar_threshold_intencion()
    inicializar_prompt_asistente()
    inicializar_prompt_slot_fill()
    inicializar_knowledge_base()
    inicializar_configuracion_delay()
    inicializar_tipos_mensajes_bloqueados()
    inicializar_usuarios_bloqueados()