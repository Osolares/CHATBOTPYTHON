import re
import json
from rapidfuzz import process, fuzz

def detectar_entidad(texto, lista_config):
    """
    Busca si alguna entidad de una lista aparece en el texto.
    Retorna la entidad encontrada o None.
    """
    texto_limpio = texto.lower()
    for item in lista_config:
        nombre = item.get("nombre", "").lower()
        slug = item.get("slug", "").lower()
        if nombre and nombre in texto_limpio:
            return nombre
        if slug and slug in texto_limpio:
            return slug
    return None

def cargar_configuracion(db_model, clave):
    """Devuelve la lista almacenada en Configuration para una clave"""
    config = db_model.query.filter_by(key=clave).first()
    if config:
        try:
            return json.loads(config.value)
        except:
            return []
    return []


def buscar_coincidencia_aproximada(texto_usuario, lista_opciones, clave="nombre", threshold=80):
    opciones = [item[clave] for item in lista_opciones if clave in item]
    result = process.extractOne(
        texto_usuario, opciones, scorer=fuzz.token_set_ratio, score_cutoff=threshold)
    if result is None:
        return None
    mejor, score, idx = result
    return opciones[idx]