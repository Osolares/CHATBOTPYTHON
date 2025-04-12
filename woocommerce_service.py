import requests
from config import Config
from datetime import datetime, timedelta
import json

class WooCommerceService:
    def __init__(self):
        self.base_url = f"{Config.WOOCOMMERCE_URL}/wp-json/wc/v3"
        self.auth = (Config.WOOCOMMERCE_KEY, Config.WOOCOMMERCE_SECRET)
    
    def obtener_ofertas_recientes(self, limite=5):
        """Obtiene las últimas ofertas de WooCommerce"""
        try:
            # Parámetros para productos en oferta y recientes
            params = {
                'per_page': limite,
                'on_sale': 'true',
                'orderby': 'date',
                'order': 'desc',
                'status': 'publish'
            }
            
            response = requests.get(
                f"{self.base_url}/products",
                params=params,
                auth=self.auth
            )
            response.raise_for_status()
            
            return response.json()
        
        except Exception as e:
            print(f"Error al obtener ofertas: {str(e)}")
            return []

    def formatear_ofertas_whatsapp(self, productos):
        """Formatea los productos para mensajes de WhatsApp"""
        if not productos:
            return ["📢 No hay ofertas disponibles en este momento."]

        mensajes = []
        for producto in productos[:3]:  # Limitar a 3 productos
            mensaje = (
                f"🏷️ *{producto['name']}*\n"
                f"💵 Precio: {producto['price']} {producto['currency']}\n"
                f"🔖 SKU: {producto['sku']}\n"
                f"📦 Stock: {producto['stock_status']}\n"
                f"🛒 {producto['permalink']}"
            )
            mensajes.append(mensaje)
        
        return mensajes