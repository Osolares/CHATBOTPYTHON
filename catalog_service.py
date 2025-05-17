import requests
import json
from models import Configuracion, db
from config import Config

def cargar_config(key):
    config = Configuracion.query.filter_by(clave=key, status='activo').first()
    if not config:
        return []
    try:
        return json.loads(config.valor)
    except Exception:
        return []

def guardar_config(key, lista):
    config = Configuracion.query.filter_by(clave=key).first()
    if not config:
        config = Configuracion(clave=key)
        db.session.add(config)
    config.valor = json.dumps(lista)
    config.status = 'activo'
    db.session.commit()

def get_woocommerce(endpoint, params=None):
    url = f"{Config.WOOCOMMERCE_URL}/wp-json/wc/v3/{endpoint}"
    auth = (Config.WOOCOMMERCE_KEY, Config.WOOCOMMERCE_SECRET)
    response = requests.get(url, auth=auth, params=params)
    response.raise_for_status()
    return response.json()

def sync_marcas():
    productos = get_woocommerce('products', params={'per_page': 100, 'status': 'publish', '_fields': 'attributes'})
    marcas = set()
    for prod in productos:
        for attr in prod.get('attributes', []):
            if attr.get('name', '').lower() == 'marca':
                marcas.update([v.strip() for v in attr.get('options', [])])
    guardar_config('marcas_permitidas', list(marcas))

def sync_series():
    productos = get_woocommerce('products', params={'per_page': 100, 'status': 'publish', '_fields': 'attributes,tags'})
    series = set()
    for prod in productos:
        for attr in prod.get('attributes', []):
            if attr.get('name', '').lower() == 'motor':
                series.update([v.strip() for v in attr.get('options', [])])
        for tag in prod.get('tags', []):
            series.add(tag.get('name', ''))
    guardar_config('series_disponibles', list(series))

def sync_todos_catalogos():
    sync_marcas()
    sync_series()

def get_marcas_permitidas():
    return cargar_config('marcas_permitidas')

def get_series_disponibles():
    return cargar_config('series_disponibles')
