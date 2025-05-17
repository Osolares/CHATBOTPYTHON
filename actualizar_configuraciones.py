# actualizar_configuraciones.py
from woocommerce_service import WooCommerceService
from config import db
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

def actualizar_configuraciones():
    # Categorías
    categorias = woo.obtener_categorias()
    categorias_lista = [{ "id": c["id"], "nombre": c["name"], "slug": c["slug"] } for c in categorias]
    guardar_config("categorias_disponibles", categorias_lista, "Categorías WooCommerce")

    # Atributos (ej: marca, motor, etc.)
    atributos = woo.obtener_atributos()
    for atributo in atributos:
        nombre_atributo = atributo["name"].lower()
        terminos = woo.obtener_terminos_atributo(atributo["id"])
        if terminos:
            terminos_lista = [{ "id": t["id"], "nombre": t["name"], "slug": t["slug"] } for t in terminos]
            guardar_config(f"{nombre_atributo}_disponibles", terminos_lista, f"Términos atributo {nombre_atributo}")

    # Etiquetas (tags)
    etiquetas = woo.obtener_etiquetas()
    etiquetas_lista = [{ "id": t["id"], "nombre": t["name"], "slug": t["slug"] } for t in etiquetas]
    guardar_config("etiquetas_disponibles", etiquetas_lista, "Etiquetas de productos WooCommerce")

    print("✅ Configuraciones sincronizadas correctamente.")

if __name__ == "__main__":
    from app import flask_app
    with flask_app.app_context():
        actualizar_configuraciones()
