# utils.py o config_utils.py
import json
from models import Configuration

def cargar_config(key):
    config = Configuration.query.filter_by(key=key, status='activo').first()
    if not config:
        return []
    try:
        return json.loads(config.value)
    except Exception:
        return []
