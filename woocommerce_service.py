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
                'status': 'publish',
                '_fields': 'id,name,price,sku,stock_status,permalink,images'  # Solo los campos necesarios
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
    """Formatea los productos para mensajes de WhatsApp con manejo seguro de campos"""
    if not productos:
        return ["📢 No hay ofertas disponibles en este momento."]

    mensajes = []
    for producto in productos[:3]:  # Limitar a 3 productos
        try:
            # Manejo seguro de campos opcionales
            nombre = producto.get('name', 'Producto sin nombre')
            precio = producto.get('price', 'Precio no disponible')
            sku = producto.get('sku', 'N/A')
            stock = producto.get('stock_status', 'N/A')
            enlace = producto.get('permalink', 'https://intermotores.com')
            
            # Obtener imagen principal si existe
            imagen = producto.get('images', [{}])[0].get('src', '')
            
            # Manejo de moneda - solución robusta
            moneda = "USD"  # Valor por defecto
            if 'currency' in producto:
                moneda = producto['currency']
            elif 'currency_symbol' in producto:
                moneda = producto['currency_symbol']
            
            mensaje = (
                f"🏷️ *{nombre}*\n"
                f"💵 Precio: {precio} {moneda}\n"
                f"🔖 SKU: {sku}\n"
                f"📦 Stock: {stock}\n"
                f"🛒 {enlace}"
            )
            
            # Agregar imagen solo si existe
            if imagen:
                mensaje += f"\n📷 {imagen}"  # WhatsApp mostrará previsualización
                
            mensajes.append(mensaje)
        except Exception as e:
            print(f"Error formateando producto: {str(e)}")
            continue
    
    return mensajes if mensajes else ["📢 No se pudieron cargar las ofertas"]