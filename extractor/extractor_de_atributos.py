import re
from models import Configuration
from flask import current_app

def cargar_lista_config(key):
    config = Configuration.query.filter_by(key=key, status='activo').first()
    if not config:
        return []
    try:
        return [v.strip().lower() for v in json.loads(config.value)]
    except:
        return []

def extraer_atributos_desde_texto(texto):
    texto = texto.lower()
    atributos = {
        "marca": None,
        "anio": None,
        "motor": None,
        "combustible": None,
        "cilindraje": None
    }

    with current_app.app_context():
        marcas = cargar_lista_config("marcas_permitidas")
        motores = cargar_lista_config("series_disponibles")

    for marca in marcas:
        if marca.lower() in texto:
            atributos["marca"] = marca
            break

    for serie in motores:
        if serie.lower() in texto:
            atributos["motor"] = serie
            break

    anios = re.findall(r"20[0-4][0-9]|19[8-9][0-9]", texto)
    if anios:
        atributos["anio"] = anios[0]

    if "diésel" in texto or "diesel" in texto:
        atributos["combustible"] = "diésel"
    elif "gasolina" in texto:
        atributos["combustible"] = "gasolina"

    cc_match = re.search(r"(\d{1,2}[\.\,]?\d{0,2})\s?(cc|litros|l)", texto)
    if cc_match:
        atributos["cilindraje"] = cc_match.group(1).replace(",", ".")

    return atributos