import json
from woocommerce_service import WooCommerceService
from models import db, Configuration
from app import flask_app

def guardar_configuracion(key, value_list):
    value_str = json.dumps(sorted(set(value_list)))
    config = Configuration.query.filter_by(key=key).first()
    if not config:
        config = Configuration(key=key)
        db.session.add(config)
    config.value = value_str
    db.session.commit()

def actualizar_configuracion_desde_woocommerce():
    with flask_app.app_context():
        woo = WooCommerceService()
        productos = woo.obtener_todos_los_productos(limit=100)

        categorias = set()
        marcas = set()
        series = set()

        for p in productos:
            if 'categories' in p:
                categorias.update([cat['name'] for cat in p['categories']])

            for attr in p.get('attributes', []):
                nombre = attr.get('name', '').lower()
                opciones = attr.get('options', [])
                if 'marca' in nombre:
                    marcas.update(opciones)
                if 'motor' in nombre:
                    series.update(opciones)

            if 'tags' in p:
                series.update([tag['name'] for tag in p['tags']])

        guardar_configuracion('categorias_disponibles', list(categorias))
        guardar_configuracion('marcas_permitidas', list(marcas))
        guardar_configuracion('series_disponibles', list(series))
        print("✅ Configuración actualizada desde WooCommerce.")